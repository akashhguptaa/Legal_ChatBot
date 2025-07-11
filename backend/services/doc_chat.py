import os
import asyncio
import traceback
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import hashlib
import json

# Core dependencies
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain.schema import BaseRetriever

# Additional dependencies
import pymongo
from pymongo import MongoClient
import fitz  # PyMuPDF for better PDF handling
from loguru import logger
import aiofiles
import tempfile

# from config.config import OPENAI_API_KEY, MONGODB_URI, MONGODB_DB_NAME, MONGODB_COLLECTION_NAME
import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = 'chatbot_db2'
MONGODB_COLLECTION_NAME = 'doc_chat'

# Initialize OpenAI client
llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4o-mini",
    temperature=0.1,
)

# Initialize embeddings
embeddings = OpenAIEmbeddings(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="text-embedding-3-small"
)

# MongoDB Atlas client
try:
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB_NAME]
    collection = db[MONGODB_COLLECTION_NAME]
    logger.info("MongoDB Atlas connection established")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB Atlas: {e}")
    client = None


def generate_file_hash(file_path: str) -> str:
    """Generate a unique hash for the file to avoid duplicates."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_text_with_page_numbers(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extract text from PDF with page numbers and section detection.
    Returns list of dictionaries with text, page_number, and section info.
    """
    try:
        doc = fitz.open(pdf_path)
        pages_data = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            
            # Clean up the text
            text = text.strip()
            if not text:
                continue
            
            # Basic section detection based on common legal document patterns
            section_markers = [
                "SECTION", "CHAPTER", "ARTICLE", "PART", "TITLE",
                "§", "Article", "Chapter", "Section", "Part"
            ]
            
            is_section_start = any(marker in text[:200] for marker in section_markers)
            
            pages_data.append({
                "text": text,
                "page_number": page_num + 1,
                "is_section_start": is_section_start,
                "char_count": len(text)
            })
        
        doc.close()
        return pages_data
    
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return []


def create_intelligent_chunks(pages_data: List[Dict[str, Any]], 
                            chunk_size: int = 1500, 
                            chunk_overlap: int = 200) -> List[Dict[str, Any]]:
    """
    Create intelligent chunks based on legal document structure.
    Prioritizes section boundaries and maintains context.
    """
    chunks = []
    current_chunk = ""
    current_pages = []
    current_section = ""
    
    for page_data in pages_data:
        text = page_data["text"]
        page_num = page_data["page_number"]
        
        # Detect section headers
        lines = text.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            # Check if this is a section header
            if page_data["is_section_start"] and i < 3:  # First few lines of section start pages
                section_markers = ["SECTION", "CHAPTER", "ARTICLE", "PART", "TITLE", "§"]
                if any(marker in line.upper() for marker in section_markers):
                    # Save current chunk if it exists
                    if current_chunk.strip():
                        chunks.append({
                            "text": current_chunk.strip(),
                            "page_numbers": current_pages.copy(),
                            "section": current_section,
                            "chunk_size": len(current_chunk)
                        })
                    
                    # Start new chunk
                    current_chunk = ""
                    current_pages = []
                    current_section = line
            
            # Add line to current chunk
            current_chunk += line + " "
            if page_num not in current_pages:
                current_pages.append(page_num)
            
            # Check if chunk is getting too large
            if len(current_chunk) > chunk_size:
                # Find a good break point
                sentences = current_chunk.split('. ')
                if len(sentences) > 1:
                    # Keep most sentences, save the last one for next chunk
                    break_point = '. '.join(sentences[:-1]) + '.'
                    remainder = sentences[-1]
                    
                    chunks.append({
                        "text": break_point,
                        "page_numbers": current_pages.copy(),
                        "section": current_section,
                        "chunk_size": len(break_point)
                    })
                    
                    # Start new chunk with remainder
                    current_chunk = remainder + " "
                    # Keep the last page for context
                    current_pages = [current_pages[-1]] if current_pages else []
                else:
                    # If no sentence breaks, just split at word boundary
                    words = current_chunk.split()
                    split_point = len(words) // 2
                    
                    first_half = ' '.join(words[:split_point])
                    second_half = ' '.join(words[split_point:])
                    
                    chunks.append({
                        "text": first_half,
                        "page_numbers": current_pages.copy(),
                        "section": current_section,
                        "chunk_size": len(first_half)
                    })
                    
                    current_chunk = second_half + " "
                    current_pages = [current_pages[-1]] if current_pages else []
    
    # Add the last chunk
    if current_chunk.strip():
        chunks.append({
            "text": current_chunk.strip(),
            "page_numbers": current_pages,
            "section": current_section,
            "chunk_size": len(current_chunk)
        })
    
    return chunks


