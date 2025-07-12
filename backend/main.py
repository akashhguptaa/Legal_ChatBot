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
from fastapi.responses import StreamingResponse
import json
import uuid
from loguru import logger

from uvicorn.protocols.utils import ClientDisconnected

from utils.dataBase_integration import (
    add_message,
    fetch_all_conversations,
    get_all_sessions_sorted,
    add_session,
    files_collection,
    sessions_collection,
)
from utils.faiss_integration import (
    create_faiss_embeddings,
    search_similar_sections,
    get_document_info,
    process_query_search,
)
from Graph.legal_graph import chat_llm_with_graph
from services.conversation import generate_session_title  # Keep only this
import os
import aiofiles
from pathlib import Path
import tempfile
from datetime import datetime

from utils.faiss_integration import extract_pdf_sections
from services.doc_chat import generate_document_summary

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FAISS_INDEX_DIR = Path("Faiss_index")
FAISS_INDEX_DIR.mkdir(exist_ok=True)


@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = None
    try:
        while True:
            data = await websocket.receive_json()
            query = data.get("query", "").strip()
            session_id = data.get("session_id")

            title = None

            if not session_id:
                session_id = str(uuid.uuid4())
                title = await generate_session_title(query)
                add_session(session_id, title)
                logger.info(
                    f"Created new session {session_id} for chat (no session_id provided)"
                )

                await websocket.send_json(
                    {
                        "session_id": session_id,
                        "title": title.strip("\"'"),
                        "info": "New session created",
                    }
                )
            else:
                logger.info(f"Received session_id for chat: {session_id}")

                existing_session = sessions_collection.find_one(
                    {"session_id": session_id}
                )
                if not existing_session:
                    title = await generate_session_title(query)
                    add_session(session_id, title)
                    logger.info(
                        f"Created new session {session_id} for chat (session_id provided but didn't exist)"
                    )
                else:
                    logger.info(f"Using existing session {session_id} for chat")

            conversation_history = fetch_all_conversations(session_id) or []

            response_text = ""

            async for response in chat_llm_with_graph(query, conversation_history, session_id):
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


@app.get("/chat/{session_id}")
async def get_chat_history(session_id: str):
    """Fetch the chat history for a given session ID."""
    history = fetch_all_conversations(session_id)
    if not history:
        return {"status": "error", "message": "No chat history found for this session."}
    return history


@app.get("/sessions")
async def get_sessions():
    """Fetch all unique chat sessions, sorted by creation time (earliest first)."""
    sessions = get_all_sessions_sorted()
    return {"status": "success", "sessions": sessions}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload/summary")
async def upload_and_stream_summary(
    file: UploadFile = File(...), session_id: str = Form(None)
):
    """Upload PDF and stream summary generation."""

    if not file.content_type.startswith("application/pdf"):
        raise HTTPException(400, "Invalid file type. PDF files only.")

    file_id = str(uuid.uuid4())
    if not session_id:
        session_id = str(uuid.uuid4())

    if not sessions_collection.find_one({"session_id": session_id}):
        add_session(session_id, f"Document: {file.filename}")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
        temp_path = temp_file.name

        async with aiofiles.open(temp_path, "wb") as buffer:
            chunk_size = 8192
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                await buffer.write(chunk)

    try:
        sections = extract_pdf_sections(temp_path)
        total_tokens = await create_faiss_embeddings(sections, file_id, file.filename)

        files_collection.insert_one(
            {
                "file_id": file_id,
                "session_id": session_id,
                "filename": file.filename,
                "file_size": os.path.getsize(temp_path),
                "total_sections": len(sections),
                "total_tokens": total_tokens,
                "upload_date": datetime.utcnow().isoformat(),
                "status": "processed",
            }
        )

        add_message(session_id, f"Uploaded: {file.filename}", "")

        async def stream_summary():
            yield f'data: {{"status": "session_id", "session_id": "{session_id}"}}\n\n'

            summary = ""
            async for chunk in generate_document_summary(sections, file.filename):
                summary += chunk
                yield f'data: {{"status": "summary_chunk", "content": {json.dumps(chunk)} }}\n\n'

            add_message(session_id, "", summary)
            yield 'data: {"status": "complete"}\n\n'

        return StreamingResponse(stream_summary(), media_type="text/event-stream")

    finally:
        os.unlink(temp_path)


@app.get("/sessions/{session_id}/files")
async def get_session_files(session_id: str):
    """Get files for a session."""
    files = list(
        files_collection.find({"session_id": session_id}, {"_id": 0}).sort(
            "upload_date", -1
        )
    )
    return {"files": files}


@app.get("/files/{file_id}")
async def get_file_details(file_id: str):
    """Get file details."""
    file_data = files_collection.find_one({"file_id": file_id}, {"_id": 0})
    if not file_data:
        raise HTTPException(404, "File not found")

    # Get section count from FAISS metadata
    try:
        doc_info = get_document_info(file_id)
        file_data["embeddings_count"] = doc_info.get("total_sections", 0)
    except:
        file_data["embeddings_count"] = 0

    return {"file": file_data}


@app.get("/search/{file_id}")
async def search_document(file_id: str, query: str):
    """Search within a specific document using FAISS."""
    try:
        result = process_query_search(query, file_id)
        return result
    except Exception as e:
        raise HTTPException(500, f"Search failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
