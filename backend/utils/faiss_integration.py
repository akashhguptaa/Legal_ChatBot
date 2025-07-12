import os
import pickle
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from loguru import logger

import faiss
from langchain_openai import OpenAIEmbeddings
from config.config import OPENAI_API_KEY

# PDF processing imports
import PyPDF2
import tiktoken
from typing import List, Dict, Any

embeddings_model = OpenAIEmbeddings(
    api_key=OPENAI_API_KEY, model="text-embedding-3-small"
)

# Initialize tokenizer for counting tokens
try:
    tokenizer = tiktoken.get_encoding("cl100k_base")
except:
    tokenizer = None


FAISS_INDEX_DIR = Path("Faiss_index")
FAISS_INDEX_DIR.mkdir(exist_ok=True)


def get_file_paths(file_id: str):
    """Get file paths for FAISS index and metadata."""
    return {
        "index": FAISS_INDEX_DIR / f"{file_id}.index",
        "metadata": FAISS_INDEX_DIR / f"{file_id}_metadata.pkl",
    }


def create_embedding_batch(batch_data):
    """Create embeddings for a batch of sections."""
    batch_sections, start_idx = batch_data
    batch_embeddings = []

    for i, section in enumerate(batch_sections):
        try:
            embedding = embeddings_model.embed_query(section["content"])
            batch_embeddings.append({"embedding": embedding, "index": start_idx + i})
        except Exception as e:
            logger.error(f"Error creating embedding for section {start_idx + i}: {e}")
            continue

    return batch_embeddings


async def create_faiss_embeddings(
    sections: List[Dict], file_id: str, filename: str
) -> int:
    """Create FAISS embeddings with parallel processing."""
    logger.info(f"Creating FAISS embeddings for {len(sections)} sections")

    # Prepare batches of 10 sections
    batches = []
    for i in range(0, len(sections), 10):
        batch = sections[i : i + 10]
        batches.append((batch, i))

    # Process batches in parallel with 4 workers
    all_embeddings = []
    metadata = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(create_embedding_batch, batches))

    for batch_result in results:
        for item in batch_result:
            all_embeddings.append(item["embedding"])
            section_data = sections[item["index"]]

            # Extract metadata
            metadata.append(
                {
                    "section_index": item["index"],
                    "section_title": section_data.get("section_title", ""),
                    "content": section_data.get("content", ""),
                    "page_start": section_data.get("page_start", 0),
                    "page_end": section_data.get("page_end", 0),
                    "token_count": section_data.get("token_count", 0),
                    "hierarchy_level": section_data.get("hierarchy_level", 0),
                    "contains_definitions": None,
                    "contains_obligations": None,
                    "contains_dates": None,
                    "file_id": file_id,
                    "filename": filename,
                }
            )

    if not all_embeddings:
        logger.error("No embeddings created")
        return 0

    dimension = len(all_embeddings[0])
    index = faiss.IndexFlatIP(dimension)  # Inner product for cosine similarity

    embeddings_array = np.array(all_embeddings).astype("float32")
    faiss.normalize_L2(embeddings_array)

    index.add(embeddings_array)

    paths = get_file_paths(file_id)
    faiss.write_index(index, str(paths["index"]))

    with open(paths["metadata"], "wb") as f:
        pickle.dump(metadata, f)

    logger.info(f"Created FAISS index with {len(all_embeddings)} embeddings")
    return sum(item["token_count"] for item in metadata)


def load_faiss_index(file_id: str):
    """Load FAISS index and metadata for a file."""
    paths = get_file_paths(file_id)

    if not paths["index"].exists() or not paths["metadata"].exists():
        raise FileNotFoundError(f"FAISS index not found for file {file_id}")

    index = faiss.read_index(str(paths["index"]))

    with open(paths["metadata"], "rb") as f:
        metadata = pickle.load(f)

    return index, metadata


def search_similar_sections(
    query: str, file_id: str = None, limit: int = 5
) -> List[Dict]:
    """Search for similar sections using FAISS."""
    try:
        if not file_id:
            raise ValueError("file_id is required for FAISS search")

        index, metadata = load_faiss_index(file_id)

        query_embedding = embeddings_model.embed_query(query)
        query_vector = np.array([query_embedding]).astype("float32")
        faiss.normalize_L2(query_vector)

        scores, indices = index.search(query_vector, limit)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(metadata):
                result = metadata[idx].copy()
                result["score"] = float(scores[0][i])
                results.append(result)

        return results

    except Exception as e:
        logger.error(f"Error in FAISS search: {e}")
        return []


