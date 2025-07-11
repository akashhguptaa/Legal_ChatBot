from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import (
    ChatPromptTemplate,
)
from loguru import logger
import traceback
from typing import (
    Optional,
    List,
    Dict,
)
from config.config import OPENAI_API_KEY

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


# Chat function to talk to the LLM
async def chat_llm(
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
):
    system_prompt = """
        You are a LAW GPT an online lawyer and YOUR NAME IS GPT_LAW.
        who knows about all the laws in the world, to guide the users for laws in the world.
        from the information of laws from different countries, if available, however if a user asks for any other thing, 
        except for laws, you will not answer it, but politely say that you are a LAW GPT and you can only answer questions related to laws.
        FEW IMPORTANT THINGS TO KEEP IN MIND:
        1. You are a LAW GPT, you can only answer questions related to laws.
        2. Your answers should be concise and to the point.
        3. If you don't know the answer, say "I don't know" instead of making up an answer.
        4. Do not be monotonous, try to vary your responses, and use emojis only when necessary.
    

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
        [("system", system_prompt),
         ("human", human_prompt)]
    )

    chain = prompt_template | llm | StrOutputParser()

    try: 
        async for chunk in chain.astream(
            {
                'query': query,
                'conversation_context': conversation_context
            }
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
        return title or "Untitled Session"
    except Exception as e:
        logger.error(f"Error generating session title: {e}\n{traceback.format_exc()}")
        return "Untitled Session"


if __name__ == "__main__":
    import asyncio

    async def main():
        response = await chat_llm("What is the law regarding contracts in India?")
        print(response)

    asyncio.run(main())
