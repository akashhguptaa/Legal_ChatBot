from utils.faiss_integration import search_similar_sections
from loguru import logger
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

async def handle_hybrid_query(state, llm):
    """Handle queries that benefit from both document context and general knowledge"""
    try:
        document_context = ""
        if state.session_files:
            all_relevant_sections = []
            for file_info in state.session_files:
                file_id = file_info["file_id"]
                try:
                    results = search_similar_sections(query=state.query, file_id=file_id, limit=3)
                    if results:
                        all_relevant_sections.extend(results)
                except Exception as e:
                    logger.error(f"Error searching file {file_id} in hybrid query: {e}")
                    continue

            all_relevant_sections.sort(key=lambda x: x.get("score", 0), reverse=True)
            top_sections = all_relevant_sections[:3]

            if top_sections:
                context_parts = []
                for section in top_sections:
                    context_parts.append(f"""
                    Document: {section.get('filename', 'Unknown')}
                    Section: {section.get('section_title', 'Untitled')}
                    Content: {section.get('content', '')[:500]}...
                    Score: {section.get('score', 0):.3f}
                    """)
                document_context = "\n---\n".join(context_parts)

        hybrid_prompt = ChatPromptTemplate.from_template(
            """
        You are LAW_GPT, a legal assistant. Answer the user's question using both the provided document context (if available) and your general legal knowledge.
        
        Document Context (if available):
        {document_context}
        
        Conversation History:
        {conversation_history}
        
        User Question: {query}
        
        Instructions:
        1. If document context is available, reference it in your answer
        2. Supplement with general legal knowledge and principles
        3. Explain how the document relates to broader legal concepts
        4. Be comprehensive but concise
        5. Always recommend consulting with a qualified attorney for specific legal advice
        6. Use proper markdown formatting with headers (###), bullet points, and line breaks
        7. Always use proper line breaks (\\n) for readability
        8. Use ### for section headers when organizing information
        
        Format your response with proper markdown structure and line breaks for readability.
        
        Answer:
        """
        )

        conversation_context = ""
        if state.conversation_history:
            for msg in state.conversation_history[-6:]:
                role = "User" if msg.get("role") == "user" else "Assistant"
                conversation_context += f"{role}: {msg['message']}\n"

        chain = hybrid_prompt | llm | StrOutputParser()
        state.response_stream = chain.astream({
            "document_context": document_context,
            "conversation_history": conversation_context,
            "query": state.query,
        })
        state.response = "Hybrid analysis complete."

    except Exception as e:
        logger.error(f"Error in hybrid query: {e}")
        state.error = str(e)
        state.response = "I encountered an error while processing your question. Please try again."

    return state
