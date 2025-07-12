import React from "react";
import { Copy } from "lucide-react";
import ReactMarkdown from "react-markdown";

interface Message {
  role: "user" | "ai";
  message: string;
  created_at: string;
}

interface ChatAreaProps {
  messages: Message[];
  streamingMessage: string;
  isEmptyChat: boolean;
  copyMessage: (text: string) => void;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
}


const ChatArea: React.FC<ChatAreaProps> = ({
  messages,
  streamingMessage,
  isEmptyChat,
  copyMessage,
  messagesEndRef,
}) => {
  const messageWidth = "min(80%, 48rem)";

  return (
    <div className="flex-1 overflow-y-auto scroll-smooth">
      {isEmptyChat ? (
        <div className="flex flex-col items-center justify-center h-full px-4">
          <div className="text-center max-w-2xl">
            <h1 className="text-4xl font-bold mb-4 bg-gradient-to-r from-teal-900 via-purple-500 to-red-500 text-transparent bg-clip-text">
              Lawroom AI
            </h1>
            <p className="text-gray-600 mb-8">
              Your legal research assistant for Law
            </p>
          </div>
        </div>
      ) : (
        <div className="w-full max-w-4xl mx-auto px-4 py-6 space-y-4">
          {messages.map((message, index) => (
            <div
              key={index}
              className="relative"
              style={{ minHeight: "4.5rem" }}
            >
              {message.role === "user" ? (
                <div className="flex justify-end w-full">
                  <div
                    className="bg-blue-600 text-white px-4 py-3 rounded-lg break-words"
                    style={{ width: messageWidth }}
                  >
                    <p className="whitespace-pre-wrap">{message.message}</p>
                  </div>
                </div>
              ) : (
                <div className="flex justify-start w-full">
                  <div
                    className="bg-gray-100 text-gray-900 px-4 py-3 rounded-lg break-words relative group"
                    style={{ width: messageWidth }}
                  >
                    <ReactMarkdown
                      components={{
                        h1: ({ children }) => (
                          <h1 className="text-xl font-bold mb-3">{children}</h1>
                        ),
                        h2: ({ children }) => (
                          <h2 className="text-lg font-semibold mb-2">
                            {children}
                          </h2>
                        ),
                        p: ({ children }) => (
                          <p className="mb-2 leading-normal">{children}</p>
                        ),
                        ul: ({ children }) => (
                          <ul className="list-disc list-inside mb-2 pl-4 space-y-1">
                            {children}
                          </ul>
                        ),
                        li: ({ children }) => (
                          <li className="leading-tight">{children}</li>
                        ),
                      }}
                    >
                      {message.message}
                    </ReactMarkdown>
                    <button
                      onClick={() => copyMessage(message.message)}
                      className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <Copy
                        size={16}
                        className="text-gray-500 hover:text-gray-700"
                      />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Only show streaming message if it has content */}
          {streamingMessage && streamingMessage.trim() && (
            <div className="relative" style={{ minHeight: "4.5rem" }}>
              <div className="flex justify-start w-full">
                <div
                  className="bg-gray-100 text-gray-900 px-4 py-3 rounded-lg break-words"
                  style={{ width: messageWidth }}
                >
                  <ReactMarkdown
                    components={{
                      h1: ({ children }) => (
                        <h1 className="text-xl font-bold mb-3">{children}</h1>
                      ),
                      p: ({ children }) => (
                        <p className="mb-2 leading-normal">{children}</p>
                      ),
                      ul: ({ children }) => (
                        <ul className="list-disc list-inside mb-2 pl-4 space-y-1">
                          {children}
                        </ul>
                      ),
                      li: ({ children }) => (
                        <li className="leading-tight">{children}</li>
                      ),
                    }}
                  >
                    {streamingMessage}
                  </ReactMarkdown>
                  <div className="absolute bottom-2 right-3 flex space-x-1">
                    {[1, 2, 3].map((i) => (
                      <div
                        key={i}
                        className="w-2 h-2 bg-gray-400 rounded-full"
                        style={{
                          animation: `pulse 1.5s ease-in-out ${
                            i * 0.2
                          }s infinite`,
                          opacity: 0.7,
                        }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}
    </div>
  );
};

export default ChatArea;
