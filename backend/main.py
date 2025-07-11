from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware

import uuid
from loguru import logger
from streamlit import json
from uvicorn.protocols.utils import ClientDisconnected

from services import doc_chat
from utils.dataBase_integration import (
    add_message,
    fetch_all_conversations,
    get_all_sessions_sorted,
    add_session,
    files_collection,
    sessions_collection,
    embeddings_collection,
)
from services.conversation import chat_llm, generate_session_title
import os
import aiofiles
from pathlib import Path
import tempfile
from datetime import datetime

from utils.create_vectorStore import (
    create_embeddings_batch,
    extract_pdf_sections,
)

from services.doc_chat import generate_document_summary

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
            
            title = None  # Track if we need to send title back
            
            if not session_id:
                session_id = str(uuid.uuid4())
                title = await generate_session_title(query)
                add_session(session_id, title)
                
                # Send session_id AND title back to frontend
                await websocket.send_json(
                    {
                        "session_id": session_id, 
                        "title": title.strip('"\''),  # Remove quotes here
                        "info": "New session created"
                    }
                )

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


@app.post("/upload")
@app.post("/upload")
async def upload_file(file: UploadFile = File(...), session_id: str = None):
    """
    Enhanced upload endpoint with PDF processing, embeddings, and summary generation.
    Now includes session_id association.
    """
    try:
        # Validate file type
        if not file.content_type.startswith("application/pdf"):
            raise HTTPException(
                status_code=400, 
                detail="Invalid file type. Please upload PDF files only."
            )
        
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        safe_filename = file.filename.replace("/", "_").replace("\\", "_").replace("..", "_")
        if not safe_filename:
            safe_filename = f"uploaded_file_{file_id}.pdf"
        
        # If no session_id provided, create a new one
        if not session_id:
            session_id = str(uuid.uuid4())
            # Generate title based on filename
            title = f"Document: {safe_filename}"
            add_session(session_id, title)
        else:
            # Verify session exists, if not create it
            existing_session = sessions_collection.find_one({"session_id": session_id})
            if not existing_session:
                title = f"Document: {safe_filename}"
                add_session(session_id, title)
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_path = temp_file.name
        temp_file.close()
        
        # Stream file to temp location using aiofiles for async operations
        async with aiofiles.open(temp_path, 'wb') as buffer:
            chunk_size = 8192
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                await buffer.write(chunk)
        
        logger.info(f"File saved to temporary location: {temp_path}")
        
        # Extract sections from PDF
        sections = extract_pdf_sections(temp_path)
        logger.info(f"Extracted {len(sections)} sections from PDF")
        
        # Create embeddings in batches
        total_embedding_tokens = await create_embeddings_batch(sections, file_id)
        
        # Generate document summary
        summary_chunks = []
        async for chunk in generate_document_summary(sections, safe_filename):
            summary_chunks.append(chunk)
        summary_data = {"summary": "".join(summary_chunks)}
        
        # Save file metadata to MongoDB with session_id
        file_metadata = {
            'file_id': file_id,
            'session_id': session_id,  # NEW: Associate with session
            'original_filename': file.filename,
            'safe_filename': safe_filename,
            'file_size': os.path.getsize(temp_path),
            'total_sections': len(sections),
            'total_tokens_embedding': total_embedding_tokens,
            'total_tokens_summary': summary_data.get('summary_tokens', 0),
            'summary': summary_data,
            'upload_date': datetime.utcnow().isoformat(),
            'status': 'processed'
        }
        
        files_collection.insert_one(file_metadata)
        
        # Clean up temp file (no permanent storage to DOCS_FOLDER)
        os.unlink(temp_path)
        
        total_tokens = total_embedding_tokens + summary_data.get('summary_tokens', 0)
        
        # NEW: Add a system message to the conversation about the uploaded document
        system_message = f"Document '{safe_filename}' has been uploaded and processed successfully. You can now ask questions about this document."
        add_message(session_id, f"[SYSTEM] Document uploaded: {safe_filename}", system_message)
        
        logger.info(f"File processed successfully. Total tokens used: {total_tokens}")
        
        return {
            "status": "success",
            "message": "File uploaded and processed successfully",
            "file_id": file_id,
            "session_id": session_id,  # NEW: Return session_id
            "filename": safe_filename,
            "sections_count": len(sections),
            "total_tokens_used": total_tokens,
            "summary": summary_data
        }
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        # Clean up temp file if it exists
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# NEW: Additional endpoint to get files by session
@app.get("/sessions/{session_id}/files")
async def get_session_files(session_id: str):
    """Get all files uploaded in a specific session"""
    files = list(files_collection.find(
        {"session_id": session_id}, 
        {"_id": 0}
    ).sort("upload_date", -1))
    return {"status": "success", "files": files}

@app.get("/files")
async def get_files():
    """Get all processed files"""
    files = list(files_collection.find({}, {"_id": 0}).sort("upload_date", -1))
    return {"status": "success", "files": files}

@app.get("/files/{file_id}")
async def get_file_details(file_id: str):
    """Get detailed information about a specific file"""
    file_data = files_collection.find_one({"file_id": file_id}, {"_id": 0})
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get embeddings count
    embeddings_count = embeddings_collection.count_documents({"file_id": file_id})
    file_data["embeddings_count"] = embeddings_count
    
    return {"status": "success", "file": file_data}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)