from utils.dataBase_integration import files_collection
from loguru import logger
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

async def route_query(state, llm):
    """Determine if query is document-specific, general, or hybrid"""
    try:
        session_files = list(
            files_collection.find(
                {"session_id": state.session_id},
                {"_id": 0, "file_id": 1, "filename": 1},
            )
        )
        state.session_files = session_files

        if not session_files:
            state.route_decision = "general"
            return state

        routing_prompt = ChatPromptTemplate.from_template(
            """
        Analyze this user query and determine the best routing strategy:
        
        User Query: {query}
        Available Documents: {file_list}
        
        Classify as:
        - "document": Query is specifically about uploaded documents
        - "general": Query is about general legal knowledge
        - "hybrid": Query could benefit from both document context AND general legal knowledge
        
        Respond with only: document, general, or hybrid
        """
        )

        file_list = [f["filename"] for f in session_files]
        chain = routing_prompt | llm | StrOutputParser()
        decision = await chain.ainvoke({
            "query": state.query,
            "file_list": ", ".join(file_list) if file_list else "None",
        })

        state.route_decision = decision.strip().lower()
        if state.route_decision not in ["document", "general", "hybrid"]:
            state.route_decision = "general"

    except Exception as e:
        logger.error(f"Error in routing: {e}")
        state.route_decision = "general"
        state.error = str(e)

    return state
