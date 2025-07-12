from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class GraphState(BaseModel):
    query: str
    session_id: str
    conversation_history: List[Dict[str, str]]
    route_decision: Optional[str] = None
    document_context: Optional[str] = None
    response: Optional[str] = None
    response_stream: Optional[Any] = None  
    session_files: Optional[List[Dict]] = None
    relevant_sections: Optional[List[Dict]] = None
    error: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True  
