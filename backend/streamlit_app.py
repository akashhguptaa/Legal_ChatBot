import streamlit as st
import requests
import os

BACKEND_URL = "http://localhost:8000"

st.set_page_config(page_title="Legal Document Chatbot", layout="wide")
st.title("📄 Legal Document Chatbot")

# Sidebar: Document management
st.sidebar.header("Document Management")

# Upload PDF
uploaded_file = st.sidebar.file_uploader("Upload a PDF", type=["pdf"])
if uploaded_file is not None:
    with st.spinner("Uploading PDF to backend..."):
        files = {"file": (uploaded_file.name, uploaded_file, "application/pdf")}
        try:
            response = requests.post(f"{BACKEND_URL}/upload", files=files)
            result = response.json()
            if result.get("success"):
                st.sidebar.success(f"Uploaded and processed: {uploaded_file.name}")
            else:
                st.sidebar.error(f"Failed: {result.get('message', 'Unknown error')}")
        except Exception as e:
            st.sidebar.error(f"Upload failed: {e}")

# List all documents
with st.sidebar.expander("All Documents", expanded=True):
    try:
        response = requests.get(f"{BACKEND_URL}/documents")
        docs = response.json()
    except Exception as e:
        docs = []
        st.write(f"Error fetching documents: {e}")
    if docs:
        for doc in docs:
            st.write(
                f"**{doc['filename']}** | Pages: {doc['total_pages']} | Chunks: {doc['total_chunks']}"
            )
    else:
        st.write("No documents found.")

# Select document
doc_names = [doc["filename"] for doc in docs] if docs else []
selected_doc = st.sidebar.selectbox("Select a document", ["All Documents"] + doc_names)

# Delete document
if selected_doc != "All Documents" and st.sidebar.button(f"Delete '{selected_doc}'"):
    with st.spinner(f"Deleting {selected_doc}..."):
        try:
            response = requests.delete(f"{BACKEND_URL}/delete/{selected_doc}")
            result = response.json()
            if result.get("success"):
                st.sidebar.success(f"Deleted: {selected_doc}")
            else:
                st.sidebar.error(f"Failed: {result.get('message', 'Unknown error')}")
        except Exception as e:
            st.sidebar.error(f"Delete failed: {e}")

# Main area: Summary and Q&A
if selected_doc != "All Documents" and selected_doc:
    st.subheader(f"Summary for: {selected_doc}")
    try:
        response = requests.get(f"{BACKEND_URL}/summary/{selected_doc}")
        summary_result = response.json()
        if summary_result.get("success"):
            st.info(summary_result["summary"])
        else:
            st.warning("No summary available.")
    except Exception as e:
        st.warning(f"Error fetching summary: {e}")
else:
    st.subheader("Ask a Question (searches all documents)")

# Question input
question = st.text_input("Enter your legal question:")
if st.button("Ask") and question.strip():
    with st.spinner("Searching and generating answer..."):
        data = {"question": question}
        if selected_doc != "All Documents" and selected_doc:
            data["filename"] = selected_doc
        try:
            response = requests.post(f"{BACKEND_URL}/query", data=data)
            result = response.json()
            if result.get("success"):
                st.markdown(f"**Answer:**\n{result['answer']}")
                with st.expander("Sources / Chunks", expanded=False):
                    for src in result["sources"]:
                        st.write(
                            f"File: {src['filename']} | Pages: {src['pages']} | Section: {src['section']} | Score: {src['relevance_score']}"
                        )
            else:
                st.error(result.get("answer", "No answer returned."))
        except Exception as e:
            st.error(f"Query failed: {e}")
