from pymongo import MongoClient
from datetime import datetime
from config.config import MONGODB_URI
from loguru import logger
from typing import Optional, List, Dict, Any

# MongoDB setup
client = MongoClient(MONGODB_URI)
db = client["chatbot_db2"]
conversations_collection = db["conversations"]
sessions_collection = db["sessions"]
files_collection = db["files"]

# Create indexes for better performance
try:
    files_collection.create_index("file_id")
    files_collection.create_index("upload_date")
    sessions_collection.create_index("session_id")
    sessions_collection.create_index("created_at")
    conversations_collection.create_index("session_id")
    conversations_collection.create_index("created_at")
    logger.info("Database indexes created successfully")
except Exception as e:
    logger.warning(f"Index creation warning: {e}")

def add_session(session_id: str, title: str) -> str:
    """Add a new session to the database."""
    sessions_collection.insert_one(
        {
            "session_id": session_id,
            "title": title,
            "created_at": datetime.utcnow().isoformat(),
        }
    )
    return title

def add_message(session_id: str, user_message: str, ai_message: str):
    """Add user and AI messages to the conversation."""
    timestamp = datetime.utcnow().isoformat()
    logger.info(f"Adding message to session {session_id} at {timestamp}")

    if user_message:
        conversations_collection.insert_one(
            {
                "session_id": session_id,
                "role": "user",
                "message": user_message,
                "created_at": timestamp,
            }
        )
    
    if ai_message:
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
    """Fetch all conversations for a session."""
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
    """Get all sessions sorted by creation time."""
    sessions = list(
        sessions_collection.find(
            {}, {"_id": 0, "session_id": 1, "title": 1, "created_at": 1}
        ).sort("created_at", -1)
    )
    return sessions

def get_file_metadata(file_id: str) -> Optional[Dict]:
    """Get file metadata from MongoDB."""
    try:
        return files_collection.find_one({"file_id": file_id}, {"_id": 0})
    except Exception as e:
        logger.error(f"Error fetching file metadata: {e}")
        return None

def update_file_status(file_id: str, status: str):
    """Update file processing status."""
    try:
        files_collection.update_one(
            {"file_id": file_id},
            {"$set": {"status": status, "updated_at": datetime.utcnow().isoformat()}},
        )
    except Exception as e:
        logger.error(f"Error updating file status: {e}")

def get_session_files(session_id: str) -> List[Dict]:
    """Get all files for a session."""
    try:
        files = list(
            files_collection.find({"session_id": session_id}, {"_id": 0}).sort(
                "upload_date", -1
            )
        )
        return files
    except Exception as e:
        logger.error(f"Error fetching session files: {e}")
        return []