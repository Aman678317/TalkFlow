import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MessageSquare, Send } from 'lucide-react';
import type { Meeting } from '@globaltalk/shared-types';
import { api } from '@/lib/api';
import { Badge, Button, Card, EmptyState, Input, Select } from '@/components/ui';
import { useLanguages } from '@/hooks/useLanguages';
import { useAuth } from '@/stores/auth';
import { timeAgo } from '@/lib/utils';

interface ChatMsg {
  id: string; seq: number; sender_name: string; original_text: string;
  detected_lang: string; kind: string;
  translations_json: Record<string, { text: string | null; error?: string }>;
  created_at: string;
}

/**
 * Multilingual chat outside a live meeting (PDD §19): pick a meeting thread,
 * view Original / My language / Both. Originals are never replaced.
 */
export default function ChatPage() {
  const user = useAuth((s) => s.user);
  const { data: langs } = useLanguages();
  const [meetingId, setMeetingId] = useState('');
  const [view, setView] = useState<'original' | 'mine' | 'both'>('both');
  const [myLang, setMyLang] = useState(user?.hear_lang ?? 'en');
  const [draft, setDraft] = useState('');

  const meetings = useQuery({
    queryKey: ['meetings'],
    queryFn: () => api<Meeting[]>('/api/v1/meetings?limit=50'),
  });
  const messages = useQuery({
    queryKey: ['chat', meetingId],
    queryFn: () => api<ChatMsg[]>(`/api/v1/meetings/${meetingId}/chat`),
    enabled: !!meetingId,
    refetchInterval: 3000,
  });

  async function send() {
    const text = draft.trim();
    if (!text || !meetingId) return;
    await api(`/api/v1/meetings/${meetingId}/chat`, { method: "POST", body: { text, target_langs: [myLang] } });
    setDraft('');
    void messages.refetch();
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4 px-4 py-8 sm:px-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Chat</h1>
        <p className="mt-1 text-sm text-slate-500">
          Multilingual threads — every message keeps its original; translations attach per reader.
        </p>
      </div>

      <Card className="flex flex-wrap items-end gap-3 p-4">
        <Select label="Conversation" className="min-w-56" value={meetingId}
                onChange={(e) => setMeetingId(e.target.value)}>
          <option value="">Choose a meeting…</option>
          {meetings.data?.map((m) => (
            <option key={m.id} value={m.id}>{m.title} ({m.status})</option>))}
        </Select>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700" htmlFor="chat-view">Show</label>
          <div role="group" id="chat-view" className="flex overflow-hidden rounded-xl2 border border-slate-300">
            {(['original', 'mine', 'both'] as const).map((v) => (
              <button key={v} onClick={() => setView(v)} aria-pressed={view === v}
                      className={`px-3 py-1.5 text-xs font-medium capitalize ${view === v ? 'bg-iris-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
                {v === 'mine' ? 'My language' : v}
              </button>
            ))}
          </div>
        </div>
        <Select label="My language" className="min-w-36" value={myLang}
                onChange={(e) => setMyLang(e.target.value)}>
          {(langs ?? []).map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
        </Select>
      </Card>

      {!meetingId ? (
        <EmptyState icon={<MessageSquare className="h-8 w-8" />} title="Pick a conversation"
          hint="Chat threads belong to meetings. Join a live meeting for realtime chat, or select one above to read and post." />
      ) : (
        <Card className="flex h-[32rem] flex-col">
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {(messages.data?.length ?? 0) === 0 && (
              <p className="pt-10 text-center text-sm text-slate-400">No messages yet.</p>
            )}
            {messages.data?.map((m) => {
              const tr = m.translations_json?.[myLang]?.text;
              const showOriginal = view === 'original' || view === 'both';
              const showTr = (view === 'mine' || view === 'both') && tr && m.detected_lang !== myLang;
              return (
                <div key={m.id} className="max-w-[85%] rounded-2xl bg-slate-50 p-3">
                  <div className="mb-1 flex items-center gap-2 text-[11px] text-slate-400">
                    <span className="font-semibold text-iris-600">{m.sender_name}</span>
                    <Badge tone="neutral">{m.detected_lang}</Badge>
                    <span>{timeAgo(m.created_at)}</span>
                  </div>
                  {showOriginal && <p className="text-sm text-slate-800">{m.original_text}</p>}
                  {showTr && (
                    <p className={`text-sm font-medium text-slate-900 ${showOriginal ? 'mt-1 border-t border-slate-200 pt-1' : ''}`}>
                      {tr}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
          <div className="flex gap-2 border-t border-slate-100 p-3">
            <Input aria-label="Chat message" placeholder="Write in any language…"
                   value={draft} onChange={(e) => setDraft(e.target.value)}
                   onKeyDown={(e) => e.key === 'Enter' && send()} />
            <Button onClick={send} aria-label="Send"><Send className="h-4 w-4" /></Button>
          </div>
        </Card>
      )}
    </div>
  );
}
