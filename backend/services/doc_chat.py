from typing import AsyncGenerator
import asyncio
from langchain_openai import ChatOpenAI
from typing import List, Dict
from langchain_core.output_parsers import StrOutputParser
from config.config import OPENAI_API_KEY
from utils.create_vectorStore import count_tokens
from loguru import logger

llm_summary = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    model="gpt-4o-mini",
    temperature=0.1,
)

async def generate_document_summary(
    sections: List[Dict], file_name: str
) -> AsyncGenerator[str, None]:
    """Stream the generation of a legal document summary as it's produced."""

    content_preview = ""
    section_titles = []

    for section in sections[:10]:  # see explanation below
        section_titles.append(section['section_title'])
        content_preview += f"Section: {section['section_title']}\n"
        content_preview += f"Content: {section['content'][:200]}...\n\n"

    summary_prompt = f"""
    Analyze this legal document and provide a comprehensive summary with the following structure:

    Document: {file_name}
    Content Preview: {content_preview}

    Please provide:
    1. Document Type and Purpose
    2. Key Sections (list all major sections)
    3. Important Dates (extract any dates mentioned)
    4. Legal Keywords/Tags (identify key legal terms)
    5. Summary (2-3 paragraph overview)
    6. Compliance Requirements (if any)
    7. Key Stakeholders (if mentioned)

    Format as JSON with these exact keys: document_type, key_sections, important_dates, legal_tags, summary, compliance_requirements, key_stakeholders
    """

    try:
        chain = llm_summary | StrOutputParser()

        full_output = ""

        async for chunk in chain.astream(summary_prompt):
            full_output += chunk
            yield chunk  # Stream each chunk

        # Background logging of token usage (non-blocking)
        async def log_tokens():
            total_tokens = count_tokens(content_preview) + count_tokens(full_output)
            logger.info(f"Summary generation used {total_tokens} tokens")

        asyncio.create_task(log_tokens())

    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        yield '{"error": "Failed to generate summary."}'
