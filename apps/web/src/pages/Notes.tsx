import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BookmarkCheck,
  BookmarkPlus,
  Search,
  Volume2,
  Copy,
  Check,
  Trash2,
  ExternalLink,
  Tag,
  Plus,
  X,
  Edit3,
  Star,
  Clock,
  ArrowRight,
  Info,
  Layers,
} from 'lucide-react';
import { api, friendlyMessage } from '../lib/api';
import { useLanguages } from '../hooks/useLanguages';
import { Button, Spinner } from '../components/ui';
import { toast } from '../stores/toasts';

interface Annotation {
  id: string;
  text: string;
  start: number;
  end: number;
  tag: string;
  comment: string;
  color?: string;
}

interface NoteItem {
  id: string;
  org_id?: string | null;
  user_id?: string | null;
  translation_id?: string | null;
  title: string;
  source_text: string;
  translated_text: string;
  source_lang: string;
  target_lang: string;
  note: string;
  tags: string[];
  annotations: Annotation[];
  is_favorite: boolean;
  created_at: string;
  updated_at: string;
  highlight_source?: string | null;
  highlight_target?: string | null;
  highlight_note?: string | null;
}

interface NoteSearchResponse {
  items: NoteItem[];
  total: number;
  query?: string | null;
  latency_ms: number;
  available_tags: string[];
  languages_represented: string[];
}

const TAG_COLORS: Record<string, string> = {
  vocabulary: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  idiom: 'bg-purple-50 text-purple-700 border-purple-200',
  grammar: 'bg-blue-50 text-blue-700 border-blue-200',
  legal: 'bg-amber-50 text-amber-700 border-amber-200',
  review: 'bg-rose-50 text-rose-700 border-rose-200',
  business: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  technical: 'bg-cyan-50 text-cyan-700 border-cyan-200',
  default: 'bg-slate-100 text-slate-700 border-slate-200',
};

