@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    try:
        print("Received upload:", file.filename)
        suffix = os.path.splitext(file.filename)[-1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
        result = await doc_chat.process_and_store_pdf(tmp_path, file.filename)
        print("Upload result:", result)
        os.remove(tmp_path)
        return result
    except Exception as e:
        print("Error in /upload endpoint:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
async def list_documents():
    try:
        print("Calling doc_chat.list_documents()")
        docs = await doc_chat.list_documents()
        print("Docs returned:", docs)
        return docs
    except Exception as e:
        print("Error in /documents endpoint:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/summary/{filename}")
async def get_summary(filename: str):
    try:
        result = await doc_chat.get_document_summary(filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query")
async def query_document(question: str = Form(...), filename: str = Form(None)):
    try:
        logger.info(
            f"Querying vector store with question: {question}, filename: {filename}"
        )
        docs = await doc_chat.query_vector_store(question, top_k=top_k, filename=filename)
        logger.info(f"Vector store returned {len(docs)} results: {docs[:1]}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/delete/{filename}")
async def delete_document(filename: str):
    try:
        result = await doc_chat.delete_document(filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))