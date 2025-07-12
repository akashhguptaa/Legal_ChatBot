from utils.faiss_integration import search_similar_sections
from loguru import logger
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

async def handle_document_query(state, llm):
    """Handle document-specific queries using FAISS RAG"""
    try:
        if not state.session_files:
            state.response = "I don't see any uploaded documents in this session. Please upload a document first."
            return state

        all_relevant_sections = []
        for file_info in state.session_files:
            file_id = file_info["file_id"]
            try:
                results = search_similar_sections(query=state.query, file_id=file_id, limit=5)
                if results:
                    all_relevant_sections.extend(results)
            except Exception as e:
                logger.error(f"Error searching file {file_id}: {e}")
                continue

        all_relevant_sections.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_sections = all_relevant_sections[:5]
        state.relevant_sections = top_sections

        if not top_sections:
            state.response = "I couldn't find relevant information in your uploaded documents for this query."
            return state

        context_parts = []
        for section in top_sections:
            context_parts.append(f"""
            Document: {section.get('filename', 'Unknown')}
            Section: {section.get('section_title', 'Untitled')}
            Content: {section.get('content', '')}
            Score: {section.get('score', 0):.3f}
            """)

        document_context = "\n---\n".join(context_parts)
        state.document_context = document_context

        document_prompt = ChatPromptTemplate.from_template(
            """
        You are LAW_GPT, a legal document assistant. Answer the user's question based on the provided document context.
        
        Document Context:
        {document_context}
        
        Conversation History:
        {conversation_history}
        
        User Question: {query}
        
        Instructions:
        1. Base your answer primarily on the provided document context
        2. If the context doesn't contain enough information, say so clearly
        3. Quote relevant sections when helpful
        4. Be precise and professional
        5. You can answer questions about the document content, structure, and meaning
        6. If asked about document sections, types, or content, provide detailed answers
        7. Don't restrict yourself to only legal questions - answer any question about the uploaded document
        8. Use proper markdown formatting with headers (###), bullet points, and line breaks
        9. Use ### for section headers when organizing information

        Format your response with proper markdown structure and line breaks for readability.
        
        Answer:
        """
        )

        conversation_context = ""
        if state.conversation_history:
            for msg in state.conversation_history[-6:]:
                role = "User" if msg.get("role") == "user" else "AI"
                conversation_context += f"{role}: {msg['message']}\n"

        chain = document_prompt | llm | StrOutputParser()
        state.response_stream = chain.astream({
            "document_context": document_context,
            "conversation_history": conversation_context,
            "query": state.query,
        })
        
        state.response = "Document analysis complete."
        
    except Exception as e:
        logger.error(f"Error in document query: {e}")
        state.error = str(e)
        state.response = "I encountered an error while analyzing your documents. Please try again."

    return state