export default function NotesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: langs } = useLanguages();

  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [selectedSourceLang, setSelectedSourceLang] = useState('');
  const [selectedTargetLang, setSelectedTargetLang] = useState('');
  const [selectedTag, setSelectedTag] = useState('');
  const [favoritesOnly, setFavoritesOnly] = useState(false);

  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [activeAudioId, setActiveAudioId] = useState<string | null>(null);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [editedNoteText, setEditedNoteText] = useState('');

  // Create Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newSourceText, setNewSourceText] = useState('');
  const [newTranslatedText, setNewTranslatedText] = useState('');
  const [newSourceLang, setNewSourceLang] = useState('en');
  const [newTargetLang, setNewTargetLang] = useState('bho');
  const [newNote, setNewNote] = useState('');
  const [newTagInput, setNewTagInput] = useState('');
  const [newTags, setNewTags] = useState<string[]>(['vocabulary']);

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery.trim());
    }, 150);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Fetch Notes Query
  const { data, isLoading } = useQuery<NoteSearchResponse>({
    queryKey: [
      'notes',
      debouncedQuery,
      selectedSourceLang,
      selectedTargetLang,
      selectedTag,
      favoritesOnly,
    ],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (debouncedQuery) p.set('q', debouncedQuery);
      if (selectedSourceLang) p.set('source_lang', selectedSourceLang);
      if (selectedTargetLang) p.set('target_lang', selectedTargetLang);
      if (selectedTag) p.set('tag', selectedTag);
      if (favoritesOnly) p.set('favorite', 'true');
      p.set('limit', '100');
      return await api<NoteSearchResponse>(`/api/v1/notes?${p.toString()}`);
    },
    staleTime: 5000,
  });

  // Delete Mutation
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api(`/api/v1/notes/${id}`, { method: 'DELETE' });
    },
    onSuccess: () => {
      toast.success('Note removed');
      queryClient.invalidateQueries({ queryKey: ['notes'] });
    },
    onError: (err) => toast.error('Failed to delete note', friendlyMessage(err)),
  });

  // Toggle Favorite Mutation
  const toggleFavMutation = useMutation({
    mutationFn: async ({ id, is_favorite }: { id: string; is_favorite: boolean }) => {
      return await api<NoteItem>(`/api/v1/notes/${id}`, {
        method: 'PATCH',
        body: { is_favorite },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes'] });
    },
  });

  // Update Note Comment Mutation
  const updateNoteMutation = useMutation({
    mutationFn: async ({ id, note }: { id: string; note: string }) => {
      return await api<NoteItem>(`/api/v1/notes/${id}`, {
        method: 'PATCH',
        body: { note },
      });
    },
    onSuccess: () => {
      toast.success('Note updated');
      setEditingNoteId(null);
      queryClient.invalidateQueries({ queryKey: ['notes'] });
    },
  });

  // Create Note Mutation
  const createMutation = useMutation({
    mutationFn: async () => {
      if (!newSourceText.trim() || !newTranslatedText.trim()) {
        throw new Error('Source text and translated text are required.');
      }
      return await api<NoteItem>('/api/v1/notes', {
        method: 'POST',
        body: {
          title: newTitle.trim() || undefined,
          source_text: newSourceText.trim(),
          translated_text: newTranslatedText.trim(),
          source_lang: newSourceLang,
          target_lang: newTargetLang,
          note: newNote.trim(),
          tags: newTags,
          is_favorite: true,
        },
      });
    },
    onSuccess: () => {
      toast.success('New note & annotation created');
      setShowCreateModal(false);
      setNewTitle('');
      setNewSourceText('');
      setNewTranslatedText('');
      setNewNote('');
      setNewTags(['vocabulary']);
      queryClient.invalidateQueries({ queryKey: ['notes'] });
    },
    onError: (err) => toast.error('Failed to create note', friendlyMessage(err)),
  });

  const copyToClipboard = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
      toast.success('Copied to clipboard');
    } catch {
      toast.error('Copy failed');
    }
  };

  const playSpeech = async (noteId: string, text: string, lang: string) => {
    try {
      setActiveAudioId(noteId);
      const res = await api<{ audio_base64: string; format: string }>('/api/v1/tts', {
        method: 'POST',
        body: { text: text.slice(0, 300), language: lang },
      });
      const mime = res.format === 'wav' ? 'audio/wav' : 'audio/mpeg';
      const audio = new Audio(`data:${mime};base64,${res.audio_base64}`);
      audio.onended = () => setActiveAudioId(null);
      audio.onerror = () => setActiveAudioId(null);
      await audio.play();
    } catch {
      setActiveAudioId(null);
      if ('speechSynthesis' in window) {
        const u = new SpeechSynthesisUtterance(text.slice(0, 200));
        u.lang = lang;
        u.onend = () => setActiveAudioId(null);
        speechSynthesis.speak(u);
      }
    }
  };

  const openInTranslate = (note: NoteItem) => {
    sessionStorage.setItem('talkflow_prefill_source', note.source_text);
    sessionStorage.setItem('talkflow_prefill_src_lang', note.source_lang);
    sessionStorage.setItem('talkflow_prefill_tgt_lang', note.target_lang);
    navigate('/translate');
  };

  const clearAllFilters = () => {
    setSearchQuery('');
    setDebouncedQuery('');
    setSelectedSourceLang('');
    setSelectedTargetLang('');
    setSelectedTag('');
    setFavoritesOnly(false);
  };

  const languageMap = useMemo(() => {
    const map = new Map<string, string>();
    (langs ?? []).forEach((l: any) => map.set(l.code, l.name));
    return map;
  }, [langs]);

  const langName = (code: string) => languageMap.get(code) || code.toUpperCase();

  const notesList = data?.items ?? [];

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6 lg:p-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-dl-border pb-5">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600 text-white shadow-xs">
              <BookmarkCheck className="h-5 w-5" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-dl-navy">
              Notes & Multilingual Search
            </h1>
          </div>
          <p className="mt-1 text-xs sm:text-sm text-dl-muted">
            DeepL-style saved translations, custom terminology notes, and inline annotations across all 119+ languages.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white shadow-xs"
          >
            <Plus className="h-4 w-4" />
            <span>New Note</span>
          </Button>
        </div>
      </div>

      {/* Multilingual Search Bar & Controls */}
      <div className="rounded-2xl border border-dl-border bg-white p-4 shadow-xs space-y-3">
        <div className="flex flex-col md:flex-row items-stretch md:items-center gap-3">
          {/* Universal Search Input */}
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-dl-muted" />
            <input
              type="text"
              className="w-full h-11 rounded-xl border border-dl-border bg-slate-50/60 pl-10 pr-9 text-sm text-dl-navy placeholder:text-dl-faint focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all"
              placeholder="Search across all languages (English, Bhojpuri, Japanese, Arabic, Russian...)"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Search notes"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-dl-muted hover:text-dl-navy p-1"
                title="Clear query"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          {/* Source Lang Filter */}
          <div className="w-full md:w-44">
            <select
              value={selectedSourceLang}
              onChange={(e) => setSelectedSourceLang(e.target.value)}
              className="w-full h-11 rounded-xl border border-dl-border bg-white px-3 text-xs font-medium text-dl-navy focus:outline-none focus:ring-2 focus:ring-blue-100"
              aria-label="Filter source language"
            >
              <option value="">All Source Langs</option>
              {(langs ?? []).map((l: any) => (
                <option key={l.code} value={l.code}>
                  {l.name} ({l.code})
                </option>
              ))}
            </select>
          </div>

          {/* Target Lang Filter */}
          <div className="w-full md:w-44">
            <select
              value={selectedTargetLang}
              onChange={(e) => setSelectedTargetLang(e.target.value)}
              className="w-full h-11 rounded-xl border border-dl-border bg-white px-3 text-xs font-medium text-dl-navy focus:outline-none focus:ring-2 focus:ring-blue-100"
              aria-label="Filter target language"
            >
              <option value="">All Target Langs</option>
              {(langs ?? []).map((l: any) => (
                <option key={l.code} value={l.code}>
                  {l.name} ({l.code})
                </option>
              ))}
            </select>
          </div>

          {/* Favorites Filter Toggle */}
          <button
            type="button"
            onClick={() => setFavoritesOnly(!favoritesOnly)}
            className={`h-11 px-4 rounded-xl border flex items-center justify-center gap-1.5 text-xs font-semibold transition-all ${
              favoritesOnly
                ? 'border-amber-400 bg-amber-50 text-amber-800'
                : 'border-dl-border bg-white text-dl-muted hover:border-slate-300 hover:text-dl-navy'
            }`}
            title="Toggle favorites filter"
          >
            <Star className={`h-4 w-4 ${favoritesOnly ? 'fill-amber-400 text-amber-500' : ''}`} />
            <span>Favorites</span>
          </button>
        </div>

        {/* Tag Filters & Search Metainfo */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-dl-border/50 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-dl-muted flex items-center gap-1 mr-1">
              <Tag className="h-3.5 w-3.5" /> Tags:
            </span>
            <button
              onClick={() => setSelectedTag('')}
              className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition-colors ${
                !selectedTag
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 text-dl-muted hover:bg-slate-200'
              }`}
            >
              All
            </button>
            {(data?.available_tags ?? []).map((t) => (
              <button
                key={t}
                onClick={() => setSelectedTag(selectedTag === t ? '' : t)}
                className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition-colors ${
                  selectedTag === t
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-100 text-dl-navy hover:bg-slate-200'
                }`}
              >
                #{t}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 text-dl-faint">
            {data && (
              <span className="tabular-nums">
                Found {data.total} {data.total === 1 ? 'note' : 'notes'} in {data.latency_ms} ms
              </span>
            )}
            {(searchQuery || selectedSourceLang || selectedTargetLang || selectedTag || favoritesOnly) && (
              <button
                onClick={clearAllFilters}
                className="text-blue-600 hover:underline font-medium"
              >
                Reset filters
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Notes List */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Spinner className="h-8 w-8 text-blue-600" />
          <span className="text-xs text-dl-muted">Searching notes library…</span>
        </div>
      ) : notesList.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-dl-border bg-white p-12 text-center">
          <BookmarkPlus className="mx-auto h-12 w-12 text-dl-faint" />
          <h3 className="mt-3 text-base font-semibold text-dl-navy">No notes match your search</h3>
          <p className="mt-1 text-xs text-dl-muted max-w-md mx-auto">
            Try searching for a different keyword across languages, clearing your filters, or save a new translation note.
          </p>
          <div className="mt-4 flex items-center justify-center gap-2">
            <Button variant="secondary" onClick={clearAllFilters}>
              Clear Filters
            </Button>
            <Button onClick={() => setShowCreateModal(true)}>
              <Plus className="h-4 w-4 mr-1" /> Create Note
            </Button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {notesList.map((item) => {
            const isEditing = editingNoteId === item.id;
            return (
              <div
                key={item.id}
                className="group relative rounded-2xl border border-dl-border bg-white p-5 shadow-xs transition-all hover:border-blue-200 hover:shadow-sm"
              >
                {/* Card Header */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-dl-border/60 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-semibold text-dl-navy">
                      <span>{langName(item.source_lang)}</span>
                      <ArrowRight className="h-3 w-3 text-dl-muted" />
                      <span>{langName(item.target_lang)}</span>
                    </span>
                    <h3 className="text-sm font-semibold text-dl-navy truncate max-w-md">
                      {item.title}
                    </h3>
                  </div>

                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() =>
                        toggleFavMutation.mutate({
                          id: item.id,
                          is_favorite: !item.is_favorite,
                        })
                      }
                      className="p-1 text-dl-muted hover:text-amber-500 transition-colors"
                      title={item.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
                    >
                      <Star
                        className={`h-4 w-4 ${
                          item.is_favorite ? 'fill-amber-400 text-amber-500' : ''
                        }`}
                      />
                    </button>
                    <button
                      type="button"
                      onClick={() => openInTranslate(item)}
                      className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 px-2 py-1 rounded-md hover:bg-blue-50 transition-colors font-medium"
                      title="Load into live translator"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                      <span className="hidden sm:inline">Open in Translate</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteMutation.mutate(item.id)}
                      className="p-1 text-dl-muted hover:text-rose-600 transition-colors"
                      title="Delete note"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {/* Card Body: Dual Pane Source & Translation with Search Highlights */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-3.5">
                  {/* Source Side */}
                  <div className="space-y-1.5 rounded-xl bg-slate-50/70 p-3 border border-slate-100">
                    <div className="flex items-center justify-between text-[11px] font-semibold text-dl-muted uppercase tracking-wider">
                      <span>Original ({item.source_lang.toUpperCase()})</span>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => playSpeech(item.id + '_src', item.source_text, item.source_lang)}
                          className="hover:text-blue-600 p-0.5"
                          title="Listen source audio"
                        >
                          <Volume2 className={`h-3.5 w-3.5 ${activeAudioId === item.id + '_src' ? 'text-blue-600 animate-pulse' : ''}`} />
                        </button>
                        <button
                          type="button"
                          onClick={() => copyToClipboard(item.id + '_src', item.source_text)}
                          className="hover:text-blue-600 p-0.5"
                          title="Copy source"
                        >
                          {copiedId === item.id + '_src' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                    </div>
                    <div className="text-sm text-dl-navy leading-relaxed break-words [&_mark]:bg-amber-200 [&_mark]:text-amber-900 [&_mark]:px-0.5 [&_mark]:rounded">
                      {item.highlight_source ? (
                        <span dangerouslySetInnerHTML={{ __html: item.highlight_source }} />
                      ) : (
                        item.source_text
                      )}
                    </div>
                  </div>

                  {/* Translated Side */}
                  <div className="space-y-1.5 rounded-xl bg-blue-50/40 p-3 border border-blue-100/60">
                    <div className="flex items-center justify-between text-[11px] font-semibold text-blue-700 uppercase tracking-wider">
                      <span>Translation ({item.target_lang.toUpperCase()})</span>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => playSpeech(item.id + '_tgt', item.translated_text, item.target_lang)}
                          className="hover:text-blue-600 p-0.5"
                          title="Listen target audio"
                        >
                          <Volume2 className={`h-3.5 w-3.5 ${activeAudioId === item.id + '_tgt' ? 'text-blue-600 animate-pulse' : ''}`} />
                        </button>
                        <button
                          type="button"
                          onClick={() => copyToClipboard(item.id + '_tgt', item.translated_text)}
                          className="hover:text-blue-600 p-0.5"
                          title="Copy translation"
                        >
                          {copiedId === item.id + '_tgt' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                    </div>
                    <div className="text-sm text-dl-navy leading-relaxed font-medium break-words [&_mark]:bg-amber-200 [&_mark]:text-amber-900 [&_mark]:px-0.5 [&_mark]:rounded">
                      {item.highlight_target ? (
                        <span dangerouslySetInnerHTML={{ __html: item.highlight_target }} />
                      ) : (
                        item.translated_text
                      )}
                    </div>
                  </div>
                </div>

                {/* Inline Annotations if any */}
                {item.annotations && item.annotations.length > 0 && (
                  <div className="mt-3 flex flex-wrap items-center gap-2 pt-2 border-t border-dl-border/40">
                    <span className="text-[11px] font-semibold text-dl-muted flex items-center gap-1">
                      <Layers className="h-3 w-3" /> Annotations:
                    </span>
                    {item.annotations.map((ann, idx) => (
                      <span
                        key={idx}
                        className={`inline-flex items-center gap-1.5 rounded-lg border px-2 py-0.5 text-xs ${
                          TAG_COLORS[ann.tag] || TAG_COLORS.default
                        }`}
                        title={ann.comment ? `${ann.tag}: ${ann.comment}` : ann.tag}
                      >
                        <span className="font-semibold">{ann.text}</span>
                        {ann.comment && (
                          <span className="text-[10px] opacity-80">({ann.comment})</span>
                        )}
                      </span>
                    ))}
                  </div>
                )}

                {/* Personal Notes / Comments Box */}
                <div className="mt-3 rounded-xl bg-amber-50/50 border border-amber-200/60 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-amber-900 flex items-center gap-1">
                      <Info className="h-3.5 w-3.5 text-amber-700" /> Personal Note:
                    </span>
                    {!isEditing && (
                      <button
                        type="button"
                        onClick={() => {
                          setEditingNoteId(item.id);
                          setEditedNoteText(item.note);
                        }}
                        className="text-[11px] text-amber-800 hover:text-amber-950 font-medium flex items-center gap-1"
                      >
                        <Edit3 className="h-3 w-3" /> Edit
                      </button>
                    )}
                  </div>

                  {isEditing ? (
                    <div className="mt-2 space-y-2">
                      <textarea
                        className="w-full h-16 rounded-lg border border-amber-300 p-2 text-xs text-dl-navy focus:outline-none focus:ring-1 focus:ring-amber-500"
                        value={editedNoteText}
                        onChange={(e) => setEditedNoteText(e.target.value)}
                        placeholder="Add notes, grammar points, or terminology explanations…"
                      />
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setEditingNoteId(null)}
                        >
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          className="bg-amber-600 hover:bg-amber-700 text-white"
                          onClick={() =>
                            updateNoteMutation.mutate({
                              id: item.id,
                              note: editedNoteText,
                            })
                          }
                        >
                          Save Note
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-1 text-xs text-amber-950 leading-relaxed [&_mark]:bg-amber-300 [&_mark]:px-0.5 [&_mark]:rounded">
                      {item.highlight_note ? (
                        <span dangerouslySetInnerHTML={{ __html: item.highlight_note }} />
                      ) : item.note ? (
                        item.note
                      ) : (
                        <span className="text-amber-600/70 italic">
                          No notes added. Click edit to add explanation.
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* Tags and Timestamp Footer */}
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-dl-muted pt-2 border-t border-dl-border/40">
                  <div className="flex flex-wrap items-center gap-1">
                    {item.tags.map((t) => (
                      <span
                        key={t}
                        className="rounded-md bg-slate-100 px-2 py-0.5 font-medium text-slate-700 hover:bg-slate-200 cursor-pointer"
                        onClick={() => setSelectedTag(t)}
                      >
                        #{t}
                      </span>
                    ))}
                  </div>
                  <span className="flex items-center gap-1 tabular-nums text-dl-faint">
                    <Clock className="h-3 w-3" />
                    {new Date(item.created_at).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                    })}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Note Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-xl rounded-2xl bg-white p-6 shadow-xl border border-dl-border space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-dl-border pb-3">
              <h2 className="text-lg font-bold text-dl-navy flex items-center gap-2">
                <BookmarkPlus className="h-5 w-5 text-blue-600" />
                <span>Save New Translation Note</span>
              </h2>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-dl-muted hover:text-dl-navy p-1"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="font-semibold text-dl-navy block mb-1">
                  Title (optional)
                </label>
                <input
                  type="text"
                  className="w-full h-9 rounded-lg border border-dl-border px-3 text-xs"
                  placeholder="e.g. Legal agreement clause, Bhojpuri dialect phrase"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-dl-navy block mb-1">
                    Source Language
                  </label>
                  <select
                    className="w-full h-9 rounded-lg border border-dl-border px-2 text-xs"
                    value={newSourceLang}
                    onChange={(e) => setNewSourceLang(e.target.value)}
                  >
                    {(langs ?? []).map((l: any) => (
                      <option key={l.code} value={l.code}>
                        {l.name} ({l.code})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="font-semibold text-dl-navy block mb-1">
                    Target Language
                  </label>
                  <select
                    className="w-full h-9 rounded-lg border border-dl-border px-2 text-xs"
                    value={newTargetLang}
                    onChange={(e) => setNewTargetLang(e.target.value)}
                  >
                    {(langs ?? []).map((l: any) => (
                      <option key={l.code} value={l.code}>
                        {l.name} ({l.code})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="font-semibold text-dl-navy block mb-1">
                  Source Text
                </label>
                <textarea
                  className="w-full h-18 rounded-lg border border-dl-border p-2.5 text-xs text-dl-navy"
                  placeholder="Type or paste source phrase…"
                  value={newSourceText}
                  onChange={(e) => setNewSourceText(e.target.value)}
                />
              </div>

              <div>
                <label className="font-semibold text-dl-navy block mb-1">
                  Translated Text
                </label>
                <textarea
                  className="w-full h-18 rounded-lg border border-dl-border p-2.5 text-xs text-dl-navy"
                  placeholder="Type or paste translated phrase…"
                  value={newTranslatedText}
                  onChange={(e) => setNewTranslatedText(e.target.value)}
                />
              </div>

              <div>
                <label className="font-semibold text-dl-navy block mb-1">
                  Notes & Explanations
                </label>
                <textarea
                  className="w-full h-16 rounded-lg border border-dl-border p-2.5 text-xs text-dl-navy"
                  placeholder="Grammar notes, context explanations, dialect variations…"
                  value={newNote}
                  onChange={(e) => setNewNote(e.target.value)}
                />
              </div>

              <div>
                <label className="font-semibold text-dl-navy block mb-1">Tags</label>
                <div className="flex items-center gap-2 mb-2">
                  <input
                    type="text"
                    className="flex-1 h-8 rounded-lg border border-dl-border px-2.5 text-xs"
                    placeholder="Add tag and press Enter"
                    value={newTagInput}
                    onChange={(e) => setNewTagInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        const t = newTagInput.trim().replace(/^#/, '');
                        if (t && !newTags.includes(t)) {
                          setNewTags([...newTags, t]);
                          setNewTagInput('');
                        }
                      }
                    }}
                  />
                  <Button
                    size="sm"
                    type="button"
                    onClick={() => {
                      const t = newTagInput.trim().replace(/^#/, '');
                      if (t && !newTags.includes(t)) {
                        setNewTags([...newTags, t]);
                        setNewTagInput('');
                      }
                    }}
                  >
                    Add
                  </Button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {newTags.map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-800"
                    >
                      #{tag}
                      <button
                        type="button"
                        onClick={() => setNewTags(newTags.filter((x) => x !== tag))}
                        className="text-slate-400 hover:text-slate-600"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-dl-border">
              <Button variant="ghost" onClick={() => setShowCreateModal(false)}>
                Cancel
              </Button>
              <Button
                className="bg-blue-600 hover:bg-blue-700 text-white"
                onClick={() => createMutation.mutate()}
                disabled={createMutation.isPending || !newSourceText.trim() || !newTranslatedText.trim()}
              >
                {createMutation.isPending ? 'Saving…' : 'Save Note'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
