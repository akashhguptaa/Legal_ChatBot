"use client";

import React, { useState, useEffect, useRef } from "react";
import Sidebar from "@/components/Sidebar";
import ChatArea from "../components/ChatArea";
import MessageInput from "../components/MessageInput";

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

export default function LawroomAI() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingMessage, setStreamingMessage] = useState("");

  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingMessage]);

  useEffect(() => {
    fetchSessions(); // Only on mount
  }, []);

  // Open WebSocket once per session or on mount
  useEffect(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      connectWebSocket();
    }
    // Clean up on unmount
    return () => {
      wsRef.current?.close();
    };
  }, [currentSessionId]);

  const connectWebSocket = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }
    wsRef.current = new WebSocket("ws://localhost:8000/ws/chat");
    wsRef.current.onopen = () => {};
    wsRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.session_id) {
          setCurrentSessionId(data.session_id);
        }
      } catch {
        // This is streaming text
        setStreamingMessage((prev) => prev + event.data);
      }
    };
    wsRef.current.onclose = () => {};
    wsRef.current.onerror = (error) => {
      console.error("WebSocket error:", error);
    };
  };

  const fetchSessions = async () => {
    try {
      const response = await fetch("http://localhost:8000/sessions");
      const data = await response.json();
      if (data.status === "success") {
        setSessions(data.sessions);
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

  const sendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;
    const userMessage = inputValue.trim();
    setInputValue("");
    setIsLoading(true);
    setStreamingMessage("");
    // Add user message to UI immediately
    const newUserMessage: Message = {
      role: "user",
      message: userMessage,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, newUserMessage]);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          query: userMessage,
          session_id: currentSessionId,
        })
      );
    }
  };

  // Listen for end of streaming and finalize AI message
  useEffect(() => {
    if (!isLoading) return;
    // If streamingMessage is being updated, wait for a pause (e.g., 500ms of no new data)
    const timeout = setTimeout(() => {
      if (streamingMessage) {
        const newAiMessage: Message = {
          role: "ai",
          message: streamingMessage,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, newAiMessage]);
        setStreamingMessage("");
        setIsLoading(false);
      }
    }, 500);
    return () => clearTimeout(timeout);
  }, [streamingMessage, isLoading]);

  const startNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setStreamingMessage("");
    connectWebSocket();
  };

  // Only call fetchChatHistory when a session is selected
  const selectSession = (sessionId: string) => {
    setCurrentSessionId(sessionId);
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
        />
      </div>
    </div>
  );
}
