import asyncio
from typing import List, Dict, Any
import PyPDF2
from langchain_openai import OpenAIEmbeddings
from config.config import OPENAI_API_KEY, MONGODB_URI
from pymongo import MongoClient
from datetime import datetime
import re
from pathlib import Path
from loguru import logger
from utils.manage_chunking import LegalDocumentChunker, count_tokens
import concurrent.futures
from functools import partial


DOCS_FOLDER = Path("docs")
DOCS_FOLDER.mkdir(exist_ok=True)

client = MongoClient(MONGODB_URI)
db = client["chatbot_db2"]
files_collection = db["files"]
embeddings_collection = db["embeddings"]

embeddings_model = OpenAIEmbeddings(
    api_key=OPENAI_API_KEY,
    model="text-embedding-3-small"  # Cost-efficient model
)


MAX_CHUNK_TOKENS = 512
OVERLAP_PERCENTAGE = 0.15


def extract_pdf_sections(pdf_path: str) -> List[Dict[str, Any]]:
    """Enhanced PDF extraction with structure preservation"""
    chunker = LegalDocumentChunker()
    
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        
        full_text = ""
        page_mapping = {}
        current_char = 0
        
        for page_num, page in enumerate(pdf_reader.pages):
            page_text = page.extract_text()
            page_mapping[current_char] = page_num + 1
            full_text += page_text + "\n"
            current_char = len(full_text)
        
        # Extract hierarchical sections
        sections = chunker.extract_hierarchical_sections(full_text)
        
        # Create overlapping chunks
        chunks = chunker.create_overlapping_chunks(sections)
        
        # Add page numbers to chunks
        for chunk in chunks:
            # Estimate page number based on content position
            chunk['page_start'] = 1
            chunk['page_end'] = len(pdf_reader.pages)
            
            # Add metadata for better retrieval
            chunk['metadata'] = {
                'document_type': 'legal',
                'hierarchy_level': len(chunk.get('hierarchy', [])),
                'has_subsections': any(re.match(r'^\s*\([a-z0-9]\)', line) 
                                     for line in chunk['content'].split('\n')),
                'contains_definitions': 'definition' in chunk['content'].lower(),
                'contains_obligations': any(word in chunk['content'].lower() 
                                          for word in ['shall', 'must', 'required', 'obligation']),
                'contains_dates': bool(re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', chunk['content'])),
                'word_count': len(chunk['content'].split())
            }
    
    return chunks

def extract_pdf_sections(pdf_path: str) -> List[Dict[str, Any]]:
    """Enhanced PDF extraction with structure preservation"""
    chunker = LegalDocumentChunker()
    
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        
        full_text = ""
        page_mapping = {}
        current_char = 0
        
        for page_num, page in enumerate(pdf_reader.pages):
            page_text = page.extract_text()
            page_mapping[current_char] = page_num + 1
            full_text += page_text + "\n"
            current_char = len(full_text)
        
        # Extract hierarchical sections
        sections = chunker.extract_hierarchical_sections(full_text)
        
        # Create overlapping chunks
        chunks = chunker.create_overlapping_chunks(sections)
        
        # Add page numbers to chunks
        for chunk in chunks:
            # Estimate page number based on content position
            chunk['page_start'] = 1
            chunk['page_end'] = len(pdf_reader.pages)
            
            # Add metadata for better retrieval
            chunk['metadata'] = {
                'document_type': 'legal',
                'hierarchy_level': len(chunk.get('hierarchy', [])),
                'has_subsections': any(re.match(r'^\s*\([a-z0-9]\)', line) 
                                     for line in chunk['content'].split('\n')),
                'contains_definitions': 'definition' in chunk['content'].lower(),
                'contains_obligations': any(word in chunk['content'].lower() 
                                          for word in ['shall', 'must', 'required', 'obligation']),
                'contains_dates': bool(re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', chunk['content'])),
                'word_count': len(chunk['content'].split())
            }
    
    return chunks

async def create_embeddings_batch(sections: List[Dict], file_id: str) -> int:
    """Create embeddings for sections in batches with parallel processing"""
    batch_size = 10
    total_tokens = 0
    max_workers = 4  # 4 workers for parallel processing
    
    def process_batch_sync(batch_sections, batch_index):
        """Synchronous batch processing function for thread pool"""
        texts = [section['content'] for section in batch_sections]
        batch_tokens = sum(count_tokens(text) for text in texts)
        
        try:
            # Create embeddings synchronously
            embeddings = embeddings_model.embed_documents(texts)
            
            embedding_docs = []
            for j, (section, embedding) in enumerate(zip(batch_sections, embeddings)):
                doc = {
                    'file_id': file_id,
                    'section_index': batch_index * batch_size + j,
                    'section_title': section['section_title'],
                    'content': section['content'],
                    'embedding': embedding,
                    'page_start': section.get('page_start', 1),
                    'page_end': section.get('page_end', 1),
                    'token_count': section['token_count'],
                    'hierarchy': section.get('hierarchy', []),
                    'metadata': section.get('metadata', {}),
                    'has_overlap': section.get('has_overlap', False),
                    'is_split': section.get('is_split', False),
                    'created_at': datetime.utcnow().isoformat()
                }
                
                if section.get('has_overlap'):
                    doc['overlap_source'] = section.get('overlap_source', '')
                if section.get('is_split'):
                    doc['part_number'] = section.get('part_number', 1)
                    doc['total_parts'] = section.get('total_parts', 1)
                
                embedding_docs.append(doc)
            
            return embedding_docs, batch_tokens
            
        except Exception as e:
            logger.error(f"Error processing batch {batch_index}: {e}")
            return [], 0
    
    # Create batches
    batches = [sections[i:i + batch_size] for i in range(0, len(sections), batch_size)]
    
    # Process batches in parallel using ThreadPoolExecutor
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all batch processing tasks
        futures = [
            loop.run_in_executor(
                executor, 
                partial(process_batch_sync, batch, i)
            )
            for i, batch in enumerate(batches)
        ]
        
        # Wait for all batches to complete
        results = await asyncio.gather(*futures)
    
    # Insert all results into MongoDB
    all_docs = []
    for embedding_docs, batch_tokens in results:
        if embedding_docs:
            all_docs.extend(embedding_docs)
            total_tokens += batch_tokens
    
    # Bulk insert all documents at once
    if all_docs:
        embeddings_collection.insert_many(all_docs)
        logger.info(f"Inserted {len(all_docs)} documents with {total_tokens} total tokens")
    
    return total_tokens