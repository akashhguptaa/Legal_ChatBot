from pymongo import MongoClient
from datetime import datetime
from config.config import MONGODB_URI
import json
import asyncio
from loguru import logger
from typing import Optional, List, Dict, Any
import numpy as np

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
    embeddings_collection.create_index([("file_id", 1), ("metadata.hierarchy_level", 1)])
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
            "created_at": datetime.utcnow().isoformat()
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
    
def search_similar_sections(
    query_embedding: List[float], 
    file_id: str = None, 
    limit: int = 5,
    filters: Dict[str, Any] = None
) -> List[Dict]:
    """
    Enhanced search with metadata filtering for better legal document retrieval
    """
    try:
        # Build base query
        query = {}
        if file_id:
            query["file_id"] = file_id
        
        # Add metadata filters
        if filters:
            for key, value in filters.items():
                if key.startswith('metadata.'):
                    query[key] = value
                elif key == 'hierarchy_level':
                    query["metadata.hierarchy_level"] = value
                elif key == 'contains_definitions':
                    query["metadata.contains_definitions"] = True
                elif key == 'contains_obligations':
                    query["metadata.contains_obligations"] = True
                elif key == 'contains_dates':
                    query["metadata.contains_dates"] = True
                elif key == 'section_type':
                    # Search in section titles
                    query["section_title"] = {"$regex": value, "$options": "i"}
        
        # Get embeddings with filters
        embeddings_docs = list(embeddings_collection.find(query, {"_id": 0}))
        
        if not embeddings_docs:
            return []
        
        # Calculate cosine similarity with prioritization
        similarities = []
        for doc in embeddings_docs:
            embedding = doc.get("embedding", [])
            if embedding:
                # Calculate base similarity
                similarity = np.dot(query_embedding, embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(embedding)
                )
                
                # Apply metadata-based boosting
                metadata = doc.get("metadata", {})
                boost = 1.0
                
                # Boost definition sections for definition queries
                if "definition" in str(filters).lower() and metadata.get("contains_definitions"):
                    boost += 0.1
                
                # Boost obligation sections for compliance queries
                if any(word in str(filters).lower() for word in ["shall", "must", "obligation"]) and metadata.get("contains_obligations"):
                    boost += 0.1
                
                # Boost higher hierarchy sections for general queries
                hierarchy_level = metadata.get("hierarchy_level", 0)
                if hierarchy_level <= 2:  # Top-level sections
                    boost += 0.05
                
                # Penalize split sections slightly to prefer complete sections
                if doc.get("is_split"):
                    boost -= 0.02
                
                doc["similarity"] = similarity * boost
                doc["boost_applied"] = boost
                similarities.append(doc)
        
        # Sort by boosted similarity
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        
        # Post-process to ensure context continuity
        final_results = []
        added_sections = set()
        
        for doc in similarities[:limit * 2]:  # Get more candidates
            section_key = f"{doc['file_id']}_{doc['section_index']}"
            
            if section_key not in added_sections:
                # Add main section
                final_results.append(doc)
                added_sections.add(section_key)
                
                # If this is a split section, try to add adjacent parts
                if doc.get("is_split") and len(final_results) < limit:
                    part_num = doc.get("part_number", 1)
                    total_parts = doc.get("total_parts", 1)
                    
                    # Try to add next part if available
                    if part_num < total_parts:
                        next_part = embeddings_collection.find_one({
                            "file_id": doc["file_id"],
                            "section_title": {"$regex": f".*Part {part_num + 1}.*"},
                            "is_split": True
                        })
                        if next_part and f"{next_part['file_id']}_{next_part['section_index']}" not in added_sections:
                            next_part["similarity"] = doc["similarity"] * 0.9  # Slightly lower score
                            final_results.append(next_part)
                            added_sections.add(f"{next_part['file_id']}_{next_part['section_index']}")
                
                if len(final_results) >= limit:
                    break
        
        return final_results[:limit]
        
    except Exception as e:
        logger.error(f"Error searching similar sections: {e}")
        return []

def search_by_section_type(file_id: str, section_types: List[str]) -> List[Dict]:
    """Search for specific types of legal sections"""
    try:
        query = {"file_id": file_id}
        
        # Create regex pattern for section types
        pattern = "|".join(section_types)
        query["section_title"] = {"$regex": pattern, "$options": "i"}
        
        sections = list(
            embeddings_collection.find(
                query, 
                {"_id": 0, "embedding": 0}
            ).sort("section_index", 1)
        )
        
        return sections
        
    except Exception as e:
        logger.error(f"Error searching by section type: {e}")
        return []

def get_document_structure(file_id: str) -> Dict[str, Any]:
    """Get hierarchical structure of a legal document"""
    try:
        pipeline = [
            {"$match": {"file_id": file_id}},
            {"$group": {
                "_id": "$metadata.hierarchy_level",
                "sections": {"$push": {
                    "title": "$section_title",
                    "index": "$section_index",
                    "token_count": "$token_count",
                    "has_subsections": "$metadata.has_subsections",
                    "contains_definitions": "$metadata.contains_definitions",
                    "contains_obligations": "$metadata.contains_obligations"
                }}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        result = list(embeddings_collection.aggregate(pipeline))
        
        structure = {
            "file_id": file_id,
            "hierarchy": {},
            "total_sections": 0,
            "definition_sections": 0,
            "obligation_sections": 0
        }
        
        for level_data in result:
            level = level_data["_id"]
            sections = level_data["sections"]
            
            structure["hierarchy"][f"level_{level}"] = sections
            structure["total_sections"] += len(sections)
            structure["definition_sections"] += sum(1 for s in sections if s.get("contains_definitions"))
            structure["obligation_sections"] += sum(1 for s in sections if s.get("contains_obligations"))
        
        return structure
        
    except Exception as e:
        logger.error(f"Error getting document structure: {e}")
        return {"error": str(e)}

def get_file_sections(file_id: str) -> List[Dict]:
    """Get all sections for a specific file"""
    try:
        sections = list(
            embeddings_collection.find(
                {"file_id": file_id}, 
                {"_id": 0, "embedding": 0}  # Exclude embeddings for performance
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
            {"$set": {"status": status, "updated_at": datetime.utcnow().isoformat()}}
        )
    except Exception as e:
        logger.error(f"Error updating file status: {e}")


if __name__ == "__main__":
    pass