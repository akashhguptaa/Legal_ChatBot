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
def generate_title_from_message(message: str) -> str:
    # Simple heuristic: use the first 8 words or 60 chars as the title
    words = message.strip().split()
    title = " ".join(words[:8])
    if len(title) > 60:
        title = title[:60] + "..."
    return title or "Untitled Session"


def get_or_create_session_title(session_id: str, user_message: str) -> str:
    session = sessions_collection.find_one({"session_id": session_id})
    if session and session.get("title"):
        return session["title"]
    # Generate and store title
    title = generate_title_from_message(user_message)
    sessions_collection.update_one(
        {"session_id": session_id},
        {"$setOnInsert": {"title": title, "created_at": datetime.utcnow().isoformat()}},
        upsert=True,
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
    if conversations_collection.count_documents({"session_id": session_id}) == 0:
        get_or_create_session_title(session_id, user_message)

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


def fetch_last_message(session_id: str):
    logger.info(f"Fetching last message for session {session_id}")

    last_message = conversations_collection.find_one(
        {"session_id": session_id}, sort=[("created_at", -1)]
    )

    if not last_message:
        return None

    # Fetch all messages for the session, sorted by created_at
    messages = list(
        conversations_collection.find({"session_id": session_id}).sort("created_at", 1)
    )

    result = []
    i = 0
    while i < len(messages) - 1:
        if messages[i]["role"] == "user" and messages[i + 1]["role"] == "ai":
            result.append(
                {"user": messages[i]["message"], "AI": messages[i + 1]["message"]}
            )
            if len(result) > 10:
                result = result[-10:]
            i += 2
        else:
            i += 1

    return result


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
    # Returns a list of session dicts sorted by created_at ascending
    sessions = list(
        sessions_collection.find(
            {}, {"_id": 0, "session_id": 1, "title": 1, "created_at": 1}
        )
    )
    sessions.sort(key=lambda x: x.get("created_at", ""))
    return sessions


if __name__ == "__main__":
    pass
