from pymongo import MongoClient
from datetime import datetime
from config.config import MONGODB_URI
import json
import asyncio
from loguru import logger
from typing import Optional, List, Dict, Any
import numpy as np


from langchain_openai import OpenAIEmbeddings
from config.config import OPENAI_API_KEY

embeddings_model = OpenAIEmbeddings(
    api_key=OPENAI_API_KEY, model="text-embedding-3-small"
)

client = MongoClient(MONGODB_URI)
db = client["chatbot_db2"]
conversations_collection = db["conversations"]
sessions_collection = db["sessions"]
files_collection = db["files"]  # New collection for file metadata
embeddings_collection = db["embeddings"]  # New collection for embeddings

# Create indexes for better performance
try:
    embeddings_collection.create_index("file_id")
    embeddings_collection.create_index("section_index")
    embeddings_collection.create_index("metadata.document_type")
    embeddings_collection.create_index("metadata.hierarchy_level")
    embeddings_collection.create_index("metadata.contains_definitions")
    embeddings_collection.create_index("metadata.contains_obligations")
    embeddings_collection.create_index("metadata.contains_dates")
    embeddings_collection.create_index(
        [("file_id", 1), ("metadata.hierarchy_level", 1)]
    )
    files_collection.create_index("file_id")
    files_collection.create_index("upload_date")
    logger.info("Enhanced database indexes created successfully")
except Exception as e:
    logger.warning(f"Index creation warning: {e}")


def add_session(session_id: str, title: str) -> str:
    sessions_collection.insert_one(
        {
            "session_id": session_id,
            "title": title,
            "created_at": datetime.utcnow().isoformat(),
        }
    )
    return title


def add_message(session_id: str, user_message: str, ai_message: str):
    timestamp = datetime.utcnow().isoformat()
    logger.info(f"Adding message to session {session_id} at {timestamp}")

    conversations_collection.insert_one(
        {
            "session_id": session_id,
            "role": "user",
            "message": user_message,
            "created_at": timestamp,
        }
    )
    conversations_collection.insert_one(
        {
            "session_id": session_id,
            "role": "ai",
            "message": ai_message,
            "created_at": timestamp,
        }
    )

    return {"status": "success", "message": "Message added successfully."}


def fetch_all_conversations(session_id: str):
    messages = list(
        conversations_collection.find({"session_id": session_id}).sort("created_at", 1)
    )
    result = []
    for msg in messages:
        result.append(
            {
                "role": msg.get("role"),
                "message": msg.get("message"),
                "created_at": msg.get("created_at"),
            }
        )
    return result


def get_all_sessions_sorted() -> list:
    sessions = list(
        sessions_collection.find(
            {}, {"_id": 0, "session_id": 1, "title": 1, "created_at": 1}
        ).sort("created_at", -1)
    )
    return sessions


import re
from typing import List, Dict, Any, Optional
from datetime import datetime


def process_query_search(query: str, file_id: str = None) -> Dict[str, Any]:
    """
    Main entry point that routes queries to appropriate functions
    """
    query_lower = query.lower()
    
    # Document info queries
    if any(word in query_lower for word in ['pages', 'page count', 'total pages']):
        logger.info(f"processing for pages, page count and total pages")
        return get_document_info(file_id, info_type='pages')

    elif any(word in query_lower for word in ['sections', 'section count', 'total sections']):
        logger.info(f"processing for sections, section count and total sections")
        return get_document_info(file_id, info_type='sections')
    
    elif any(word in query_lower for word in ['structure', 'outline', 'hierarchy']):
        logger.info(f"processing for structure, outline and hierarchy")
        return get_document_structure(file_id)
    
    # Section-specific queries
    elif re.search(r'section\s+(\d+)', query_lower):
        logger.info(f"processing for section-specific queries")
        section_num = re.search(r'section\s+(\d+)', query_lower).group(1)
        if 'summar' in query_lower:
            return get_section_summary(file_id, int(section_num))
        else:
            return get_section_content(file_id, int(section_num))
    
    # Date extraction queries

    elif any(word in query_lower for word in ['dates', 'date', 'deadline', 'timeline']):
        logger.info(f"processing for dates, date, deadline and timeline")
        return extract_dates(file_id)
    
    # Default to semantic search
    else:
        logger.info(f"processing for semantic search")
        return semantic_search(query, file_id)


