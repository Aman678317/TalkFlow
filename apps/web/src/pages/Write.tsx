/**
 * DeepL Write Equivalent — AI Writing Companion (PDD §14, §21).
 *
 * Provides:
 * - Grammar, spelling, punctuation, and structural fixes
 * - Style customization: Business, Academic, Casual, Simple, Creative
 * - Tone customization: Professional, Friendly, Confident, Diplomatic, Direct
 * - Inline diff visualization (additions, deletions, phrasing changes)
 * - Granular suggestion inspector with contextual explanations
 * - Multiple alternative full-text rewrites
 * - Readability statistics & one-click copy / download
 */
import { useEffect, useState } from 'react';
import {
  ArrowRight, Check, ChevronDown, Copy, Download, FileText,
  Mic, MicOff, PenTool, RefreshCw, RotateCcw, Sparkles,
  Volume2, Wand2, Zap,
} from 'lucide-react';
import { api, friendlyMessage } from '@/lib/api';
import { Badge, Button, Card, Spinner } from '@/components/ui';
import { toast } from '@/stores/toasts';
import { cn } from '@/lib/utils';

interface WriteDiff {
  original: string;
  replacement: string;
  diff_type: string;
  explanation: string;
}

interface WriteResponse {
  original_text: string;
  improved_text: string;
  language: string;
  style: string;
  tone: string;
  changes_count: int;
  diffs: WriteDiff[];
  alternatives: string[];
}

const STYLES = [
  { value: 'business', label: '💼 Business', desc: 'Clear, executive, and impactful' },
  { value: 'academic', label: '🎓 Academic', desc: 'Scholarly, formal, and precise' },
  { value: 'casual', label: '☕ Casual', desc: 'Natural, friendly, and conversational' },
  { value: 'simple', label: '⚡ Simple', desc: 'Short sentences and plain language' },
  { value: 'creative', label: '🎨 Creative', desc: 'Expressive and vivid phrasing' },
];

const TONES = [
  { value: 'professional', label: 'Professional' },
  { value: 'confident', label: 'Confident' },
  { value: 'friendly', label: 'Friendly' },
  { value: 'diplomatic', label: 'Diplomatic' },
  { value: 'direct', label: 'Direct' },
];

const SAMPLE_TEXT = `i think that asap we wanna get in touch with the team to talk about the big problem. a lot of people feel like we got to look into this very good.`;

