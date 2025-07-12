from typing import Dict, List, Any, Optional, AsyncGenerator
from loguru import logger
from langchain_openai import ChatOpenAI
from models.models import GraphState

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_IMPORTS_OK = True
except ImportError as e:
    logger.error(f"Failed to import langgraph: {e}")
    LANGGRAPH_IMPORTS_OK = False

from config.config import OPENAI_API_KEY
from nodes.handle_document import handle_document_query
from nodes.handle_general import handle_general_query
from nodes.handle_hybrid import handle_hybrid_query
from nodes.routing import route_query


# Initialize models
llm = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    model="gpt-4o-mini",
    temperature=0.1,
    streaming=True,
)


class LegalChatGraph:
    def __init__(self):
        self.graph = self._create_graph()

    def _create_graph(self) -> StateGraph:
        """Create the LangGraph workflow"""
        workflow = StateGraph(GraphState)

        # Adding nodes
        workflow.add_node("router", self._route_query)
        workflow.add_node("document_query", self._handle_document_query)
        workflow.add_node("general_query", self._handle_general_query)
        workflow.add_node("hybrid_query", self._handle_hybrid_query)

        # Adding edges
        workflow.set_entry_point("router")
        workflow.add_conditional_edges(
            "router",
            self._routing_decision,
            {
                "document": "document_query",
                "general": "general_query",
                "hybrid": "hybrid_query",
            },
        )

        # All paths lead to END
        workflow.add_edge("document_query", END)
        workflow.add_edge("general_query", END)
        workflow.add_edge("hybrid_query", END)

        return workflow.compile()

    async def _route_query(self, state: GraphState) -> GraphState:
        return await route_query(state, llm)

    def _routing_decision(self, state: GraphState) -> str:
        return state.route_decision or "general"

    async def _handle_document_query(self, state: GraphState) -> GraphState:
        return await handle_document_query(state, llm)

    async def _handle_general_query(self, state: GraphState) -> GraphState:
        return await handle_general_query(state, llm)

    async def _handle_hybrid_query(self, state: GraphState) -> GraphState:
        return await handle_hybrid_query(state, llm)

    async def process_query(
        self, query: str, session_id: str, conversation_history: List[Dict] = None
    ) -> AsyncGenerator[str, None]:
        """Process a query through the graph and stream the response"""
        initial_state = GraphState(
            query=query,
            session_id=session_id,
            conversation_history=conversation_history or [],
        )

        try:
            final_state = await self.graph.ainvoke(initial_state)

            # LangGraph returns state as dict, not object
            if isinstance(final_state, dict):
                response_stream = final_state.get("response_stream")
                response = final_state.get("response")
            else:
                response_stream = getattr(final_state, 'response_stream', None)
                response = getattr(final_state, 'response', None)

            # Stream from the response_stream if available
            if response_stream:
                async for chunk in response_stream:
                    yield chunk
            elif response:
                yield response
            else:
                yield "I'm sorry, I couldn't generate a response. Please try again."

        except Exception as e:
            logger.error(f"Error processing query through graph: {e}")
            yield "I encountered an error while processing your request. Please try again."


# Global instance
legal_graph = LegalChatGraph()


# Updated function for backward compatibility
async def chat_llm_with_graph(
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    session_id: str = None,
):
    """Enhanced chat function using LangGraph"""
    if not session_id or not LANGGRAPH_IMPORTS_OK:
        from services.conversation import chat_llm
        async for chunk in chat_llm(query, conversation_history):
            yield chunk
        return

    async for chunk in legal_graph.process_query(query, session_id, conversation_history):
        yield chunk