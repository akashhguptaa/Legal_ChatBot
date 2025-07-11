from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import uuid
from loguru import logger
from uvicorn.protocols.utils import ClientDisconnected

from services import doc_chat
from utils.dataBase_integration import (
    add_message,
    fetch_all_conversations,
    get_all_sessions_sorted,
    add_session,
)
from services.conversation import chat_llm, generate_session_title

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = None
    try:
        while True:
            data = await websocket.receive_json()
            query = data.get("query", "").strip()
            session_id = data.get("session_id")
            if not session_id:
                session_id = str(uuid.uuid4())
                await websocket.send_json(
                    {"session_id": session_id, "info": "New session created"}
                )
                title = await generate_session_title(query)
                add_session(session_id, title)

            conversation_history = fetch_all_conversations(session_id) or []

            response_text = ""
            async for response in chat_llm(query, conversation_history):
                response_text += response
                try:
                    await websocket.send_text(response)
                except (WebSocketDisconnect, ClientDisconnected):
                    logger.error("Client disconnected during streaming.")
                    return

            add_message(session_id, query, response_text)
    except (WebSocketDisconnect, ClientDisconnected):
        logger.error("WebSocket disconnected.")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        # Do NOT call await websocket.close() here!


@app.get("/chat/{session_id}")
async def get_chat_history(session_id: str):
    """
    Fetch the chat history for a given session ID.
    """
    history = fetch_all_conversations(session_id)
    if not history:
        return {"status": "error", "message": "No chat history found for this session."}
    return history


@app.get("/sessions")
async def get_sessions():
    """
    Fetch all unique chat sessions, sorted by creation time (earliest first).
    """
    sessions = get_all_sessions_sorted()
    return {"status": "success", "sessions": sessions}

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
