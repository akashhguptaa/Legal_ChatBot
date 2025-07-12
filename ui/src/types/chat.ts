export interface Message {
  role: "user" | "ai";
  message: string;
  created_at: string;
}

export interface ChatSession {
  session_id: string;
  title: string;
  created_at: string;
}

export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

export interface WebSocketMessage {
  query: string;
  session_id: string | null;
}

export interface WebSocketResponse {
  session_id?: string;
  title?: string;
}