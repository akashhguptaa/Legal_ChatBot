from typing import List, Dict, Any
import re
from tiktoken import encoding_for_model


encoding = encoding_for_model("gpt-4o-mini")

def count_tokens(text: str) -> int:
    """Count tokens in text"""
    return len(encoding.encode(text))

class LegalDocumentChunker:
    """Enhanced chunker for legal documents with structure preservation"""
    
    def __init__(self, max_tokens: int = 512, overlap_percentage: float = 0.15):
        self.max_tokens = max_tokens
        self.overlap_percentage = overlap_percentage
        self.legal_section_patterns = [
            r'^\s*(ARTICLE|Article|SECTION|Section|CHAPTER|Chapter)\s+([IVX]+|\d+)',
            r'^\s*(\d+)\.\s*([A-Z][^.]*\.?)',
            r'^\s*([A-Z][A-Z\s]{3,})\s*$',  
            r'^\s*(WHEREAS|THEREFORE|NOW THEREFORE)',
            r'^\s*(Definitions?|Obligations?|Representations?|Warranties?|Termination|Liability|Confidentiality)',
            r'^\s*\([a-z]\)\s*',  
            r'^\s*\([0-9]+\)\s*',  
        ]
    
    def is_section_header(self, line: str) -> bool:
        """Check if line is a section header"""
        line = line.strip()
        if len(line) < 3:
            return False
        
        return any(re.match(pattern, line, re.IGNORECASE) for pattern in self.legal_section_patterns)
    
    def extract_hierarchical_sections(self, text: str) -> List[Dict[str, Any]]:
        """Extract sections maintaining hierarchical structure"""
        lines = text.split('\n')
        sections = []
        current_section = None
        current_content = []
        section_hierarchy = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            if self.is_section_header(line):
                # Save previous section if exists
                if current_section and current_content:
                    content = ' '.join(current_content).strip()
                    if content:
                        sections.append({
                            'section_title': current_section,
                            'content': content,
                            'hierarchy': section_hierarchy.copy(),
                            'line_start': i - len(current_content),
                            'line_end': i - 1,
                            'token_count': count_tokens(content)
                        })
                
                # Start new section
                current_section = line
                current_content = []
                
                # Determine hierarchy level
                if re.match(r'^\s*(ARTICLE|SECTION|CHAPTER)', line, re.IGNORECASE):
                    section_hierarchy = [line]
                elif re.match(r'^\s*\d+\.', line):
                    section_hierarchy = section_hierarchy[:1] + [line]
                elif re.match(r'^\s*\([a-z]\)', line):
                    section_hierarchy = section_hierarchy[:2] + [line]
                else:
                    section_hierarchy.append(line)
            else:
                current_content.append(line)
        
        # Add final section
        if current_section and current_content:
            content = ' '.join(current_content).strip()
            if content:
                sections.append({
                    'section_title': current_section,
                    'content': content,
                    'hierarchy': section_hierarchy.copy(),
                    'line_start': len(lines) - len(current_content),
                    'line_end': len(lines) - 1,
                    'token_count': count_tokens(content)
                })
        
        return sections
    
    def create_overlapping_chunks(self, sections: List[Dict]) -> List[Dict]:
        """Create overlapping chunks with context preservation"""
        chunks = []
        
        for i, section in enumerate(sections):
            content = section['content']
            token_count = section['token_count']
            
            if token_count <= self.max_tokens:
                # Section fits in one chunk
                chunk = section.copy()
                
                # Add overlap from previous section if exists
                if i > 0 and sections[i-1]['token_count'] > 0:
                    prev_content = sections[i-1]['content']
                    overlap_tokens = int(count_tokens(prev_content) * self.overlap_percentage)
                    
                    if overlap_tokens > 0:
                        prev_words = prev_content.split()
                        overlap_words = prev_words[-overlap_tokens:] if len(prev_words) > overlap_tokens else prev_words
                        overlap_text = ' '.join(overlap_words)
                        
                        chunk['content'] = f"{overlap_text} {content}"
                        chunk['has_overlap'] = True
                        chunk['overlap_source'] = sections[i-1]['section_title']
                
                chunks.append(chunk)
            else:
                # Split large section into multiple chunks
                words = content.split()
                chunk_size = self.max_tokens - 50  # Leave room for overlap
                
                for j in range(0, len(words), chunk_size):
                    chunk_words = words[j:j + chunk_size]
                    chunk_content = ' '.join(chunk_words)
                    
                    # Add overlap from previous chunk
                    if j > 0:
                        overlap_size = int(chunk_size * self.overlap_percentage)
                        overlap_words = words[max(0, j - overlap_size):j]
                        overlap_text = ' '.join(overlap_words)
                        chunk_content = f"{overlap_text} {chunk_content}"
                    
                    chunk = {
                        'section_title': f"{section['section_title']} (Part {j//chunk_size + 1})",
                        'content': chunk_content,
                        'hierarchy': section['hierarchy'],
                        'is_split': True,
                        'part_number': j//chunk_size + 1,
                        'total_parts': (len(words) + chunk_size - 1) // chunk_size,
                        'token_count': count_tokens(chunk_content),
                        'has_overlap': j > 0
                    }
                    chunks.append(chunk)
        
        return chunks