async def generate_summary(pdf_path: str, filename: str) -> str:
    """Generate a detailed summary of the legal document."""
    try:
        # Extract text for summary generation
        pages_data = extract_text_with_page_numbers(pdf_path)
        
        if not pages_data:
            return "Unable to extract text from the document."
        
        # Combine first few pages for summary (up to 10 pages or 5000 chars)
        summary_text = ""
        for page_data in pages_data[:10]:
            summary_text += page_data["text"] + " "
            if len(summary_text) > 5000:
                break
        
        # Truncate if too long
        if len(summary_text) > 5000:
            summary_text = summary_text[:5000] + "..."
        
        summary_prompt = f"""
        Create a detailed summary of this legal document titled "{filename}".
        
        Document content:
        {summary_text}
        
        Please provide:
        1. Document type and purpose
        2. Key legal topics covered
        3. Main sections and their content
        4. Important legal principles mentioned
        5. Jurisdiction or applicable law (if mentioned)
        6. Key parties, dates, or cases referenced
        
        Keep the summary comprehensive but concise (300-500 words).
        """
        
        chain = llm | StrOutputParser()
        summary = await chain.ainvoke(summary_prompt)
        
        return summary.strip()
    
    except Exception as e:
        logger.error(f"Error generating summary: {e}\n{traceback.format_exc()}")
        return f"Error generating summary for {filename}"


async def process_and_store_pdf(pdf_path: str, filename: str) -> Dict[str, Any]:
    """
    Process a PDF file and store it in MongoDB Atlas vector database.
    Returns processing results and metadata.
    """
    try:
        # Generate file hash to check for duplicates
        file_hash = generate_file_hash(pdf_path)
        
        # Check if file already exists
        existing_doc = collection.find_one({"metadata.file_hash": file_hash})
        if existing_doc:
            logger.info(f"File {filename} already exists in database")
            return {
                "success": True,
                "message": "File already exists in database",
                "file_id": str(existing_doc["_id"]),
                "chunks_count": 0
            }
        
        # Extract text with page numbers
        logger.info(f"Extracting text from {filename}")
        pages_data = extract_text_with_page_numbers(pdf_path)
        
        if not pages_data:
            return {
                "success": False,
                "message": "No text could be extracted from the PDF",
                "file_id": None,
                "chunks_count": 0
            }
        
        # Generate summary
        logger.info(f"Generating summary for {filename}")
        summary = await generate_summary(pdf_path, filename)
        
        # Create intelligent chunks
        logger.info(f"Creating chunks for {filename}")
        chunks_data = create_intelligent_chunks(pages_data)
        
        # Prepare documents for vector storage
        documents = []
        for i, chunk_data in enumerate(chunks_data):
            doc = Document(
                page_content=chunk_data["text"],
                metadata={
                    "filename": filename,
                    "file_hash": file_hash,
                    "chunk_index": i,
                    "page_numbers": chunk_data["page_numbers"],
                    "section": chunk_data["section"],
                    "chunk_size": chunk_data["chunk_size"],
                    "total_chunks": len(chunks_data),
                    "upload_date": datetime.now(),
                    "summary": summary
                }
            )
            documents.append(doc)
        
        # Store in MongoDB Atlas Vector Search
        logger.info(f"Storing {len(documents)} chunks in vector database")
        vector_store = MongoDBAtlasVectorSearch.from_documents(
            documents=documents,
            embedding=embeddings,
            collection=collection,
            index_name="vector_index"
        )
        
        # Store summary and metadata separately
        summary_doc = {
            "filename": filename,
            "file_hash": file_hash,
            "summary": summary,
            "total_pages": len(pages_data),
            "total_chunks": len(chunks_data),
            "upload_date": datetime.now(),
            "file_size": os.path.getsize(pdf_path),
            "processing_status": "completed"
        }
        
        summary_result = db.document_summaries.insert_one(summary_doc)
        
        logger.info(f"Successfully processed {filename}: {len(chunks_data)} chunks created")
        
        return {
            "success": True,
            "message": f"Successfully processed {filename}",
            "file_id": str(summary_result.inserted_id),
            "chunks_count": len(chunks_data),
            "summary": summary
        }
    
    except Exception as e:
        logger.error(f"Error processing PDF {filename}: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "message": f"Error processing PDF: {str(e)}",
            "file_id": None,
            "chunks_count": 0
        }


