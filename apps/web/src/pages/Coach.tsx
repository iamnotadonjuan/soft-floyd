import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import type {
  CoachConversationOut,
  CoachMemoryNoteOut,
  CoachMessageOut,
  CoachSourceOut,
} from "../api/types";
import CoachText from "../components/CoachText";

const SUGGESTIONS = [
  "How did my last month of riding go?",
  "What should I work on to climb better?",
  "Plan my next week of training around my schedule.",
];

interface Draft {
  text: string;
  status: string | null;
  sources: CoachSourceOut[];
}

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

function SourceList({ sources }: { sources: CoachSourceOut[] }) {
  if (!sources.length) return null;
  return (
    <ul className="mt-3 flex flex-wrap gap-2" aria-label="Book sources">
      {sources.map((s) => (
        <li key={`${s.book_id}-${s.page_start}`} className="status-pill" data-tone="neutral">
          {s.title}, p. {s.page_start}{s.page_end !== s.page_start ? `–${s.page_end}` : ""}
        </li>
      ))}
    </ul>
  );
}

// The coach chat (exec-plan 0007). Dashboard only offers this view once a
// ride source is connected; the server enforces cycling-only scope.
export default function Coach({ onBack }: { onBack: () => void }) {
  const [conversations, setConversations] = useState<CoachConversationOut[] | null>(null);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<CoachMessageOut[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<CoachMemoryNoteOut[]>([]);
  const abort = useRef<AbortController | null>(null);
  const threadEnd = useRef<HTMLDivElement>(null);
  const busy = draft !== null;

  useEffect(() => {
    let active = true;
    api.listCoachConversations()
      .then((items) => {
        if (!active) return;
        setConversations(items);
        if (items[0]) void openConversation(items[0].id);
      })
      .catch((e) => { if (active) setError(errorText(e)); });
    refreshNotes();
    return () => { active = false; abort.current?.abort(); };
  }, []);

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ block: "end" });
  }, [messages, draft?.text]);

  function refreshNotes() {
    api.listCoachMemory().then(setNotes).catch(() => { /* memory panel is optional */ });
  }

  async function openConversation(id: number) {
    setError(null);
    setActiveId(id);
    setMessages([]);
    try {
      setMessages((await api.getCoachConversation(id)).messages);
    } catch (e) {
      setError(errorText(e));
    }
  }

  function startNew() {
    if (busy) return;
    setActiveId(null);
    setMessages([]);
    setError(null);
  }

  async function removeConversation(id: number) {
    try {
      await api.deleteCoachConversation(id);
      setConversations((items) => items?.filter((c) => c.id !== id) ?? null);
      if (id === activeId) startNew();
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function removeNote(id: number) {
    try {
      await api.deleteCoachMemory(id);
      setNotes((items) => items.filter((n) => n.id !== id));
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function send(text: string) {
    text = text.trim();
    if (!text || busy) return;
    setError(null);
    setInput("");
    setDraft({ text: "", status: null, sources: [] });
    const optimistic: CoachMessageOut = {
      id: -Date.now(), role: "user", content: text, sources: [], created_at: new Date().toISOString(),
    };
    setMessages((items) => [...items, optimistic]);
    const controller = new AbortController();
    abort.current = controller;
    try {
      let id = activeId;
      if (id === null) {
        const created = await api.createCoachConversation();
        id = created.id;
        setActiveId(id);
      }
      await api.streamCoachMessage(id, text, (event) => {
        if (event.type === "delta" && event.text) {
          setDraft((d) => d && { ...d, text: d.text + event.text, status: null });
        } else if (event.type === "tool_status" && event.text) {
          setDraft((d) => d && { ...d, status: event.text ?? null });
        } else if (event.type === "sources" && event.sources) {
          setDraft((d) => d && { ...d, sources: event.sources ?? [] });
        } else if (event.type === "done" && event.message) {
          setMessages((items) => [...items, event.message!]);
        } else if (event.type === "error") {
          setError(event.text ?? "The coach couldn't answer. Please try again.");
        }
      }, controller.signal);
      setConversations(await api.listCoachConversations());
      refreshNotes();
    } catch (e) {
      if (!controller.signal.aborted) {
        setError(errorText(e));
        // A turn refused up front (budget, no API key) was never saved.
        setMessages((items) => items.filter((m) => m.id !== optimistic.id));
        setInput(text);
      }
    } finally {
      setDraft(null);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void send(input);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(input);
    }
  }

  return (
    <main className="app-shell">
      <div className="page-wrap">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <span className="brand">Soft Floyd / Coach</span>
          <button onClick={onBack} className="text-button">← Back to rides</button>
        </header>

        <div className="grid gap-6 lg:grid-cols-[17rem_1fr]">
          <aside className="space-y-5" aria-label="Conversations and memory">
            <button onClick={startNew} disabled={busy} className="primary-button w-full">New conversation</button>
            <nav className="surface p-3" aria-label="Conversations">
              {conversations === null ? <p className="body-muted p-2 text-sm">Loading…</p> :
                conversations.length === 0 ? <p className="body-muted p-2 text-sm">No conversations yet.</p> :
                <ul className="space-y-1">
                  {conversations.map((c) => (
                    <li key={c.id} className="coach-thread-row" data-active={c.id === activeId}>
                      <button className="coach-thread-title" disabled={busy} onClick={() => void openConversation(c.id)}
                        aria-current={c.id === activeId ? "true" : undefined}>{c.title}</button>
                      <button className="coach-thread-delete" disabled={busy} onClick={() => void removeConversation(c.id)}
                        aria-label={`Delete conversation ${c.title}`}>×</button>
                    </li>
                  ))}
                </ul>}
            </nav>
            <details className="surface-soft p-4">
              <summary className="eyebrow cursor-pointer">What the coach remembers ({notes.length})</summary>
              {notes.length === 0 ?
                <p className="body-muted mt-3 text-sm">Nothing yet. Tell the coach about injuries, schedule or preferences and it will keep them in mind.</p> :
                <ul className="mt-3 space-y-2">
                  {notes.map((n) => (
                    <li key={n.id} className="flex items-start justify-between gap-2 text-sm">
                      <span>{n.text}</span>
                      <button className="coach-thread-delete" onClick={() => void removeNote(n.id)}
                        aria-label={`Forget: ${n.text}`}>×</button>
                    </li>
                  ))}
                </ul>}
            </details>
          </aside>

          <section className="surface coach-panel" aria-label="Coach chat">
            <div className="coach-thread" aria-live="polite">
              {messages.length === 0 && !busy && (
                <div className="py-6">
                  <p className="eyebrow mb-3">Your cycling coach</p>
                  <h1 className="section-title">Ask about your rides, training, or how to get faster.</h1>
                  <p className="body-muted mt-3 max-w-xl">The coach reads your synced rides and imported training books, and remembers what you tell it. It only talks cycling.</p>
                  <div className="mt-5 flex flex-wrap gap-2">
                    {SUGGESTIONS.map((s) => (
                      <button key={s} className="choice-chip" onClick={() => void send(s)}>{s}</button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((m) => (
                <article key={m.id} className="coach-message" data-role={m.role}>
                  {m.role === "assistant" ? <CoachText text={m.content} /> : <p className="whitespace-pre-wrap">{m.content}</p>}
                  <SourceList sources={m.sources} />
                </article>
              ))}
              {draft && (
                <article className="coach-message" data-role="assistant" aria-busy="true">
                  {draft.text ? <CoachText text={draft.text} /> : null}
                  <p className="body-muted text-sm">{draft.status ? `${draft.status}…` : draft.text ? "" : "Thinking…"}</p>
                  <SourceList sources={draft.sources} />
                </article>
              )}
              <div ref={threadEnd} />
            </div>

            {error && <p className="notice-error mx-5 mb-3" role="alert">{error}</p>}

            <form onSubmit={onSubmit} className="coach-composer">
              <label htmlFor="coach-input" className="sr-only">Message the coach</label>
              <textarea id="coach-input" className="form-field" rows={2} maxLength={4000} value={input}
                placeholder="Ask your coach… (Shift+Enter for a new line)"
                onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown} />
              <button type="submit" className="primary-button" disabled={busy || !input.trim()}>
                {busy ? "Coaching…" : "Send"}
              </button>
            </form>
          </section>
        </div>
      </div>
    </main>
  );
}
