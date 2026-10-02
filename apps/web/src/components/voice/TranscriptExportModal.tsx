import React, { useState, useMemo } from "react";
import {
  X,
  Download,
  Copy,
  Check,
  FileText,
  FileCode,
  Subtitles,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui";
import { toast } from "@/stores/toasts";
import {
  formatAsTxt,
  formatAsJson,
  formatAsSrt,
  formatAsVtt,
  downloadFile,
  type ExportTranscriptItem,
} from "@/lib/transcriptExporter";

export interface TranscriptExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  transcripts: ExportTranscriptItem[];
  title?: string;
}

type ExportFormat = "txt" | "srt" | "vtt" | "json";

export default function TranscriptExportModal({
  isOpen,
  onClose,
  transcripts,
  title = "Export Transcript & Subtitles",
}: TranscriptExportModalProps) {
  const [activeFormat, setActiveFormat] = useState<ExportFormat>("txt");
  const [includeOriginal, setIncludeOriginal] = useState(true);
  const [includeTranslation, setIncludeTranslation] = useState(true);
  const [copied, setCopied] = useState(false);

  // Compute formatted content dynamically based on current configuration
  const formattedContent = useMemo(() => {
    if (!transcripts || transcripts.length === 0) {
      return "// No transcripts recorded yet.";
    }

    switch (activeFormat) {
      case "txt":
        return formatAsTxt(transcripts, { includeOriginal, includeTranslation });
      case "srt":
        return formatAsSrt(transcripts);
      case "vtt":
        return formatAsVtt(transcripts);
      case "json":
        return formatAsJson(transcripts);
      default:
        return "";
    }
  }, [transcripts, activeFormat, includeOriginal, includeTranslation]);

  if (!isOpen) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(formattedContent);
      setCopied(true);
      toast.success("Transcript copied to clipboard!");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Failed to copy transcript");
    }
  };

  const handleDownload = () => {
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const filenameMap: Record<ExportFormat, { filename: string; mime: string }> = {
      txt: { filename: `globaltalk-transcript-${timestamp}.txt`, mime: "text/plain" },
      srt: { filename: `globaltalk-subtitles-${timestamp}.srt`, mime: "application/x-subrip" },
      vtt: { filename: `globaltalk-captions-${timestamp}.vtt`, mime: "text/vtt" },
      json: { filename: `globaltalk-data-${timestamp}.json`, mime: "application/json" },
    };

    const target = filenameMap[activeFormat];
    downloadFile(formattedContent, target.filename, target.mime);
    toast.success(`Downloaded ${target.filename}`);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="relative flex flex-col w-full max-w-2xl max-h-[85vh] rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* HEADER */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-iris-50 text-iris-600">
              <Download className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">{title}</h2>
              <p className="text-xs text-slate-500">
                {transcripts.length} transcript exchanges ready to export
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* FORMAT SELECTOR TABS */}
        <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-6 py-2.5">
          <div className="flex items-center gap-1 rounded-xl bg-slate-200/60 p-1">
            <button
              type="button"
              onClick={() => setActiveFormat("txt")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                activeFormat === "txt"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <FileText className="h-3.5 w-3.5 text-iris-600" />
              Plain Text (.txt)
            </button>
            <button
              type="button"
              onClick={() => setActiveFormat("srt")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                activeFormat === "srt"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Subtitles className="h-3.5 w-3.5 text-lagoon-600" />
              SubRip (.srt)
            </button>
            <button
              type="button"
              onClick={() => setActiveFormat("vtt")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                activeFormat === "vtt"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Sparkles className="h-3.5 w-3.5 text-emerald-600" />
              WebVTT (.vtt)
            </button>
            <button
              type="button"
              onClick={() => setActiveFormat("json")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                activeFormat === "json"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <FileCode className="h-3.5 w-3.5 text-amber-600" />
              JSON (.json)
            </button>
          </div>

          {activeFormat === "txt" && (
            <div className="flex items-center gap-3 text-xs text-slate-600">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeOriginal}
                  onChange={(e) => setIncludeOriginal(e.target.checked)}
                  className="rounded border-slate-300 text-iris-600 focus:ring-iris-500"
                />
                Original
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeTranslation}
                  onChange={(e) => setIncludeTranslation(e.target.checked)}
                  className="rounded border-slate-300 text-iris-600 focus:ring-iris-500"
                />
                Translation
              </label>
            </div>
          )}
        </div>

        {/* PREVIEW WINDOW */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-950/95 font-mono text-xs text-slate-200">
          <pre className="whitespace-pre-wrap break-words leading-relaxed select-all">
            {formattedContent}
          </pre>
        </div>

        {/* ACTIONS FOOTER */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-white px-6 py-4">
          <span className="text-xs text-slate-500">
            Export ready for video editing, translation memory, and meeting archives.
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleCopy}
              disabled={transcripts.length === 0}
              className="gap-1.5 text-xs"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? "Copied" : "Copy Content"}
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleDownload}
              disabled={transcripts.length === 0}
              className="gap-1.5 text-xs"
            >
              <Download className="h-3.5 w-3.5" />
              Download .{activeFormat}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