async def query_documents(question: str, 
                         filename: Optional[str] = None,
                         top_k: int = 5) -> Dict[str, Any]:
    """
    Query the vector database and return relevant document chunks with sources.
    """
    try:
        # Create vector store instance
        vector_store = MongoDBAtlasVectorSearch(
            collection=collection,
            embedding=embeddings,
            index_name="vector_index"
        )
        
        # Build search filter
        search_filter = {}
        if filename:
            search_filter["metadata.filename"] = filename
        
        # Perform similarity search
        if search_filter:
            docs = vector_store.similarity_search_with_score(
                query=question,
                k=top_k,
                filter=search_filter
            )
        else:
            docs = vector_store.similarity_search_with_score(
                query=question,
                k=top_k
            )
        
        if not docs:
            return {
                "success": False,
                "message": "No relevant documents found",
                "answer": "I couldn't find relevant information in the documents.",
                "sources": []
            }
        
        # Extract relevant chunks
        relevant_chunks = []
        sources = []
        
        for doc, score in docs:
            chunk_info = {
                "text": doc.page_content,
                "filename": doc.metadata.get("filename", "Unknown"),
                "page_numbers": doc.metadata.get("page_numbers", []),
                "section": doc.metadata.get("section", ""),
                "relevance_score": score
            }
            relevant_chunks.append(chunk_info)
            
            # Prepare source information
            source_info = {
                "filename": doc.metadata.get("filename", "Unknown"),
                "pages": doc.metadata.get("page_numbers", []),
                "section": doc.metadata.get("section", ""),
                "relevance_score": round(score, 3)
            }
            sources.append(source_info)
        
        # Generate answer using retrieved context
        context = "\n\n".join([chunk["text"] for chunk in relevant_chunks])
        
        answer_prompt = f"""
        Based on the following legal document excerpts, answer the user's question comprehensively.
        
        Question: {question}
        
        Document Context:
        {context}
        
        Instructions:
        1. Provide a detailed answer based solely on the provided context
        2. If the context doesn't contain enough information, clearly state this
        3. Reference specific sections or pages when relevant
        4. Maintain legal accuracy and precision
        5. If multiple documents are referenced, distinguish between them
        
        Answer:
        """
        
        chain = llm | StrOutputParser()
        answer = await chain.ainvoke(answer_prompt)
        
        return {
            "success": True,
            "message": "Query processed successfully",
            "answer": answer.strip(),
            "sources": sources,
            "relevant_chunks": relevant_chunks
        }
    
    except Exception as e:
        logger.error(f"Error querying documents: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "message": f"Error querying documents: {str(e)}",
            "answer": "An error occurred while processing your query.",
            "sources": []
        }


async def get_document_summary(filename: str) -> Dict[str, Any]:
    """Retrieve the summary of a specific document."""
    try:
        summary_doc = db.document_summaries.find_one({"filename": filename})
        
        if not summary_doc:
            return {
                "success": False,
                "message": "Document not found",
                "summary": None
            }
        
        return {
            "success": True,
            "message": "Summary retrieved successfully",
            "summary": summary_doc["summary"],
            "metadata": {
                "filename": summary_doc["filename"],
                "total_pages": summary_doc["total_pages"],
                "total_chunks": summary_doc["total_chunks"],
                "upload_date": summary_doc["upload_date"],
                "file_size": summary_doc["file_size"]
            }
        }
    
    except Exception as e:
        logger.error(f"Error retrieving summary: {e}")
        return {
            "success": False,
            "message": f"Error retrieving summary: {str(e)}",
            "summary": None
        }


async def list_documents() -> List[Dict[str, Any]]:
    """List all documents in the database."""
    try:
        documents = list(db.document_summaries.find(
            {},
            {
                "filename": 1,
                "total_pages": 1,
                "total_chunks": 1,
                "upload_date": 1,
                "file_size": 1
            }
        ))
        
        return [
            {
                "filename": doc["filename"],
                "total_pages": doc["total_pages"],
                "total_chunks": doc["total_chunks"],
                "upload_date": doc["upload_date"],
                "file_size": doc["file_size"]
            }
            for doc in documents
        ]
    
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        return []


async def delete_document(filename: str) -> Dict[str, Any]:
    """Delete a document and all its chunks from the database."""
    try:
        # Delete from vector collection
        vector_result = collection.delete_many({"metadata.filename": filename})
        
        # Delete from summaries collection
        summary_result = db.document_summaries.delete_one({"filename": filename})
        
        if vector_result.deleted_count > 0 or summary_result.deleted_count > 0:
            return {
                "success": True,
                "message": f"Document {filename} deleted successfully",
                "chunks_deleted": vector_result.deleted_count
            }
        else:
            return {
                "success": False,
                "message": "Document not found",
                "chunks_deleted": 0
            }
    
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        return {
            "success": False,
            "message": f"Error deleting document: {str(e)}",
            "chunks_deleted": 0
        }


# Example usage and testing
async def main():
    """Example usage of the document processing system."""
    
    # Example 1: Process a PDF
    pdf_path = "sample_legal_document.pdf"
    if os.path.exists(pdf_path):
        result = await process_and_store_pdf(pdf_path, "C:\\Users\\akash\\OneDrive\\Documents\\projects\\ChatBot\\backend\\docs\\doc1.pdf")
        print("Processing result:", result)
    
    # Example 2: Query documents
    query_result = await query_documents("What are the key provisions regarding contract formation?")
    print("Query result:", query_result)
    
    # Example 3: Get document summary
    summary_result = await get_document_summary("C:\\Users\\akash\\OneDrive\\Documents\\projects\\ChatBot\\backend\\docs\\doc1.pdf")
    print("Summary result:", summary_result)
    
    # Example 4: List all documents
    documents = await list_documents()
    print("All documents:", documents)


if __name__ == "__main__":
    asyncio.run(main())