import React from "react";
import { RefreshCw, Send, Paperclip } from "lucide-react";

interface MessageInputProps {
  inputValue: string;
  setInputValue: (value: string) => void;
  isLoading: boolean;
  sendMessage: () => void;
  handleKeyPress: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  // File upload props
  onFileUpload?: () => void;
  isUploading?: boolean;
  onDrop?: (e: React.DragEvent) => void;
  onDragOver?: (e: React.DragEvent) => void;
}

const MessageInput: React.FC<MessageInputProps> = ({
  inputValue,
  setInputValue,
  isLoading,
  sendMessage,
  handleKeyPress,
  inputRef,
  onFileUpload,
  isUploading = false,
  onDrop,
  onDragOver,
}) => (
  <div className="border-t border-gray-200 bg-white p-4">
    <div className="max-w-4xl mx-auto">
      <div className="flex items-end gap-2">
        <div 
          className="flex-1 relative"
          onDrop={onDrop}
          onDragOver={onDragOver}
        >
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask anything about Indian law..."
            className="w-full px-4 py-3 pr-20 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent resize-none text-gray-600"
            rows={1}
            disabled={isLoading || isUploading}
          />
          <div className="absolute right-3 top-3 flex items-center gap-2">
            {/* File upload button */}
            {onFileUpload && (
              <button
                onClick={onFileUpload}
                disabled={isLoading || isUploading}
                className="p-1 text-gray-600 hover:text-gray-900 disabled:opacity-50"
                title="Upload file"
              >
                <Paperclip size={20} />
              </button>
            )}
            
            {/* Send button */}
            <button
              onClick={sendMessage}
              disabled={!inputValue.trim() || isLoading || isUploading}
              className="p-1 text-gray-600 hover:text-gray-900 disabled:opacity-50"
            >
              {isLoading ? (
                <RefreshCw size={20} className="animate-spin" />
              ) : (
                <Send size={20} />
              )}
            </button>
          </div>
        </div>
      </div>
      <div className="mt-3 text-center">
        <p className="text-xs text-gray-500">
          Disclaimer: Lawroom AI provides informational assistance and is not a
          substitute for professional legal advice.
          {onFileUpload && (
            <>
              <br />
              You can upload PDF, DOC, DOCX, or TXT files (max 100MB). Drag & drop or click the paperclip icon.
            </>
          )}
        </p>
      </div>
    </div>
  </div>
);

export default MessageInput;