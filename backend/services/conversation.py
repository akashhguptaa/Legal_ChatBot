from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger
import traceback
from typing import Optional, List, Dict
from config.config import OPENAI_API_KEY

# Original LLM for backward compatibility and session title generation
llm = None
try:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set in environment variables.")

    llm = ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model="gpt-4o-mini",
        temperature=0.1,
        streaming=True,
    )

    logger.info(f"OpenAI LLM client initialized: {llm}")
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}\n{traceback.format_exc()}")

# Check LangGraph availability and import
LANGGRAPH_AVAILABLE = False
chat_llm_with_graph = None

try:
    from Graph.legal_graph import chat_llm_with_graph
    LANGGRAPH_AVAILABLE = True
    logger.info("LangGraph integration available")
except ImportError as e:
    LANGGRAPH_AVAILABLE = False
    logger.warning(f"LangGraph not available, falling back to original chat_llm: {e}")
except Exception as e:
    LANGGRAPH_AVAILABLE = False
    logger.warning(f"LangGraph not available, falling back to original chat_llm: {e}")


async def chat_llm(
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    session_id: str = None,
):
    """
    Enhanced chat function that uses LangGraph when available and session_id is provided
    """

    # Use LangGraph if available and session_id is provided
    if LANGGRAPH_AVAILABLE and session_id:
        try:
            async for chunk in chat_llm_with_graph(
                query, conversation_history, session_id
            ):
                yield chunk
            return
        except Exception as e:
            logger.error(f"Error with LangGraph, falling back to original: {e}")
            # Fall through to original implementation

    # Original implementation (fallback)
    system_prompt = """
        You are LAW_GPT, an AI assistant who can help with various topics.
        You are knowledgeable and can provide helpful information on many subjects.
        FEW IMPORTANT THINGS TO KEEP IN MIND:
        1. You are helpful and informative.
        2. Your answers should be concise and to the point.
        3. If you don't know the answer, say "I don't know" instead of making up an answer.
        4. Do not be monotonous, try to vary your responses, and use emojis only when necessary.
        5. Use proper markdown formatting with headers (###), bullet points, and line breaks.
        7. Use ### for section headers when organizing information.
    """

    conversation_context = ""
    if conversation_history:
        conversation_context = "\nPrevious Conversation:\n"
        for msg in conversation_history:
            if msg.get("role") == "user":
                conversation_context += f"User: {msg['message']}\n"
            if msg.get("role") == "ai":
                conversation_context += f"Assistant: {msg['message']}\n"

    human_prompt = """
        This is the conversation history between the user and the AI.
        conversation_context: {conversation_context}
        Original question: {query}
        Please answer the question, keeping the conversation flow in the context, so it don't look like a new conversation.
    """

    prompt_template = ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("human", human_prompt)]
    )

    chain = prompt_template | llm | StrOutputParser()

    try:
        async for chunk in chain.astream(
            {"query": query, "conversation_context": conversation_context}
        ):
            yield chunk

    except Exception as e:
        logger.error(f"Error in chat_llm: {e}\n{traceback.format_exc()}")
        yield "An error occurred while processing your request. Please try again later."


# Function to generate a session title using the LLM
async def generate_session_title(user_message: str) -> str:
    prompt = f"Generate a concise, relevant title (max 8 words) for a legal chat session based on this user message: '{user_message}'. Return only the title, no extra text and be unique with the titles."

    try:
        chain = llm | StrOutputParser()
        result = await chain.ainvoke(prompt)

        title = result.strip().replace("\n", " ")
        if len(title) > 60:
            title = title[:60] + "..."

        title = title.replace("  ", " ").strip()
        return title or "Untitled Session"
    except Exception as e:
        logger.error(f"Error generating session title: {e}\n{traceback.format_exc()}")
        return "Untitled Session"


if __name__ == "__main__":
    import asyncio

    async def main():
        # Test both modes
        print("Testing original mode:")
        async for chunk in chat_llm("What is contract law?"):
            print(chunk, end="")
        print("\n\nTesting with session ID:")
        async for chunk in chat_llm("What is contract law?", session_id="test-session"):
            print(chunk, end="")

    asyncio.run(main())