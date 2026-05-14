import { useEffect, useRef, useState } from "react";
import { getMessages, streamChat, triggerAnalysis } from "../api/client";
import type { ChatMessage } from "../api/types";

interface Props {
  activityId: number;
}

interface ToolPill {
  id: number;
  name: string;
}

export default function ChatPanel({ activityId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [toolPills, setToolPills] = useState<ToolPill[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const pillId = useRef(0);

  useEffect(() => {
    setLoading(true);
    getMessages(activityId)
      .then((res) => setMessages(res.messages))
      .finally(() => setLoading(false));
  }, [activityId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  function handleTrigger() {
    setTriggering(true);
    triggerAnalysis(activityId)
      .then(() => getMessages(activityId).then((res) => setMessages(res.messages)))
      .finally(() => setTriggering(false));
  }

  function handleSend() {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    setStreaming(true);
    setStreamingText("");
    setToolPills([]);

    const userMsg: ChatMessage = {
      id: Date.now(),
      role: "user",
      text,
      tokens_in: null,
      tokens_out: null,
      cache_read: null,
      cost_usd: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    cancelRef.current = streamChat(
      activityId,
      text,
      (chunk) => setStreamingText((t) => t + chunk),
      (toolName) => {
        const id = ++pillId.current;
        setToolPills((p) => [...p, { id, name: toolName }]);
      },
      () => {
        // done — reload messages from DB
        setStreaming(false);
        setStreamingText("");
        setToolPills([]);
        getMessages(activityId).then((res) => setMessages(res.messages));
      },
      (err) => {
        setStreaming(false);
        setStreamingText("");
        setToolPills([]);
        console.error("chat error", err);
      },
    );
  }

  const hasMessages = messages.filter((m) => m.role === "assistant").length > 0;

  return (
    <div className="flex flex-col h-full min-h-0">
      <h2 className="text-sm font-semibold text-gray-700 mb-3">Soft Floyd</h2>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto space-y-3 mb-3 pr-1">
        {loading && <p className="text-sm text-gray-400">Loading…</p>}

        {!loading && !hasMessages && !streaming && (
          <div className="text-center py-6">
            <p className="text-sm text-gray-400 mb-3">No analysis yet.</p>
            <button
              onClick={handleTrigger}
              disabled={triggering}
              className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {triggering ? "Generating…" : "Generate Soft Floyd's analysis"}
            </button>
          </div>
        )}

        {messages
          .filter((m) => m.role !== "user" || m.text.length < 500)
          .map((m) => (
            <div
              key={m.id}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${
                  m.role === "user"
                    ? "bg-indigo-600 text-white rounded-br-sm"
                    : "bg-white border border-gray-100 text-gray-800 rounded-bl-sm shadow-sm"
                }`}
              >
                {m.text}
                {m.role === "assistant" && m.cost_usd != null && (
                  <span className="block mt-1 text-xs text-gray-400">
                    ${m.cost_usd.toFixed(4)}
                    {m.cache_read ? " (cached)" : ""}
                  </span>
                )}
              </div>
            </div>
          ))}

        {/* Tool pills */}
        {toolPills.map((p) => (
          <div key={p.id} className="flex justify-start">
            <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded-full">
              checking {p.name.replace(/_/g, " ")}…
            </span>
          </div>
        ))}

        {/* Streaming bubble */}
        {streaming && streamingText && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-2xl rounded-bl-sm px-3 py-2 text-sm bg-white border border-gray-100 text-gray-800 shadow-sm whitespace-pre-wrap">
              {streamingText}
              <span className="animate-pulse">▍</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder="Ask Soft Floyd…"
          disabled={streaming}
          className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:bg-gray-50"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || streaming}
          className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-40 transition-colors"
        >
          Send
        </button>
      </div>
    </div>
  );
}