def get_document_info(file_id: str) -> Dict[str, Any]:
    """Get document information from FAISS metadata."""
    try:
        _, metadata = load_faiss_index(file_id)

        max_page = max(item["page_end"] for item in metadata)
        total_sections = len(metadata)

        return {
            "total_pages": max_page,
            "total_sections": total_sections,
            "filename": metadata[0]["filename"] if metadata else "Unknown",
        }
    except Exception as e:
        logger.error(f"Error getting document info: {e}")
        return {"total_pages": 0, "total_sections": 0, "filename": "Unknown"}


def process_query_search(query: str, file_id: str) -> Dict[str, Any]:
    """Process query with metadata extraction and filtering."""
    
    # Step 1: Extract metadata from query
    metadata = extract_query_metadata(query)
    
    if metadata["has_metadata"]:
        # Step 2: Generate pre-filters based on metadata
        filters = generate_prefilters(metadata)
        
        # Step 3: Vector search with filters
        results = filtered_vector_search(query, file_id, filters)
        
        return {
            "type": "filtered_search",
            "query": query,
            "metadata_found": metadata,
            "filters_applied": filters,
            "results": results,
            "answer": generate_filtered_answer(query, results, metadata)
        }
    else:
        # Direct vector search
        results = search_similar_sections(query, file_id, limit=5)
        
        return {
            "type": "semantic_search",
            "query": query,
            "results": results,
            "answer": generate_answer_with_context(query, results)
        }


def get_section_content(metadata: List[Dict], section_num: int) -> Dict[str, Any]:
    """Get specific section content."""
    section = None
    for item in metadata:
        if item["section_index"] == section_num:
            section = item
            break

    if not section:
        return {
            "type": "section_content",
            "query": f"Section {section_num}",
            "answer": f"Section {section_num} not found.",
            "data": None,
        }

    return {
        "type": "section_content",
        "query": f"Section {section_num}",
        "answer": f"Section {section_num}: {section['section_title']}\n\n{section['content'][:500]}...",
        "data": section,
    }

def semantic_search(query: str, file_id: str) -> Dict[str, Any]:
    """Perform semantic search."""
    results = search_similar_sections(query, file_id, limit=5)

    if not results:
        return {
            "type": "semantic_search",
            "query": query,
            "answer": "No relevant content found.",
            "data": {"results": []},
        }

    answer = f"Found {len(results)} relevant sections:\n\n"
    for i, result in enumerate(results, 1):
        answer += f"{i}. {result['section_title']}\n"
        answer += f"   {result['content'][:200]}...\n\n"

    return {
        "type": "semantic_search",
        "query": query,
        "answer": answer,
        "data": {"results": results},
    }


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken."""
    if not tokenizer:
        return len(text) // 4
    return len(tokenizer.encode(text))

def extract_pdf_sections(pdf_path: str, max_tokens: int = 500) -> List[Dict[str, Any]]:
    """Chunk PDF by logical sections with token limits"""
    sections = []
    current_section = []
    current_tokens = 0
    hierarchy = 0
    
    with open(pdf_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)
        
        for page_num, page in enumerate(pdf_reader.pages, 1):
            text = page.extract_text()
            if not text.strip():
                continue
                
            lines = text.split('\n')
            header = None

            if len(lines) > 1 and _is_section_header(lines[0]):
                header = lines[0]
                hierarchy = _get_header_level(header)
                remaining_text = "\n".join(lines[1:])
            else:
                remaining_text = text

            tokens = count_tokens(remaining_text)
            
            if (header or current_tokens + tokens > max_tokens) and current_section:
                sections.append(_create_section(current_section))
                current_section = []
                current_tokens = 0
                
            current_section.append({
                "page": page_num,
                "header": header,
                "text": remaining_text,
                "tokens": tokens,
                "hierarchy": hierarchy
            })
            current_tokens += tokens
            
        if current_section:
            sections.append(_create_section(current_section))
            
    return sections

def _create_section(pages: List[Dict]) -> Dict[str, Any]:
    """Combine pages into a coherent section"""
    return {
        "section_title": pages[0]["header"] or f"Section starting page {pages[0]['page']}",
        "content": "\n".join(p["text"] for p in pages),
        "page_start": pages[0]["page"],
        "page_end": pages[-1]["page"],
        "token_count": sum(p["tokens"] for p in pages),
        "hierarchy_level": pages[0]["hierarchy"]
    }


def _is_section_header(line: str) -> bool:
    """Check if a line might be a section header."""
    header_patterns = [
        r"^[A-Z][A-Z\s]+$",  # ALL CAPS
        r"^\d+\.\s+[A-Z]",  # Numbered sections
        r"^[A-Z][a-z]+(\s+[A-Z][a-z]+)*$",  # Title Case
        r"^Section\s+\d+",  # Section X
        r"^Chapter\s+\d+",  # Chapter X
        r"^Article\s+\d+",  # Article X
        r"^Part\s+\d+",  # Part X
    ]

    for pattern in header_patterns:
        if re.match(pattern, line.strip()):
            return True

    if len(line.strip()) < 100 and any(
        indicator in line for indicator in [":", ".", "§"]
    ):
        return True

    return False


def _get_header_level(line: str) -> int:
    """Determine the hierarchy level of a header."""
    line_lower = line.lower()

    if any(word in line_lower for word in ["chapter", "part"]):
        return 1
    elif any(word in line_lower for word in ["section", "article"]):
        return 2
    elif re.match(r"^\d+\.\d+", line):
        return 3
    elif re.match(r"^\d+\.", line):
        return 2
    else:
        return 1


def extract_query_metadata(query: str) -> Dict[str, Any]:
    """Extract metadata like page numbers, sections from query."""
    metadata = {"has_metadata": False}
    
    # Check for page numbers
    page_match = re.search(r'page\s*(\d+)', query.lower())
    if page_match:
        metadata["page"] = int(page_match.group(1))
        metadata["has_metadata"] = True
    
    # Check for section numbers
    section_match = re.search(r'section\s*(\d+)', query.lower())
    if section_match:
        metadata["section"] = int(section_match.group(1))
        metadata["has_metadata"] = True
    
    return metadata

def generate_prefilters(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Generate filters based on extracted metadata."""
    filters = {}
    
    if "page" in metadata:
        filters["page_range"] = [metadata["page"] - 1, metadata["page"] + 1]
    
    if "section" in metadata:
        filters["section_index"] = metadata["section"]
    
    return filters