export default function WritePage() {
  const [sourceText, setSourceText] = useState('');
  const [style, setStyle] = useState('business');
  const [tone, setTone] = useState('professional');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<WriteResponse | null>(null);
  const [viewMode, setViewMode] = useState<'clean' | 'diffs' | 'suggestions'>('clean');
  const [copied, setCopied] = useState(false);
  const [isListening, setIsListening] = useState(false);

  // Auto-rewrite on text or style change with debounce
  useEffect(() => {
    if (!sourceText.trim()) {
      setResult(null);
      return;
    }
    const timer = setTimeout(() => {
      void runRewrite(sourceText);
    }, 700);
    return () => clearTimeout(timer);
  }, [sourceText, style, tone]);

  async function runRewrite(text: string) {
    if (!text.trim()) return;
    setLoading(true);
    try {
      const res = await api<WriteResponse>('/api/v1/write', {
        method: 'POST',
        body: {
          text,
          language: 'en',
          style,
          tone,
        },
      });
      setResult(res);
    } catch (err) {
      toast.error('Rewrite failed', friendlyMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const handleCopy = async (textToCopy: string) => {
    if (!textToCopy) return;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      toast.success('Copied to clipboard');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Copy failed');
    }
  };

  const handleDownload = () => {
    if (!result?.improved_text) return;
    const blob = new Blob([result.improved_text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `improved-writing-${style}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const speakText = (text: string) => {
    if (!('speechSynthesis' in window) || !text) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    window.speechSynthesis.speak(utterance);
  };

  const toggleMic = () => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      toast.error('Speech recognition not supported in this browser');
      return;
    }
    if (isListening) {
      setIsListening(false);
      return;
    }
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => setIsListening(false);
    recognition.onresult = (e: any) => {
      const transcript = e.results[0][0].transcript;
      setSourceText((prev) => (prev ? `${prev} ${transcript}` : transcript));
    };
    recognition.start();
  };

  const wordCount = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0);
  const origWords = wordCount(sourceText);
  const impWords = wordCount(result?.improved_text || '');

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Top Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-iris-600/10 text-iris-600">
              <Sparkles className="h-5 w-5" />
            </span>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">DeepL Write</h1>
            <Badge tone="indigo" className="ml-1 text-[11px] font-semibold">AI Assistant</Badge>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Perfect your writing with instant grammar correction, vocabulary upgrades, and tone tuning.
          </p>
        </div>

        {/* Style & Tone Pills */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Style selector */}
          <div className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
            <span className="pl-2 text-xs font-semibold text-slate-400">Style:</span>
            <div className="flex gap-1">
              {STYLES.map((s) => (
                <button
                  key={s.value}
                  onClick={() => setStyle(s.value)}
                  className={cn(
                    'rounded-lg px-2.5 py-1 text-xs font-medium transition-all',
                    style === s.value
                      ? 'bg-iris-600 text-white shadow-sm'
                      : 'text-slate-600 hover:bg-slate-100'
                  )}
                  title={s.desc}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Tone selector */}
          <div className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
            <span className="pl-2 text-xs font-semibold text-slate-400">Tone:</span>
            <div className="flex gap-1">
              {TONES.map((t) => (
                <button
                  key={t.value}
                  onClick={() => setTone(t.value)}
                  className={cn(
                    'rounded-lg px-2.5 py-1 text-xs font-medium transition-all',
                    tone === t.value
                      ? 'bg-slate-900 text-white shadow-sm'
                      : 'text-slate-600 hover:bg-slate-100'
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Main Dual-Pane Editor */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* LEFT PANE: Source Draft */}
        <Card className="flex flex-col border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Your draft</span>
              <span className="text-xs text-slate-400">({origWords} words · {sourceText.length} chars)</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSourceText(SAMPLE_TEXT)}
                className="text-xs text-iris-600 hover:text-iris-700 hover:underline"
              >
                Try sample text
              </button>
              {sourceText && (
                <button
                  onClick={() => setSourceText('')}
                  className="text-xs text-slate-400 hover:text-rose-600"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          <div className="relative flex-1 p-4">
            <textarea
              value={sourceText}
              onChange={(e) => setSourceText(e.target.value)}
              placeholder="Paste or type your draft text here to improve grammar, vocabulary, and tone…"
              className="h-80 w-full resize-none border-0 bg-transparent text-[15px] leading-relaxed text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-0"
              aria-label="Input draft text"
            />
          </div>

          {/* Bottom Left Toolbar */}
          <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-4 py-3 rounded-b-xl">
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant={isListening ? 'danger' : 'secondary'}
                onClick={toggleMic}
                title={isListening ? 'Stop listening' : 'Dictate with voice'}
                className="gap-1.5"
              >
                {isListening ? <MicOff className="h-3.5 w-3.5 text-rose-500 animate-pulse" /> : <Mic className="h-3.5 w-3.5" />}
                <span className="text-xs">{isListening ? 'Listening…' : 'Dictate'}</span>
              </Button>
              {sourceText && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => speakText(sourceText)}
                  title="Listen to original"
                >
                  <Volume2 className="h-3.5 w-3.5 text-slate-600" />
                </Button>
              )}
            </div>

            <Button
              size="sm"
              onClick={() => runRewrite(sourceText)}
              loading={loading}
              disabled={!sourceText.trim() || loading}
              className="gap-1.5 bg-iris-600 hover:bg-iris-700"
            >
              <Wand2 className="h-3.5 w-3.5" />
              <span>Improve with Write</span>
            </Button>
          </div>
        </Card>

        {/* RIGHT PANE: Improved Result & Suggestions */}
        <Card className="flex flex-col border-slate-200 bg-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between border-b border-slate-100 px-4 py-3 gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Improved version</span>
              {result && (
                <Badge tone="emerald" className="gap-1 font-semibold text-[11px]">
                  <Check className="h-3 w-3" />
                  {result.changes_count} improvement{result.changes_count !== 1 ? 's' : ''} applied
                </Badge>
              )}
            </div>

            {/* View Mode Switcher */}
            <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-0.5">
              <button
                onClick={() => setViewMode('clean')}
                className={cn('rounded px-2 py-1 text-xs font-medium transition-colors', viewMode === 'clean' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-800')}
              >
                Clean text
              </button>
              <button
                onClick={() => setViewMode('diffs')}
                className={cn('rounded px-2 py-1 text-xs font-medium transition-colors', viewMode === 'diffs' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-800')}
              >
                Changes
              </button>
              <button
                onClick={() => setViewMode('suggestions')}
                className={cn('rounded px-2 py-1 text-xs font-medium transition-colors', viewMode === 'suggestions' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-800')}
              >
                Analysis ({result?.diffs.length ?? 0})
              </button>
            </div>
          </div>

          <div className="relative flex-1 p-4 overflow-y-auto max-h-[380px]">
            {loading ? (
              <div className="flex h-64 flex-col items-center justify-center gap-3 text-slate-400">
                <Spinner className="h-6 w-6 text-iris-600" />
                <p className="text-sm font-medium">Polishing and adjusting tone…</p>
              </div>
            ) : !result ? (
              <div className="flex h-64 flex-col items-center justify-center text-center text-slate-400">
                <PenTool className="mb-2 h-8 w-8 text-slate-300" />
                <p className="text-sm font-medium text-slate-600">No improvements yet</p>
                <p className="mt-1 max-w-xs text-xs text-slate-400">
                  Type or paste text on the left to see improved grammar, tone adjustments, and alternate phrasings.
                </p>
              </div>
            ) : viewMode === 'clean' ? (
              /* 1. Clean Improved Text */
              <div className="h-full">
                <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-slate-900 select-text">
                  {result.improved_text}
                </p>
              </div>
            ) : viewMode === 'diffs' ? (
              /* 2. Visual Diff Mode */
              <div className="space-y-4">
                <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-4">
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">Highlighted Changes</h4>
                  <div className="flex flex-wrap gap-1.5 text-sm leading-relaxed">
                    {result.diffs.map((d, i) => (
                      <span key={i} className="inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 border border-slate-200 shadow-xs">
                        <span className="line-through text-rose-500 text-xs">{d.original}</span>
                        <ArrowRight className="h-3 w-3 text-slate-400" />
                        <span className="font-semibold text-emerald-700">{d.replacement}</span>
                      </span>
                    ))}
                  </div>
                </div>
                <div className="rounded-xl bg-slate-50 p-3">
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
                    {result.improved_text}
                  </p>
                </div>
              </div>
            ) : (
              /* 3. Detailed Suggestions Inspector */
              <div className="space-y-3">
                {result.diffs.length === 0 ? (
                  <p className="text-sm text-slate-500 italic">No grammatical or phrasing issues detected.</p>
                ) : (
                  result.diffs.map((d, i) => (
                    <div key={i} className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5">
                      <div className="flex items-center justify-between gap-2">
                        <Badge
                          tone={d.diff_type === 'grammar' ? 'rose' : d.diff_type === 'vocabulary' ? 'indigo' : 'lagoon'}
                          className="capitalize text-[10px]"
                        >
                          {d.diff_type}
                        </Badge>
                        <span className="text-xs text-slate-400">{d.explanation}</span>
                      </div>
                      <div className="mt-2 flex items-center gap-2 text-sm">
                        <span className="line-through text-slate-400">{d.original}</span>
                        <ArrowRight className="h-3 w-3 text-slate-400" />
                        <span className="font-semibold text-emerald-600">{d.replacement}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Alternatives Bar (DeepL Write Feature) */}
          {result?.alternatives && result.alternatives.length > 0 && (
            <div className="border-t border-slate-100 bg-slate-50/40 p-4">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-500">
                Alternative Phrasings
              </span>
              <div className="space-y-2">
                {result.alternatives.map((alt, i) => (
                  <div
                    key={i}
                    className="group flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-2.5 text-xs text-slate-700 shadow-xs hover:border-iris-400"
                  >
                    <p className="flex-1 truncate">{alt}</p>
                    <button
                      onClick={() => handleCopy(alt)}
                      className="shrink-0 text-slate-400 hover:text-iris-600 font-medium"
                      title="Copy alternative"
                    >
                      Copy
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Bottom Right Toolbar */}
          <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-4 py-3 rounded-b-xl">
            <div className="flex items-center gap-2">
              {result && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => speakText(result.improved_text)}
                  title="Listen to improved version"
                >
                  <Volume2 className="h-3.5 w-3.5 text-slate-600" />
                </Button>
              )}
              {result && (
                <span className="text-xs text-slate-400">
                  {impWords} words ({Math.round(((impWords - origWords) / (origWords || 1)) * 100)}% word diff)
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={handleDownload}
                disabled={!result}
                className="gap-1.5"
              >
                <Download className="h-3.5 w-3.5 text-slate-600" />
                <span className="hidden sm:inline">Download</span>
              </Button>
              <Button
                size="sm"
                variant="primary"
                onClick={() => handleCopy(result?.improved_text || '')}
                disabled={!result}
                className={cn('gap-1.5', copied && 'bg-emerald-600 hover:bg-emerald-700')}
              >
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                <span>{copied ? 'Copied!' : 'Copy text'}</span>
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
