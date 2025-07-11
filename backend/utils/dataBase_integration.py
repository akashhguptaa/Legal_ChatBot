from pymongo import MongoClient
from datetime import datetime
from config.config import MONGODB_URI
import json
import asyncio
from loguru import logger
from typing import Optional

client = MongoClient(MONGODB_URI)
db = client["chatbot_db2"]
conversations_collection = db["conversations"]
sessions_collection = db["sessions"]  # New collection for session metadata


# Helper to generate a title from the first user message
def add_session(session_id: str, title: str) -> str:
    sessions_collection.insert_one(
        {
            "session_id": session_id,
            "title": title,
            "created_at": datetime.utcnow().isoformat()
        }
    )
    return title

def add_message(
    session_id: str,
    user_message: str,
    ai_message: str,
):
    timestamp = datetime.utcnow().isoformat()
    logger.info(f"Adding message to session {session_id} at {timestamp}")
    # If this is the first message for the session, create a title
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

# Returns a list of session dicts sorted by created_at ascending
def get_all_sessions_sorted() -> list:

    sessions = list(
        sessions_collection.find(
            {}, {"_id": 0, "session_id": 1, "title": 1, "created_at": 1}
        ).sort("created_at", -1)
    )
    # sessions.sort(key=lambda x: x.get("created_at", ""))
    return sessions


if __name__ == "__main__":
    pass