def get_document_info(file_id: str, info_type: str) -> Dict[str, Any]:
    """Get basic document information"""
    try:
        if info_type == 'pages':
            # Get max page_end value
            pipeline = [
                {"$match": {"file_id": file_id}},
                {"$group": {"_id": None, "max_page": {"$max": "$page_end"}}}
            ]
            result = list(embeddings_collection.aggregate(pipeline))
            page_count = result[0]["max_page"] if result else 0
            
            return {
                "type": "document_info",
                "query": f"Total pages in document",
                "answer": f"The document has {page_count} pages.",
                "data": {"page_count": page_count}
            }
        
        elif info_type == 'sections':
            count = embeddings_collection.count_documents({"file_id": file_id})
            return {
                "type": "document_info",
                "query": f"Total sections in document",
                "answer": f"The document has {count} sections.",
                "data": {"section_count": count}
            }
            
    except Exception as e:
        return {"type": "error", "message": str(e)}


def get_section_content(file_id: str, section_num: int) -> Dict[str, Any]:
    """Get content of a specific section"""
    try:
        section = embeddings_collection.find_one(
            {"file_id": file_id, "section_index": section_num},
            {"_id": 0, "embedding": 0}
        )
        
        if not section:
            return {
                "type": "section_content",
                "query": f"Section {section_num}",
                "answer": f"Section {section_num} not found.",
                "data": None
            }
        
        return {
            "type": "section_content",
            "query": f"Section {section_num}",
            "answer": f"Section {section_num}: {section['section_title']}\n\n{section['content'][:500]}...",
            "data": section
        }
        
    except Exception as e:
        return {"type": "error", "message": str(e)}


def get_section_summary(file_id: str, section_num: int) -> Dict[str, Any]:
    """Get summary of a specific section"""
    try:
        section = embeddings_collection.find_one(
            {"file_id": file_id, "section_index": section_num},
            {"_id": 0, "embedding": 0}
        )
        
        if not section:
            return {
                "type": "section_summary",
                "query": f"Summary of Section {section_num}",
                "answer": f"Section {section_num} not found.",
                "data": None
            }
        
        # Simple extractive summary (first 2 sentences)
        content = section['content']
        sentences = content.split('. ')
        summary = '. '.join(sentences[:2]) + '.' if len(sentences) > 1 else content[:200]
        
        return {
            "type": "section_summary",
            "query": f"Summary of Section {section_num}",
            "answer": f"Summary of Section {section_num} ({section['section_title']}):\n\n{summary}",
            "data": {"section": section, "summary": summary}
        }
        
    except Exception as e:
        return {"type": "error", "message": str(e)}


def extract_dates(file_id: str) -> Dict[str, Any]:
    """Extract important dates from document"""
    try:
        # Get all sections
        sections = list(embeddings_collection.find(
            {"file_id": file_id},
            {"content": 1, "section_title": 1, "section_index": 1, "_id": 0}
        ))
        
        date_patterns = [
            r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}',  # DD/MM/YYYY or DD-MM-YYYY
            r'\d{4}[-/]\d{1,2}[-/]\d{1,2}',    # YYYY/MM/DD or YYYY-MM-DD
            r'\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b'
        ]
        
        found_dates = []
        for section in sections:
            content = section['content']
            for pattern in date_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    found_dates.append({
                        "date": match,
                        "section": section['section_title'],
                        "section_index": section['section_index']
                    })
        
        # Remove duplicates
        unique_dates = []
        seen = set()
        for date_info in found_dates:
            if date_info['date'] not in seen:
                unique_dates.append(date_info)
                seen.add(date_info['date'])
        
        answer = "Important dates found in the document:\n\n"
        for date_info in unique_dates[:10]:  # Limit to first 10 dates
            answer += f"• {date_info['date']} (Section: {date_info['section']})\n"
        
        return {
            "type": "date_extraction",
            "query": "Important dates in document",
            "answer": answer if unique_dates else "No dates found in the document.",
            "data": {"dates": unique_dates}
        }
        
    except Exception as e:
        return {"type": "error", "message": str(e)}


def semantic_search(query: str, file_id: str = None) -> Dict[str, Any]:
   """Perform semantic search using existing function"""
   try:
       # Generate query embedding
       query_embedding = embeddings_model.embed_query(query)
       
       # Use your existing search_similar_sections function
       results = search_similar_sections(
           query_embedding=query_embedding,
           file_id=file_id,
           limit=5
       )
       
       if not results:
           return {
               "type": "semantic_search",
               "query": query,
               "answer": "No relevant content found for your query.",
               "data": {"results": []}
           }
       
       # Format answer
       answer = f"Found {len(results)} relevant sections for '{query}':\n\n"
       for i, result in enumerate(results, 1):
           answer += f"{i}. {result['section_title']}\n"
           answer += f"   {result['content'][:200]}...\n\n"
       
       return {
           "type": "semantic_search",
           "query": query,
           "answer": answer,
           "data": {"results": results}
       }
       
   except Exception as e:
       return {"type": "error", "message": str(e)}