def filtered_vector_search(query: str, file_id: str, filters: Dict[str, Any]) -> List[Dict]:
    """Vector search with pre-filters applied."""
    try:
        index, metadata = load_faiss_index(file_id)
        
        filtered_indices = []
        for i, item in enumerate(metadata):
            if apply_filters(item, filters):
                filtered_indices.append(i)
        
        if not filtered_indices:
            return search_similar_sections(query, file_id, limit=3)
        
        # Create query embedding
        query_embedding = embeddings_model.embed_query(query)
        query_vector = np.array([query_embedding]).astype("float32")
        faiss.normalize_L2(query_vector)
        
        scores, indices = index.search(query_vector, len(filtered_indices))
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx in filtered_indices and i < 3:  
                result = metadata[idx].copy()
                result["score"] = float(scores[0][i])
                results.append(result)
        
        return results
        
    except Exception as e:
        logger.error(f"Error in filtered search: {e}")
        return search_similar_sections(query, file_id, limit=3)

def apply_filters(item: Dict, filters: Dict[str, Any]) -> bool:
    """Check if item matches the filters."""
    if "page_range" in filters:
        page_start, page_end = filters["page_range"]
        if not (page_start <= item["page_start"] <= page_end or 
                page_start <= item["page_end"] <= page_end):
            return False
    
    if "section_index" in filters:
        if item["section_index"] != filters["section_index"]:
            return False
    
    return True

def generate_filtered_answer(query: str, results: List[Dict], metadata: Dict) -> str:
    """Generate answer for filtered search results."""
    if not results:
        return "No relevant content found with the specified filters."
    
    answer = f"Based on your search"
    if "page" in metadata:
        answer += f" around page {metadata['page']}"
    if "section" in metadata:
        answer += f" in section {metadata['section']}"
    answer += ":\n\n"
    
    for result in results:
        answer += f"• {result['content'][:200]}... (Page {result['page_start']}-{result['page_end']})\n\n"
    
    return answer

def generate_answer_with_context(query: str, results: List[Dict]) -> str:
    """Generate answer with page context for regular search."""
    if not results:
        return "No relevant content found."
    
    answer = "Found relevant information:\n\n"
    for result in results:
        answer += f"• {result['content'][:200]}... (Page {result['page_start']}-{result['page_end']})\n\n"
    
    return answer