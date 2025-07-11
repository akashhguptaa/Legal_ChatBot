import os
import traceback
from typing import List, Dict, Any, Optional
from datetime import datetime
from langchain_core.documents import Document
from loguru import logger
from dotenv import load_dotenv
from utils.create_vectorStore import (
    create_vector_store,
    query_vector_store,
    delete_vector_store_by_filename,
)
from utils.manage_chunking import (
    extract_text_with_page_numbers,
    create_intelligent_chunks,
    generate_file_hash,
)
from pymongo import MongoClient
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = "chatbot_db2"

try:
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB_NAME]
    logger.info("MongoDB Atlas connection established (doc_chat)")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB Atlas: {e}")
    client = None

llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4o-mini",
    temperature=0.1,
)


async def process_and_store_pdf(pdf_path: str, filename: str) -> dict:
    try:
        file_hash = generate_file_hash(pdf_path)
        # Check if file already exists
        existing_doc = db.document_summaries.find_one({"file_hash": file_hash})
        if existing_doc:
            logger.info(f"File {filename} already exists in database")
            return {
                "success": True,
                "message": "File already exists in database",
                "file_id": str(existing_doc.get("_id", "")),
                "chunks_count": 0,
            }
        logger.info(f"Extracting text from {filename}")
        pages_data = extract_text_with_page_numbers(pdf_path)
        if not pages_data:
            return {
                "success": False,
                "message": "No text could be extracted from the PDF",
                "file_id": None,
                "chunks_count": 0,
            }
        logger.info(f"Generating summary for {filename}")
        summary = await generate_summary(pdf_path, filename)
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
                    "summary": summary,
                },
            )
            documents.append(doc)
        logger.info(f"Storing {len(documents)} chunks in vector database (batched)")
        chunks_stored = create_vector_store(documents)
        # Store summary and metadata separately
        summary_doc = {
            "filename": filename,
            "file_hash": file_hash,
            "summary": summary,
            "total_pages": len(pages_data),
            "total_chunks": len(chunks_data),
            "upload_date": datetime.now(),
            "file_size": os.path.getsize(pdf_path),
            "processing_status": "completed",
        }
        summary_result = db.document_summaries.insert_one(summary_doc)
        logger.info(
            f"Successfully processed {filename}: {len(chunks_data)} chunks created"
        )
        return {
            "success": True,
            "message": f"Successfully processed {filename}",
            "file_id": str(summary_result.inserted_id),
            "chunks_count": len(chunks_data),
            "summary": summary,
        }
    except Exception as e:
        logger.error(f"Error processing PDF {filename}: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "message": f"Error processing PDF: {str(e)}",
            "file_id": None,
            "chunks_count": 0,
        }


