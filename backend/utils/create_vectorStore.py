import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from langchain_openai import OpenAIEmbeddings
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_core.documents import Document
from pymongo import MongoClient
from loguru import logger

# Load environment variables
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = "chatbot_db2"
MONGODB_COLLECTION_NAME = "doc_chat"

# Initialize embeddings
embeddings = OpenAIEmbeddings(
    api_key=os.getenv("OPENAI_API_KEY"), model="text-embedding-3-small"
)

# MongoDB Atlas client
try:
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB_NAME]
    collection = db[MONGODB_COLLECTION_NAME]
    logger.info("MongoDB Atlas connection established (vector store)")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB Atlas: {e}")
    client = None

BATCH_SIZE = 50


def create_vector_store(
    documents: List[Document], index_name: str = "vector_index"
) -> int:
    """
    Store documents in MongoDB Atlas Vector Search in batches.
    Returns the number of chunks stored.
    """
    total_chunks = 0
    for i in range(0, len(documents), BATCH_SIZE):
        batch = documents[i : i + BATCH_SIZE]
        MongoDBAtlasVectorSearch.from_documents(
            documents=batch,
            embedding=embeddings,
            collection=collection,
            index_name=index_name,
        )
        total_chunks += len(batch)
        logger.info(f"Stored batch {i//BATCH_SIZE+1}: {len(batch)} chunks")
    return total_chunks


def query_vector_store(
    query: str,
    top_k: int = 5,
    filename: Optional[str] = None,
    index_name: str = "vector_index",
) -> List[Dict[str, Any]]:
    """
    Query the vector store and return relevant document chunks with metadata.
    """
    vector_store = MongoDBAtlasVectorSearch(
        collection=collection, embedding=embeddings, index_name=index_name
    )
    search_filter = {}
    if filename:
        search_filter["metadata.filename"] = filename
    if search_filter:
        docs = vector_store.similarity_search_with_score(
            query=query, k=top_k, filter=search_filter
        )
    else:
        docs = vector_store.similarity_search_with_score(query=query, k=top_k)
    results = []
    for doc, score in docs:
        results.append(
            {
                "text": doc.page_content,
                "metadata": doc.metadata,
                "relevance_score": score,
            }
        )
    return results


def delete_vector_store_by_filename(filename: str) -> int:
    """
    Delete all vector store chunks for a given filename.
    Returns the number of deleted chunks.
    """
    result = collection.delete_many({"metadata.filename": filename})
    return result.deleted_count