# Keep your existing functions for backward compatibility
def search_similar_sections(query_embedding, file_id=None, limit=5):
    """Searches for sections similar to the query embedding."""

    # Define the core $vectorSearch stage
    vector_search_stage = {
        "$vectorSearch": {
            "index": "vector_index",
            "path": "embedding",
            "queryVector": query_embedding,
            "numCandidates": limit * 10, # It's good practice to have more candidates than the limit
            "limit": limit,
        }
    }

    # -- THIS IS THE FIX --
    # If a file_id is provided, add it as a pre-filter inside the $vectorSearch stage.
    if file_id:
        vector_search_stage["$vectorSearch"]["filter"] = {
            "file_id": {"$eq": file_id}
        }

    # The pipeline starts with the correctly configured vector search
    pipeline = [
        vector_search_stage,
        {
            "$project": {
                "_id": 0, # Exclude the _id field
                "content": 1,
                "file_id": 1,
                "section_title": 1,
                "score": {"$meta": "vectorSearchScore"}
            }
        }
        # The $sort is redundant since $vectorSearch already returns by score.
    ]

    results = list(embeddings_collection.aggregate(pipeline))

    # You can simplify the file name lookup or remove if not needed for the test
    for result in results:
        file_doc = files_collection.find_one({"file_id": result["file_id"]}, {"filename": 1, "_id": 0})
        result["filename"] = file_doc["filename"] if file_doc else "Unknown"

    return results


def get_document_structure(file_id: str) -> Dict[str, Any]:
    """Get hierarchical structure of a legal document"""
    try:
        pipeline = [
            {"$match": {"file_id": file_id}},
            {
                "$group": {
                    "_id": "$metadata.hierarchy_level",
                    "sections": {
                        "$push": {
                            "title": "$section_title",
                            "index": "$section_index",
                            "token_count": "$token_count",
                        }
                    },
                }
            },
            {"$sort": {"_id": 1}},
        ]

        result = list(embeddings_collection.aggregate(pipeline))
        
        if not result:
            return {
                "type": "document_structure", 
                "query": "Document structure",
                "answer": "No structure information found.",
                "data": {}
            }

        structure = {"hierarchy": {}, "total_sections": 0}
        answer = "Document Structure:\n\n"

        for level_data in result:
            level = level_data["_id"] or 0
            sections = level_data["sections"]
            structure["hierarchy"][f"level_{level}"] = sections
            structure["total_sections"] += len(sections)
            
            answer += f"Level {level}: {len(sections)} sections\n"
            for section in sections[:5]:  # Show first 5 sections per level
                answer += f"  • {section['title']}\n"
            if len(sections) > 5:
                answer += f"  ... and {len(sections) - 5} more sections\n"
            answer += "\n"

        return {
            "type": "document_structure",
            "query": "Document structure",
            "answer": answer,
            "data": structure
        }

    except Exception as e:
        return {"type": "error", "message": str(e)}


# Keep other existing functions...
def search_by_section_type(file_id: str, section_types: List[str]) -> List[Dict]:
    """Search for specific types of legal sections"""
    try:
        query = {"file_id": file_id}
        pattern = "|".join(section_types)
        query["section_title"] = {"$regex": pattern, "$options": "i"}

        sections = list(
            embeddings_collection.find(query, {"_id": 0, "embedding": 0}).sort(
                "section_index", 1
            )
        )
        return sections

    except Exception as e:
        logger.error(f"Error searching by section type: {e}")
        return []


def get_file_sections(file_id: str) -> List[Dict]:
    """Get all sections for a specific file"""
    try:
        sections = list(
            embeddings_collection.find(
                {"file_id": file_id},
                {"_id": 0, "embedding": 0},
            ).sort("section_index", 1)
        )
        return sections
    except Exception as e:
        logger.error(f"Error fetching file sections: {e}")
        return []


def get_file_metadata(file_id: str) -> Optional[Dict]:
    """Get file metadata"""
    try:
        return files_collection.find_one({"file_id": file_id}, {"_id": 0})
    except Exception as e:
        logger.error(f"Error fetching file metadata: {e}")
        return None


def update_file_status(file_id: str, status: str):
    """Update file processing status"""
    try:
        files_collection.update_one(
            {"file_id": file_id},
            {"$set": {"status": status, "updated_at": datetime.utcnow().isoformat()}},
        )
    except Exception as e:
        logger.error(f"Error updating file status: {e}")


if __name__ == "__main__":
    # Example usage
    result = process_query_search("How many pages are in this document?", "dbd4cc47-3d3f-4df8-a662-2c694af00928")
    print(result["answer"])
    pass