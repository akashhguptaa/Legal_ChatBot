import React from "react";
import { Plus } from "lucide-react";

interface ChatSession {
  session_id: string;
  title: string;
  created_at: string;
}

interface SidebarProps {
  sessions: ChatSession[];
  currentSessionId: string | null;
  onStartNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
}

const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  currentSessionId,
  onStartNewChat,
  onSelectSession,
}) => (
  <div className="w-64 bg-white border-r border-gray-200 flex flex-col">
    <div className="p-4 border-b border-gray-200">
      <button
        onClick={onStartNewChat}
        className="w-full flex items-center gap-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg border border-gray-200"
      >
        <Plus size={16} />
        New chat
      </button>
    </div>
    <div className="flex-1 overflow-y-auto">
      <div className="p-4">
        <h3 className="text-sm font-medium text-gray-500 mb-2">Recent Chats</h3>
        <div className="space-y-1">
          {sessions.map((session: ChatSession) => (
            <button
              key={session.session_id}
              onClick={() => onSelectSession(session.session_id)}
              className={`w-full text-left p-2 rounded-lg text-sm hover:bg-gray-100 ${
                currentSessionId === session.session_id
                  ? "bg-blue-50 text-blue-600"
                  : "text-gray-700"
              }`}
            >
              {session.title}
            </button>
          ))}
        </div>
      </div>
    </div>
    <div className="p-4 border-t border-gray-200">
      <button className="w-full bg-blue-900 text-white py-2 px-4 rounded-lg text-sm font-medium">
        Join Premium Waitlist
      </button>
    </div>
  </div>
);

export default Sidebar;
