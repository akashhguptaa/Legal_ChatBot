from typing import AsyncGenerator
import asyncio
from langchain_openai import ChatOpenAI
from typing import List, Dict
from langchain_core.output_parsers import StrOutputParser
from config.config import OPENAI_API_KEY
from utils.faiss_integration import count_tokens
from loguru import logger

llm_summary = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    model="gpt-4o-mini",
    temperature=0.1,
    streaming=True,
)


async def generate_document_summary(
    sections: List[Dict], file_name: str
) -> AsyncGenerator[str, None]:
    """Stream the generation of a clean, formatted legal document summary."""

    content_preview = ""
    section_titles = []

    for section in sections[:10]:  # First 10 sections for context
        section_titles.append(section["section_title"])
        content_preview += f"Section: {section['section_title']}\n"
        content_preview += f"Content: {section['content'][:200]}...\n\n"

    summary_prompt = f"""
    Analyze this legal document and provide a clean, well-formatted summary using markdown formatting.
    
    Document: {file_name}
    Content Preview: {content_preview}
    
    Create a summary with the following structure using markdown if these things are present in the document, if not then do not include them:
    
    # 📄 Document Summary: {file_name}
    
    ## 📋 Document Type
    [Brief description of document type and purpose]
    
    ## 🔑 Key Sections
    - [List major sections with bullet points]
    - [Use clear, concise descriptions]
    
    ## ⏰ Important Dates
    - [List any dates mentioned, if none say "No specific dates mentioned"]
    
    ## 🏷️ Legal Terms
    - [List key legal terms and definitions]
    
    ## 📝 Summary
    [2-3 paragraph overview in clear, professional language, and in detail]
    
    ## ⚖️ Compliance Requirements
    - [List any compliance requirements, if none say "No specific compliance requirements mentioned"]
    
    ## 👥 Key Parties
    - [List main stakeholders/parties involved]
    
    Instructions:
    1. Format the response with proper markdown headings, bullet points, and bold text where appropriate
    2. Make it visually appealing and easy to read in a chat interface
    3. Ensure each section is clearly separated with line breaks
    4. Use ### for section headers and maintain consistent formatting
    """

    try:
        chain = llm_summary | StrOutputParser()

        full_output = ""

        async for chunk in chain.astream(summary_prompt):
            full_output += chunk
            yield chunk  

        # Background logging of token usage (non-blocking)
        async def log_tokens():
            total_tokens = count_tokens(content_preview) + count_tokens(full_output)
            logger.info(f"Summary generation used {total_tokens} tokens")

        asyncio.create_task(log_tokens())

    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        yield "## ❌ Error\nFailed to generate summary. Please try again."
