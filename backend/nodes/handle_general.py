from langchain_core.prompts import ChatPromptTemplate
from loguru import logger
from langchain_core.output_parsers import StrOutputParser

async def handle_general_query(state, llm):
    """Handle general legal queries"""
    try:
        general_prompt = ChatPromptTemplate.from_template(
            """
        You are Lawroom AI, an AI assistant. Answer questions with accurate, helpful information.
        
        Conversation History:
        {conversation_history}
        
        User Question: {query}
        
        Instructions:
        1. Provide accurate and helpful information
        2. Be concise and to the point
        3. If you don't know something, say so
        4. Try to answer as many things as you can, just adding laws and legal principles to it, 
            for example, if a user asks a vauge question about, tell me about sports, 
            then find the relevant laws and legal principles related to sports,
            example2: if a user asks for something related to resume, or anything can you solve this problem, 
            then find the relevant laws and legal principles related to resume, or anything can you solve this problem,
        
        5. Only for the queries who are highly out of the scope of legal, then answer that I am Lawroom AI, an AI assistant, I can only answer questions related to legal topics,
    
        
        Format your response with proper markdown structure and line breaks for readability.
        
        Answer:
        """
        )

        conversation_context = ""
        if state.conversation_history:
            for msg in state.conversation_history[-6:]:
                role = "User" if msg.get("role") == "user" else "Assistant"
                conversation_context += f"{role}: {msg['message']}\n"

        chain = general_prompt | llm | StrOutputParser()
        state.response_stream = chain.astream({
            "conversation_history": conversation_context,
            "query": state.query,
        })
        state.response = "General query processing complete."

    except Exception as e:
        logger.error(f"Error in general query: {e}")
        state.error = str(e)
        state.response = "I encountered an error while processing your question. Please try again."

    return state