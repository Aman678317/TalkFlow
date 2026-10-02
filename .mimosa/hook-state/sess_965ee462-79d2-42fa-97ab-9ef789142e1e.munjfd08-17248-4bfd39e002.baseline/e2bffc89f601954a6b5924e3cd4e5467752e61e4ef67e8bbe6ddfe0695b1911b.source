import React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { MeetingSocket } from "../lib/ws";
import type { Meeting, RealtimeEvent } from "../lib/types";
import { Badge, Button, Card, EmptyState, Input } from "../components/ui";
import { useAuth } from "../stores/auth";
import { useLanguages, languageLabel } from "../hooks/useLanguages";

interface ChatLine { id: string; sender: string; original: string; language: string; translated?: string; mine: boolean; }

/**
 * Chat rooms: text-first multilingual rooms backed by the same meetings + realtime
 * protocol (chat events over WebSocket). Originals are never replaced; translations
 * render beneath per the display toggle. For voice, open the full meeting room.
 */
export default function ChatRooms() {
  const { user } = useAuth();
  const { data: langs } = useLanguages();
  const [params, setParams] = useSearchParams();
  const activeId = params.get("room");
  const [listenLang, setListenLang] = React.useState(user?.default_language || "en");
  const [draft, setDraft] = React.useState("");
  const [lines, setLines] = React.useState<ChatLine[]>([]);
  const [connected, setConnected] = React.useState(false);
  const socketRef = React.useRef<MeetingSocket | null>(null);
  const endRef = React.useRef<HTMLDivElement>(null);

  const meetingsQ = useQuery({ queryKey: ["meetings"], queryFn: () => api<Meeting[]>("/api/v1/meetings") });
  const historyQ = useQuery({
    queryKey: ["chat-history", activeId, listenLang],
    queryFn: () => api<any[]>(`/api/v1/meetings/${activeId}/chat?listening_language=${listenLang}`),
    enabled: !!activeId,
  });

  React.useEffect(() => {
    if (historyQ.data) {
      setLines(historyQ.data.map((m) => ({
        id: m.id, sender: m.sender, original: m.original_text, language: m.language,
        translated: m.translated_text ?? undefined, mine: false,
      })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyQ.data]);

  React.useEffect(() => {
    if (!activeId) return;
    const meeting = (meetingsQ.data ?? []).find((m) => m.id === activeId);
    if (!meeting) return;
    const socket = new MeetingSocket({
      meetingId: activeId,
      joinToken: meeting.join_token,
      displayName: user?.full_name || "Guest",
      preferences: {
        speaking_language: "AUTO", listening_language: listenLang,
        audio_mode: "original", caption_mode: "original", latency_mode: "balanced",
      },
      onStateChange: (s) => setConnected(s === "joined"),
      onBinary: () => { /* chat-only */ },
      onEvent: (evt: RealtimeEvent) => {
        if (evt.type === "chat.message") {
          setLines((prev) => prev.some((l) => l.id === evt.message_id) ? prev : [...prev, {
            id: evt.message_id as string, sender: (evt.display_name as string) || "?",
            original: evt.original_text as string, language: (evt.language as string) || "",
            mine: false,
          }]);
        } else if (evt.type === "chat.translation") {
          setLines((prev) => prev.map((l) =>
            l.id === evt.message_id ? { ...l, translated: evt.text as string } : l));
        }
      },
    });
    socketRef.current = socket;
    socket.connect();
    return () => socket.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, meetingsQ.data, listenLang]);

  React.useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [lines]);

  function send(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    socketRef.current?.sendChat(draft.trim());
    setDraft("");
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-4 p-4 lg:grid-cols-[280px_1fr] lg:p-6">
      <div className="space-y-2">
        <h1 className="text-lg font-bold text-ink-900">Chat rooms</h1>
        {(meetingsQ.data ?? []).map((m) => (
          <button key={m.id} onClick={() => setParams({ room: m.id })}
                  className={`gt-card w-full p-3 text-left transition hover:border-signal-300 ${activeId === m.id ? "border-signal-500 ring-2 ring-signal-500/20" : ""}`}>
            <p className="truncate text-sm font-semibold text-ink-900">{m.title}</p>
            <p className="text-[11px] text-ink-400">{m.status} · <Link className="text-signal-700 hover:underline" to={`/meeting/${m.id}`}>open voice room ↗</Link></p>
          </button>
        ))}
        {(meetingsQ.data ?? []).length === 0 && (
          <Card><EmptyState title="No rooms" body="Create a meeting first — every meeting has a multilingual chat." icon="💬"
            action={<Link to="/meetings"><Button size="sm">Go to meetings</Button></Link>} /></Card>
        )}
      </div>

      {activeId ? (
        <Card className="flex h-[70vh] flex-col !p-0" title={
          <span className="flex items-center gap-2">
            {(meetingsQ.data ?? []).find((m) => m.id === activeId)?.title}
            <Badge tone={connected ? "good" : "warn"}>{connected ? "● connected" : "connecting…"}</Badge>
          </span>}
          action={
            <label className="flex items-center gap-1.5 text-xs text-ink-500">
              Read in
              <select className="gt-input !w-36 !py-1 text-xs" value={listenLang} aria-label="Reading language"
                      onChange={(e) => setListenLang(e.target.value)}>
                {(langs ?? []).filter((l) => l.translation_supported).map((l) => (
                  <option key={l.code} value={l.code}>{l.name}</option>
                ))}
              </select>
            </label>
          }>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4" aria-live="polite">
            {lines.map((m) => (
              <div key={m.id} className={`max-w-[80%] rounded-xl p-2.5 text-sm ${m.mine ? "ml-auto bg-signal-50" : "bg-ink-50"}`}>
                <p className="mb-0.5 text-[11px] font-semibold text-ink-500">
                  {m.sender} {m.language && <Badge>{languageLabel(langs, m.language)}</Badge>}
                </p>
                <p className="text-ink-700">{m.original}</p>
                {m.translated && m.language !== listenLang && (
                  <p className="mt-1 border-t border-ink-100 pt-1 font-medium text-ink-900">{m.translated}</p>
                )}
              </div>
            ))}
            <div ref={endRef} />
          </div>
          <form onSubmit={send} className="flex gap-2 border-t border-ink-100 p-3">
            <Input value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Chat message"
                   placeholder="Write in any language — readers see it in theirs" className="flex-1" />
            <Button type="submit" disabled={!connected || !draft.trim()}>Send</Button>
          </form>
        </Card>
      ) : (
        <Card><EmptyState title="Pick a room" body="Select a meeting on the left to open its multilingual chat." icon="💬" /></Card>
      )}
    </div>
  );
}