async def generate_summary(pdf_path: str, filename: str) -> str:
    try:
        pages_data = extract_text_with_page_numbers(pdf_path)
        if not pages_data:
            return "Unable to extract text from the document."
        summary_text = ""
        for page_data in pages_data[:10]:
            summary_text += page_data["text"] + " "
            if len(summary_text) > 5000:
                break
        if len(summary_text) > 5000:
            summary_text = summary_text[:5000] + "..."
        summary_prompt = f"""
        Create a detailed summary of this legal document titled \"{filename}\".
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


async def query_documents(
    question: str, filename: Optional[str] = None, top_k: int = 5
) -> Dict[str, Any]:
    try:
        docs = query_vector_store(question, top_k=top_k, filename=filename)
        if not docs:
            return {
                "success": False,
                "message": "No relevant documents found",
                "answer": "I couldn't find relevant information in the documents.",
                "sources": [],
            }
        relevant_chunks = []
        sources = []
        for doc in docs:
            chunk_info = {
                "text": doc["text"],
                "filename": doc["metadata"].get("filename", "Unknown"),
                "page_numbers": doc["metadata"].get("page_numbers", []),
                "section": doc["metadata"].get("section", ""),
                "relevance_score": doc["relevance_score"],
            }
            relevant_chunks.append(chunk_info)
            source_info = {
                "filename": doc["metadata"].get("filename", "Unknown"),
                "pages": doc["metadata"].get("page_numbers", []),
                "section": doc["metadata"].get("section", ""),
                "relevance_score": round(doc["relevance_score"], 3),
            }
            sources.append(source_info)
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
            "relevant_chunks": relevant_chunks,
        }
    except Exception as e:
        logger.error(f"Error querying documents: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "message": f"Error querying documents: {str(e)}",
            "answer": "An error occurred while processing your query.",
            "sources": [],
        }


async def get_document_summary(filename: str) -> Dict[str, Any]:
    try:
        summary_doc = db.document_summaries.find_one({"filename": filename})
        if not summary_doc:
            return {"success": False, "message": "Document not found", "summary": None}
        return {
            "success": True,
            "message": "Summary retrieved successfully",
            "summary": summary_doc["summary"],
            "metadata": {
                "filename": summary_doc["filename"],
                "total_pages": summary_doc["total_pages"],
                "total_chunks": summary_doc["total_chunks"],
                "upload_date": summary_doc["upload_date"],
                "file_size": summary_doc["file_size"],
            },
        }
    except Exception as e:
        logger.error(f"Error retrieving summary: {e}")
        return {
            "success": False,
            "message": f"Error retrieving summary: {str(e)}",
            "summary": None,
        }


async def list_documents() -> List[Dict[str, Any]]:
    try:
        documents = list(
            db.document_summaries.find(
                {},
                {
                    "filename": 1,
                    "total_pages": 1,
                    "total_chunks": 1,
                    "upload_date": 1,
                    "file_size": 1,
                },
            )
        )
        return [
            {
                "filename": doc["filename"],
                "total_pages": doc["total_pages"],
                "total_chunks": doc["total_chunks"],
                "upload_date": doc["upload_date"],
                "file_size": doc["file_size"],
            }
            for doc in documents
        ]
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        return []


async def delete_document(filename: str) -> Dict[str, Any]:
    try:
        chunks_deleted = delete_vector_store_by_filename(filename)
        summary_result = db.document_summaries.delete_one({"filename": filename})
        if chunks_deleted > 0 or summary_result.deleted_count > 0:
            return {
                "success": True,
                "message": f"Document {filename} deleted successfully",
                "chunks_deleted": chunks_deleted,
            }
        else:
            return {
                "success": False,
                "message": "Document not found",
                "chunks_deleted": 0,
            }
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        return {
            "success": False,
            "message": f"Error deleting document: {str(e)}",
            "chunks_deleted": 0,
        }


# Example usage and testing
async def main():
    """Example usage of the document processing system."""

    # Example 1: Process a PDF
    pdf_path = "C:\\Users\\akash\\OneDrive\\Documents\\projects\\ChatBot\\backend\\docs\\doc1.pdf"
    if os.path.exists(pdf_path):
        result = await generate_summary(
            pdf_path,
            "C:\\Users\\akash\\OneDrive\\Documents\\projects\\ChatBot\\backend\\docs\\doc1.pdf",
        )
        print("Processing result:", result)

    # Example 2: Query documents
    query_result = await query_documents(
        "What are the key provisions regarding contract formation?"
    )
    print("Query result:", query_result)

    # Example 3: Get document summary
    summary_result = await get_document_summary(
        "C:\\Users\\akash\\OneDrive\\Documents\\projects\\ChatBot\\backend\\docs\\doc1.pdf"
    )
    print("Summary result:", summary_result)

    # Example 4: List all documents
    documents = await list_documents()
    print("All documents:", documents)


if __name__ == "__main__":
    # The main function now only calls generate_summary and query_documents.
    # The chunking utilities are no longer imported directly here.
    # If summary generation or query processing needs chunking, it should be
    # handled within these functions or by importing the chunking utilities
    # directly if they are intended to be used for other purposes.
    # For now, the example usage reflects the new structure.
    pass
