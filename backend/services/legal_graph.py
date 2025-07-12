from typing import Dict, List, Any, Optional, AsyncGenerator
import asyncio
from loguru import logger
import json

try:
    from langgraph.graph import StateGraph, END

    LANGGRAPH_IMPORTS_OK = True
except ImportError as e:
    logger.error(f"Failed to import langgraph: {e}")
    LANGGRAPH_IMPORTS_OK = False

from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from config.config import OPENAI_API_KEY
from utils.faiss_integration import (  # Changed from dataBase_integration
    process_query_search,
    search_similar_sections,
)
from utils.dataBase_integration import (
    files_collection,
    get_file_metadata,
)
from langchain_openai import OpenAIEmbeddings

# Initialize models
llm = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    model="gpt-4o-mini",
    temperature=0.1,
    streaming=True,
)


# State definition
class GraphState(BaseModel):
    query: str
    session_id: str
    conversation_history: List[Dict[str, str]]
    route_decision: Optional[str] = None
    document_context: Optional[str] = None
    response: Optional[str] = None
    response_stream: Optional[Any] = None  # Add this line
    session_files: Optional[List[Dict]] = None
    relevant_sections: Optional[List[Dict]] = None
    error: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True  


class LegalChatGraph:
    def __init__(self):
        self.graph = self._create_graph()

    def _create_graph(self) -> StateGraph:
        """Create the LangGraph workflow"""

        # Create the graph
        workflow = StateGraph(GraphState)

        # Add nodes
        workflow.add_node("router", self._route_query)
        workflow.add_node("document_query", self._handle_document_query)
        workflow.add_node("general_query", self._handle_general_query)
        workflow.add_node("hybrid_query", self._handle_hybrid_query)

        # Add edges
        workflow.set_entry_point("router")

        # Router decision logic
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
        """Determine if query is document-specific, general, or hybrid"""
        try:
            # Get files for this session from MongoDB
            session_files = list(
                files_collection.find(
                    {"session_id": state.session_id},
                    {"_id": 0, "file_id": 1, "filename": 1},
                )
            )

            state.session_files = session_files

            logger.info(
                f"Session {state.session_id} has {len(session_files)} files: {[f['filename'] for f in session_files]}"
            )

            # If no files, then general routing
            if not session_files:
                state.route_decision = "general"
                logger.info(
                    f"No files found for session {state.session_id}, routing to general"
                )
                return state

            routing_prompt = ChatPromptTemplate.from_template(
                """
            Analyze this user query and determine the best routing strategy:
            
            User Query: {query}
            
            Available Documents: {file_list}
            
            Classify as:
            - "document": Query is specifically about uploaded documents (e.g., "What does section 5 say?", "Summarize this contract")
            - "general": Query is about general legal knowledge (e.g., "What is contract law?", "How do I file a lawsuit?")
            - "hybrid": Query could benefit from both document context AND general legal knowledge (e.g., "Is this clause legal?", "What are my rights here?")
            
            Respond with only: document, general, or hybrid
            """
            )

            file_list = [f["filename"] for f in session_files]

            chain = routing_prompt | llm | StrOutputParser()
            decision = await chain.ainvoke(
                {
                    "query": state.query,
                    "file_list": ", ".join(file_list) if file_list else "None",
                }
            )

            state.route_decision = decision.strip().lower()

            # Fallback to general if unclear
            if state.route_decision not in ["document", "general", "hybrid"]:
                state.route_decision = "general"

            logger.info(
                f"Routing decision: {state.route_decision} for query: {state.query[:50]}..."
            )

        except Exception as e:
            logger.error(f"Error in routing: {e}")
            state.route_decision = "general"
            state.error = str(e)

        return state

    def _routing_decision(self, state: GraphState) -> str:
        """Return the routing decision"""
        return state.route_decision or "general"

    async def _handle_document_query(self, state: GraphState) -> GraphState:
        """Handle document-specific queries using FAISS RAG"""
        try:
            if not state.session_files:
                state.response = "I don't see any uploaded documents in this session. Please upload a document first."
                return state

            all_relevant_sections = []

            # Search through each file using FAISS
            for file_info in state.session_files:
                file_id = file_info["file_id"]
                logger.info(f"Processing query: {state.query} for file: {file_id}")

                try:
                    # Use FAISS search for this file
                    results = search_similar_sections(
                        query=state.query, file_id=file_id, limit=5
                    )

                    if results:
                        all_relevant_sections.extend(results)
                        logger.info(
                            f"Found {len(results)} relevant sections in file {file_id}"
                        )
                    else:
                        logger.info(f"No relevant sections found in file {file_id}")

                except Exception as e:
                    logger.error(f"Error searching file {file_id}: {e}")
                    continue

            # Sort by score (FAISS returns similarity scores)
            all_relevant_sections.sort(key=lambda x: x.get("score", 0), reverse=True)
            top_sections = all_relevant_sections[:5]

            state.relevant_sections = top_sections

            if not top_sections:
                state.response = "I couldn't find relevant information in your uploaded documents for this query."
                return state

            # Build context from relevant sections
            context_parts = []
            for section in top_sections:
                context_parts.append(
                    f"""
                Document: {section.get('filename', 'Unknown')}
                Section: {section.get('section_title', 'Untitled')}
                Content: {section.get('content', '')}
                Score: {section.get('score', 0):.3f}
                """
                )

            document_context = "\n---\n".join(context_parts)
            state.document_context = document_context

            # Generate response using document context
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

            # Stream the response
            state.response_stream = chain.astream(
            {
                "document_context": document_context,
                "conversation_history": conversation_context,
                "query": state.query,
            }
        )
            
            state.response = "Document analysis complete."
            
        except Exception as e:
            logger.error(f"Error in document query: {e}")
            state.error = str(e)
            state.response = "I encountered an error while analyzing your documents. Please try again."

        return state

    async def _handle_general_query(self, state: GraphState) -> GraphState:
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

            # Stream the response
            state.response_stream = chain.astream(
            {
                "conversation_history": conversation_context,
                "query": state.query,
            }
        )
            state.response = "General query processing complete."

        except Exception as e:
            logger.error(f"Error in general query: {e}")
            state.error = str(e)
            state.response = "I encountered an error while processing your question. Please try again."

        return state

    async def _handle_hybrid_query(self, state: GraphState) -> GraphState:
        """Handle queries that benefit from both document context and general knowledge"""
        try:
            document_context = ""
            if state.session_files:
                all_relevant_sections = []

                # Search through each file using FAISS
                for file_info in state.session_files:
                    file_id = file_info["file_id"]
                    logger.info(
                        f"Processing hybrid query: {state.query} for file: {file_id}"
                    )

                    try:
                        # Use FAISS search for this file
                        results = search_similar_sections(
                            query=state.query,
                            file_id=file_id,
                            limit=3,  # Fewer results for hybrid queries
                        )

                        if results:
                            all_relevant_sections.extend(results)

                    except Exception as e:
                        logger.error(
                            f"Error searching file {file_id} in hybrid query: {e}"
                        )
                        continue

                # Sort by score and take top 3
                all_relevant_sections.sort(
                    key=lambda x: x.get("score", 0), reverse=True
                )
                top_sections = all_relevant_sections[:3]

                if top_sections:
                    context_parts = []
                    for section in top_sections:
                        context_parts.append(
                            f"""
                        Document: {section.get('filename', 'Unknown')}
                        Section: {section.get('section_title', 'Untitled')}
                        Content: {section.get('content', '')[:500]}...
                        Score: {section.get('score', 0):.3f}
                        """
                        )
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

            # Stream the response
            state.response_stream = chain.astream(
            {
                "document_context": document_context,
                "conversation_history": conversation_context,
                "query": state.query,
            }
        )
            state.response = "Hybrid analysis complete."

        except Exception as e:
            logger.error(f"Error in hybrid query: {e}")
            state.error = str(e)
            state.response = "I encountered an error while processing your question. Please try again."

        return state

    async def process_query(
        self, query: str, session_id: str, conversation_history: List[Dict] = None
    ) -> AsyncGenerator[str, None]:
        """Process a query through the graph and stream the response"""

        # Create initial state
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
        # Fallback to original behavior for backward compatibility
        from services.conversation import chat_llm

        async for chunk in chat_llm(query, conversation_history):
            yield chunk
        return

    # Use the new graph-based approach
    async for chunk in legal_graph.process_query(
        query, session_id, conversation_history
    ):
        yield chunk
