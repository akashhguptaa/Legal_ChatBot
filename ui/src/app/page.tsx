"use client";

import React, { useState, useEffect, useRef } from "react";
import Sidebar from "@/components/Sidebar";
import ChatArea from "../components/ChatArea";
import MessageInput from "../components/MessageInput";
import { streamSummary } from "../utils/streaming";

interface Message {
  role: "user" | "ai";
  message: string;
  created_at: string;
}

interface ChatSession {
  session_id: string;
  title: string;
  created_at: string;
}

interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

export default function LawroomAI() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingMessage, setStreamingMessage] = useState("");

  // File upload states
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(
    null
  );
  const [uploadError, setUploadError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isStreamingRef = useRef(false);
  const currentSessionIdRef = useRef<string | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingMessage]);

  useEffect(() => {
    fetchSessions();
    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const connectWebSocket = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    wsRef.current = new WebSocket("ws://localhost:8000/ws/chat");

    wsRef.current.onopen = () => {
      console.log("WebSocket connected");
    };

    wsRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.session_id) {
          setCurrentSessionId(data.session_id);
          currentSessionIdRef.current = data.session_id;

          fetchSessions().then(() => {
            setSessions((prev) =>
              prev.map((session) =>
                session.session_id === data.session_id &&
                session.title === "New Chat"
                  ? { ...session, title: data.title || session.title }
                  : session
              )
            );
          });
        }
      } catch {
        if (isStreamingRef.current) {
          setStreamingMessage((prev) => prev + event.data);
        }
      }
    };

    wsRef.current.onclose = (event) => {
      console.log("WebSocket closed", event.code, event.reason);
      if (event.code !== 1000) {
        setTimeout(connectWebSocket, 1000);
      }
    };

    wsRef.current.onerror = (error) => {
      console.error("WebSocket error:", error);
    };
  };

  const cleanTitle = (title: string): string => {
    return title.replace(/^["']|["']$/g, ""); // Remove quotes from start and end
  };

  const fetchSessions = async () => {
    try {
      const response = await fetch("http://localhost:8000/sessions");
      const data = await response.json();
      if (data.status === "success") {
        // Clean up titles by removing quotes
        const cleanedSessions = data.sessions.map((session: ChatSession) => ({
          ...session,
          title: cleanTitle(session.title),
        }));
        setSessions(cleanedSessions);
      }
    } catch (error) {
      console.error("Error fetching sessions:", error);
    }
  };

  const fetchChatHistory = async (sessionId: string) => {
    try {
      const response = await fetch(`http://localhost:8000/chat/${sessionId}`);
      const data = await response.json();
      if (Array.isArray(data)) {
        setMessages(data);
      }
    } catch (error) {
      console.error("Error fetching chat history:", error);
    }
  };

  // File upload function with progress tracking
  const uploadFile = async (file: File): Promise<boolean> => {
    if (!file) return false;

    setIsUploading(true);
    setUploadError(null);
    setUploadProgress(null);

    try {
      setMessages((prev) => [
        ...prev,
        {
          role: "user" as const,
          message: `Uploaded: ${file.name}`,
          created_at: new Date().toISOString(),
        },
      ]);

      setStreamingMessage("Starting file upload...");

      const sessionId = currentSessionIdRef.current || currentSessionId;
      if (!sessionId) {
        console.log("No session ID available, letting backend create one");
      }

      console.log(
        "Uploading file with session ID:",
        sessionId || "null (will be created by backend)"
      );
      console.log("Ref session ID:", currentSessionIdRef.current);
      console.log("State session ID:", currentSessionId);
      console.log("About to call streamSummary with sessionId:", sessionId);

      let summary = "";
      const confirmedSessionId = await streamSummary(
        file,
        sessionId,
        (chunk) => {
          summary += chunk;
          setStreamingMessage(summary);
        },
        (status, message) => {
          switch (status) {
            case "processing":
              setStreamingMessage("📄 Processing PDF file...");
              break;
            case "embeddings":
              setStreamingMessage(
                "🔍 Creating embeddings and analyzing document..."
              );
              break;
            case "summary":
              setStreamingMessage("📝 Generating document summary...");
              break;
            case "complete":
              setStreamingMessage("✅ Summary generated successfully!");
              break;
            case "error":
              setUploadError(message);
              setStreamingMessage("");
              break;
          }
        }
      );

      // Update session ID
      if (confirmedSessionId) {
        if (!sessionId || confirmedSessionId !== sessionId) {
          console.log("Backend confirmed session ID:", confirmedSessionId);

          setCurrentSessionId(confirmedSessionId);
          currentSessionIdRef.current = confirmedSessionId;

          if (!sessionId) {
            const newSession: ChatSession = {
              session_id: confirmedSessionId,
              title: `Document: ${file.name}`,
              created_at: new Date().toISOString(),
            };
            setSessions((prev) => [newSession, ...prev]);
          } else {
            setSessions((prev) => {
              const updatedSessions = prev.map((session) =>
                session.session_id === sessionId
                  ? { ...session, session_id: confirmedSessionId }
                  : session
              );
              return updatedSessions;
            });
          }
        } else {
          console.log("Backend confirmed same session ID:", confirmedSessionId);
        }
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          message: summary,
          created_at: new Date().toISOString(),
        },
      ]);
      setStreamingMessage("");
      return true;
    } catch {
      setUploadError("Failed to upload or stream summary.");
      setStreamingMessage("");
      return false;
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileSelect = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0];
    if (file) {
      await uploadFile(file);
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleDrop = async (event: React.DragEvent) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) {
      await uploadFile(file);
    }
  };

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault();
  };

  const sendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage = inputValue.trim();
    setInputValue("");
    setIsLoading(true);
    setStreamingMessage("");
    isStreamingRef.current = true;

    const sessionIdToUse = currentSessionIdRef.current || currentSessionId;
    console.log("Sending message with session ID:", sessionIdToUse);
    console.log("Ref session ID:", currentSessionIdRef.current);
    console.log("State session ID:", currentSessionId);

    const newUserMessage: Message = {
      role: "user",
      message: userMessage,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, newUserMessage]);

    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      connectWebSocket();
      await new Promise((resolve) => setTimeout(resolve, 100));
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const messageData = {
        query: userMessage,
        session_id: sessionIdToUse,
      };
      console.log("Sending WebSocket message:", messageData);
      wsRef.current.send(JSON.stringify(messageData));
    } else {
      console.error("WebSocket not connected");
      setIsLoading(false);
      isStreamingRef.current = false;
    }
  };

  useEffect(() => {
    if (!isLoading || !streamingMessage) return;

    const timeout = setTimeout(() => {
      if (streamingMessage && isStreamingRef.current) {
        const newAiMessage: Message = {
          role: "ai",
          message: streamingMessage,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, newAiMessage]);
        setStreamingMessage("");
        setIsLoading(false);
        isStreamingRef.current = false;
      }
    }, 1000);

    return () => clearTimeout(timeout);
  }, [streamingMessage, isLoading]);

  const startNewChat = () => {
    setCurrentSessionId(null);
    currentSessionIdRef.current = null;
    setMessages([]);
    setStreamingMessage("");
    setIsLoading(false);
    isStreamingRef.current = false;
    setUploadError(null);
    setUploadProgress(null);
  };

  const selectSession = (sessionId: string) => {
    setCurrentSessionId(sessionId);
    currentSessionIdRef.current = sessionId;
    setStreamingMessage("");
    setIsLoading(false);
    isStreamingRef.current = false;
    setUploadError(null);
    setUploadProgress(null);
    fetchChatHistory(sessionId);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const copyMessage = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const isEmptyChat = messages.length === 0 && !streamingMessage;

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        onStartNewChat={startNewChat}
        onSelectSession={selectSession}
      />
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="bg-white border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-8">
              <h1 className="text-xl font-bold bg-gradient-to-r from-teal-600 via-purple-600 to-pink-500 text-transparent bg-clip-text">
                Lawroom AI
              </h1>

              <nav className="hidden md:flex items-center gap-6">
                <a href="#" className="text-gray-600 hover:text-gray-900">
                  Home
                </a>
                <a href="#" className="text-gray-600 hover:text-gray-900">
                  About Us
                </a>
                <a href="#" className="text-gray-600 hover:text-gray-900">
                  Legal AI Chat
                </a>
                <a href="#" className="text-gray-600 hover:text-gray-900">
                  Smart Drafting
                </a>
                <a href="#" className="text-gray-600 hover:text-gray-900">
                  Upcoming Features
                </a>
              </nav>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-600">Akash Gupta</span>
                <div className="w-8 h-8 bg-red-500 rounded-full flex items-center justify-center">
                  <span className="text-white text-sm font-medium">A</span>
                </div>
              </div>
              <button className="bg-cyan-400 text-white px-4 py-2 rounded-lg text-sm font-medium">
                Try Now
              </button>
            </div>
          </div>
        </header>

        {/* Upload Progress Bar */}
        {uploadProgress && (
          <div className="bg-blue-50 border-b border-blue-200 px-6 py-2">
            <div className="max-w-4xl mx-auto">
              <div className="flex items-center gap-4">
                <span className="text-sm text-blue-600">Uploading file...</span>
                <div className="flex-1 bg-blue-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${uploadProgress.percentage}%` }}
                  />
                </div>
                <span className="text-sm text-blue-600">
                  {uploadProgress.percentage}%
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Upload Error */}
        {uploadError && (
          <div className="bg-red-50 border-b border-red-200 px-6 py-2">
            <div className="max-w-4xl mx-auto">
              <div className="flex items-center gap-2">
                <span className="text-sm text-red-600">❌ {uploadError}</span>
                <button
                  onClick={() => setUploadError(null)}
                  className="text-red-400 hover:text-red-600"
                >
                  ×
                </button>
              </div>
            </div>
          </div>
        )}

        <ChatArea
          messages={messages}
          streamingMessage={streamingMessage}
          isEmptyChat={isEmptyChat}
          copyMessage={copyMessage}
          messagesEndRef={messagesEndRef}
        />
        <MessageInput
          inputValue={inputValue}
          setInputValue={setInputValue}
          isLoading={isLoading}
          sendMessage={sendMessage}
          handleKeyPress={handleKeyPress}
          inputRef={inputRef}
          onFileUpload={() => fileInputRef.current?.click()}
          isUploading={isUploading}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        />

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx,.txt"
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>
    </div>
  );
}
