import fitz  # PyMuPDF for better PDF handling
from typing import List, Dict, Any
import hashlib
from loguru import logger


def generate_file_hash(file_path: str) -> str:
    """Generate a unique hash for the file to avoid duplicates."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_text_with_page_numbers(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extract text from PDF with page numbers and section detection.
    Returns list of dictionaries with text, page_number, and section info.
    """
    try:
        doc = fitz.open(pdf_path)
        pages_data = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            text = text.strip()
            if not text:
                continue
            section_markers = [
                "SECTION",
                "CHAPTER",
                "ARTICLE",
                "PART",
                "TITLE",
                "§",
                "Article",
                "Chapter",
                "Section",
                "Part",
            ]
            is_section_start = any(marker in text[:200] for marker in section_markers)
            pages_data.append(
                {
                    "text": text,
                    "page_number": page_num + 1,
                    "is_section_start": is_section_start,
                    "char_count": len(text),
                }
            )
        doc.close()
        return pages_data
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return []


def create_intelligent_chunks(
    pages_data: List[Dict[str, Any]], chunk_size: int = 1500, chunk_overlap: int = 200
) -> List[Dict[str, Any]]:
    """
    Create intelligent chunks based on legal document structure.
    Prioritizes section boundaries and maintains context.
    """
    chunks = []
    current_chunk = ""
    current_pages = []
    current_section = ""
    for page_data in pages_data:
        text = page_data["text"]
        page_num = page_data["page_number"]
        lines = text.split("\n")
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            if page_data["is_section_start"] and i < 3:
                section_markers = [
                    "SECTION",
                    "CHAPTER",
                    "ARTICLE",
                    "PART",
                    "TITLE",
                    "§",
                ]
                if any(marker in line.upper() for marker in section_markers):
                    if current_chunk.strip():
                        chunks.append(
                            {
                                "text": current_chunk.strip(),
                                "page_numbers": current_pages.copy(),
                                "section": current_section,
                                "chunk_size": len(current_chunk),
                            }
                        )
                    current_chunk = ""
                    current_pages = []
                    current_section = line
            current_chunk += line + " "
            if page_num not in current_pages:
                current_pages.append(page_num)
            if len(current_chunk) > chunk_size:
                sentences = current_chunk.split(". ")
                if len(sentences) > 1:
                    break_point = ". ".join(sentences[:-1]) + "."
                    remainder = sentences[-1]
                    chunks.append(
                        {
                            "text": break_point,
                            "page_numbers": current_pages.copy(),
                            "section": current_section,
                            "chunk_size": len(break_point),
                        }
                    )
                    current_chunk = remainder + " "
                    current_pages = [current_pages[-1]] if current_pages else []
                else:
                    words = current_chunk.split()
                    split_point = len(words) // 2
                    first_half = " ".join(words[:split_point])
                    second_half = " ".join(words[split_point:])
                    chunks.append(
                        {
                            "text": first_half,
                            "page_numbers": current_pages.copy(),
                            "section": current_section,
                            "chunk_size": len(first_half),
                        }
                    )
                    current_chunk = second_half + " "
                    current_pages = [current_pages[-1]] if current_pages else []
    if current_chunk.strip():
        chunks.append(
            {
                "text": current_chunk.strip(),
                "page_numbers": current_pages,
                "section": current_section,
                "chunk_size": len(current_chunk),
            }
        )
    return chunks
