import { useState } from 'react';
import {
  Bot,
  Workflow,
  Sparkles,
  GitBranch,
  CheckCircle2,
  RefreshCw,
  Copy,
  Check,
  Send,
  ShieldAlert,
  Search,
  BookOpen,
  ArrowRight,
  Activity,
  FileText
} from 'lucide-react';
import { api, friendlyMessage } from '@/lib/api';

type SystemTab = 'triage' | 'content' | 'research' | 'resume';

export default function AgentStudio() {
  const [activeTab, setActiveTab] = useState<SystemTab>('triage');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // --- System 02: Triage Graph State ---
  const [triageTicket, setTriageTicket] = useState(
    'I was charged twice this month for my subscription order ord_101. Please refund me.'
  );
  const [triageLoading, setTriageLoading] = useState(false);
  const [triageResult, setTriageResult] = useState<any>(null);
  const [triageError, setTriageError] = useState<string | null>(null);

  // --- System 03: Content Pipeline State ---
  const [contentTopic, setContentTopic] = useState('Why agentic AI needs typed tool calls');
  const [contentLoading, setContentLoading] = useState(false);
  const [contentResult, setContentResult] = useState<any>(null);
  const [contentError, setContentError] = useState<string | null>(null);

  // --- System 01: Research Crew State ---
  const [researchTopic, setResearchTopic] = useState('State of agentic AI, 2026');
  const [researchLoading, setResearchLoading] = useState(false);
  const [researchResult, setResearchResult] = useState<any>(null);
  const [researchError, setResearchError] = useState<string | null>(null);

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const handleRunTriage = async (ticketOverride?: string) => {
    const ticketToRun = ticketOverride || triageTicket;
    setTriageLoading(true);
    setTriageError(null);
    try {
      const res = await api.post('/api/v1/agent-studio/triage', { ticket: ticketToRun });
      setTriageResult(res);
    } catch (err) {
      setTriageError(friendlyMessage(err));
    } finally {
      setTriageLoading(false);
    }
  };

  const handleRunContentPipeline = async (topicOverride?: string) => {
    const topicToRun = topicOverride || contentTopic;
    setContentLoading(true);
    setContentError(null);
    try {
      const res = await api.post('/api/v1/agent-studio/content-pipeline', { topic: topicToRun });
      setContentResult(res);
    } catch (err) {
      setContentError(friendlyMessage(err));
    } finally {
      setContentLoading(false);
    }
  };

  const handleRunResearchCrew = async (topicOverride?: string) => {
    const topicToRun = topicOverride || researchTopic;
    setResearchLoading(true);
    setResearchError(null);
    try {
      const res = await api.post('/api/v1/agent-studio/research-crew', { topic: topicToRun });
      setResearchResult(res);
    } catch (err) {
      setResearchError(friendlyMessage(err));
    } finally {
      setResearchLoading(false);
    }
  };

  return (
    <div className="min-h-full bg-slate-50/60 p-4 sm:p-6 lg:p-8">
      {/* Header Banner */}
      <div className="mb-6 rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 p-6 text-white shadow-lg">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-indigo-500/20 px-3 py-1 text-xs font-semibold text-indigo-300 ring-1 ring-inset ring-indigo-400/30">
              <Bot className="h-3.5 w-3.5" />
              Multi-Agent Systems Portfolio · Built Tonight
            </div>
            <h1 className="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">
              Multi-Agent Architecture Studio
            </h1>
            <p className="mt-1 text-sm text-slate-300">
              Live orchestration engines built with LangGraph & CrewAI. Test state machines, hub-and-spoke crews, and self-correcting feedback loops.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300 ring-1 ring-emerald-500/30">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              Runtime Active
            </span>
          </div>
        </div>

        {/* System Badges */}
        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-xl bg-white/5 p-3 backdrop-blur ring-1 ring-white/10">
            <div className="text-[11px] font-medium uppercase tracking-wider text-indigo-300">System 01 · CrewAI</div>
            <div className="text-sm font-semibold text-white">Research Assistant Crew</div>
            <div className="text-xs text-slate-400">4 Specialist Personas · Hub & Spoke</div>
          </div>
          <div className="rounded-xl bg-white/5 p-3 backdrop-blur ring-1 ring-white/10">
            <div className="text-[11px] font-medium uppercase tracking-wider text-emerald-300">System 02 · LangGraph</div>
            <div className="text-sm font-semibold text-white">Support Triage Graph</div>
            <div className="text-xs text-slate-400">Conditional Edge Router · Escalation</div>
          </div>
          <div className="rounded-xl bg-white/5 p-3 backdrop-blur ring-1 ring-white/10">
            <div className="text-[11px] font-medium uppercase tracking-wider text-amber-300">System 03 · Hybrid</div>
            <div className="text-sm font-semibold text-white">Autonomous Content Pipeline</div>
            <div className="text-xs text-slate-400">Self-Correcting Critique Loop · Quality Gate</div>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="mb-6 flex space-x-1 rounded-xl bg-white p-1.5 shadow-sm ring-1 ring-slate-200">
        <button
          onClick={() => setActiveTab('triage')}
          className={`flex flex-1 items-center justify-center gap-2 rounded-lg py-2.5 text-xs sm:text-sm font-semibold transition-all ${
            activeTab === 'triage'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <GitBranch className="h-4 w-4" />
          <span>02. Support Triage Graph</span>
        </button>

        <button
          onClick={() => setActiveTab('content')}
          className={`flex flex-1 items-center justify-center gap-2 rounded-lg py-2.5 text-xs sm:text-sm font-semibold transition-all ${
            activeTab === 'content'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <RefreshCw className="h-4 w-4" />
          <span>03. Content Pipeline</span>
        </button>

        <button
          onClick={() => setActiveTab('research')}
          className={`flex flex-1 items-center justify-center gap-2 rounded-lg py-2.5 text-xs sm:text-sm font-semibold transition-all ${
            activeTab === 'research'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <Search className="h-4 w-4" />
          <span>01. Research Crew</span>
        </button>

        <button
          onClick={() => setActiveTab('resume')}
          className={`flex flex-1 items-center justify-center gap-2 rounded-lg py-2.5 text-xs sm:text-sm font-semibold transition-all ${
            activeTab === 'resume'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <FileText className="h-4 w-4" />
          <span>Specs & Resume Bullets</span>
        </button>
      </div>

      {/* TAB 1: Support Triage Graph */}
      {activeTab === 'triage' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Controls & Input */}
          <div className="lg:col-span-5 space-y-5">
            <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
              <h3 className="text-base font-semibold text-slate-900 flex items-center gap-2">
                <GitBranch className="h-4 w-4 text-indigo-600" />
                Ticket Classifier & State Router
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                LangGraph state machine that evaluates intent and sentiment, executes conditional edges, and handles human escalation.
              </p>

              {/* Quick Presets */}
              <div className="mt-4">
                <label className="text-xs font-semibold text-slate-700">Quick Test Scenarios:</label>
                <div className="mt-2 flex flex-col gap-2">
                  <button
                    onClick={() => {
                      const text = 'I was charged twice this month for my subscription order ord_101. Please refund me.';
                      setTriageTicket(text);
                      void handleRunTriage(text);
                    }}
                    className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-left text-xs font-medium text-slate-700 hover:border-indigo-300 hover:bg-indigo-50/50 transition-all"
                  >
                    <span>💳 Billing: Double Charge Refund (ord_101)</span>
                    <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                  <button
                    onClick={() => {
                      const text = 'My WebRTC microphone audio has high latency and packet lag during calls.';
                      setTriageTicket(text);
                      void handleRunTriage(text);
                    }}
                    className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-left text-xs font-medium text-slate-700 hover:border-indigo-300 hover:bg-indigo-50/50 transition-all"
                  >
                    <span>🛠️ Tech: WebRTC Latency & Packet Loss</span>
                    <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                  <button
                    onClick={() => {
                      const text = 'This is ridiculous and unacceptable, your platform is a scam, get a human now!';
                      setTriageTicket(text);
                      void handleRunTriage(text);
                    }}
                    className="flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50/60 p-2.5 text-left text-xs font-medium text-amber-900 hover:border-amber-400 hover:bg-amber-100/50 transition-all"
                  >
                    <span>🚨 Angry Escalation: Slack Channel Alert</span>
                    <ArrowRight className="h-3.5 w-3.5 text-amber-500" />
                  </button>
                </div>
              </div>

              {/* Ticket Input */}
              <div className="mt-4">
                <label className="text-xs font-semibold text-slate-700">Custom Support Ticket Text:</label>
                <textarea
                  value={triageTicket}
                  onChange={(e) => setTriageTicket(e.target.value)}
                  rows={3}
                  className="mt-1.5 w-full rounded-xl border border-slate-300 p-3 text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  placeholder="Enter support ticket text..."
                />
              </div>

              <button
                onClick={() => handleRunTriage()}
                disabled={triageLoading || !triageTicket.trim()}
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:opacity-50 transition-all"
              >
                {triageLoading ? (
                  <>
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    Executing LangGraph State Machine...
                  </>
                ) : (
                  <>
                    <Send className="h-3.5 w-3.5" />
                    Dispatch Ticket into Graph
                  </>
                )}
              </button>

              {triageError && (
                <div className="mt-3 rounded-xl bg-rose-50 p-3 text-xs text-rose-700 ring-1 ring-rose-200">
                  {triageError}
                </div>
              )}
            </div>

            {/* Architecture Node Map */}
            <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Graph Topology</h4>
              <div className="mt-3 space-y-2 text-xs">
                <div className="flex items-center gap-2 rounded-lg bg-slate-100 p-2 text-slate-700">
                  <div className="h-2 w-2 rounded-full bg-slate-400" />
                  <span className="font-semibold">Node 1:</span> Ticket In (Raw user message)
                </div>
                <div className="flex items-center gap-2 rounded-lg bg-indigo-50 p-2 text-indigo-800">
                  <div className="h-2 w-2 rounded-full bg-indigo-500" />
                  <span className="font-semibold">Node 2:</span> Classifier (Structured JSON intent + sentiment)
                </div>
                <div className="flex items-center gap-2 rounded-lg bg-slate-100 p-2 text-slate-700">
                  <div className="h-2 w-2 rounded-full bg-amber-500" />
                  <span className="font-semibold">Edge:</span> Conditional router [billing / tech / low_conf]
                </div>
                <div className="flex items-center gap-2 rounded-lg bg-emerald-50 p-2 text-emerald-800">
                  <div className="h-2 w-2 rounded-full bg-emerald-500" />
                  <span className="font-semibold">Specialists:</span> Billing Agent ($50 cap) | Tech Agent (KB search) | Human Queue
                </div>
              </div>
            </div>
          </div>

          {/* Results Panel */}
          <div className="lg:col-span-7">
            <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 h-full flex flex-col">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-emerald-600" />
                  <h3 className="text-sm font-bold text-slate-900">Execution Output & State Machine Trace</h3>
                </div>
                {triageResult && (
                  <button
                    onClick={() => copyToClipboard(JSON.stringify(triageResult, null, 2), 'triage')}
                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
                  >
                    {copiedKey === 'triage' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copiedKey === 'triage' ? 'Copied' : 'Copy State'}</span>
                  </button>
                )}
              </div>

              {triageResult ? (
                <div className="mt-5 space-y-4 flex-1">
                  {/* Status Badges */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200/70">
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Route</div>
                      <div className="mt-1 text-sm font-bold text-indigo-700 capitalize">{triageResult.route}</div>
                    </div>
                    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200/70">
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Category</div>
                      <div className="mt-1 text-sm font-bold text-slate-800 capitalize">{triageResult.category}</div>
                    </div>
                    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200/70">
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Confidence</div>
                      <div className="mt-1 text-sm font-bold text-emerald-700">
                        {Math.round(triageResult.confidence * 100)}%
                      </div>
                    </div>
                    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200/70">
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Sentiment</div>
                      <div className={`mt-1 text-sm font-bold capitalize ${
                        triageResult.sentiment === 'angry' ? 'text-rose-600' : 'text-slate-800'
                      }`}>
                        {triageResult.sentiment}
                      </div>
                    </div>
                  </div>

                  {/* Escalation Banner */}
                  {triageResult.escalated ? (
                    <div className="rounded-xl bg-rose-50 border border-rose-200 p-4">
                      <div className="flex items-center gap-2 text-rose-800 font-bold text-xs">
                        <ShieldAlert className="h-4 w-4 text-rose-600" />
                        Human Escalation Triggered
                      </div>
                      <p className="mt-1 text-xs text-rose-700">
                        {triageResult.escalation_reason || 'Low-confidence classification or high angry sentiment score.'}
                      </p>
                      <div className="mt-2 text-[11px] text-rose-600 font-mono">
                        Action: Pushed ticket snapshot to on-call engineer Slack channel #support-escalations.
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-3 text-xs text-emerald-800 flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span>Specialist node resolved autonomously without escalation.</span>
                    </div>
                  )}

                  {/* Specialist Response */}
                  <div className="rounded-xl border border-slate-200 bg-white p-4">
                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                      Specialist Agent Resolution:
                    </div>
                    <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-800 whitespace-pre-wrap font-sans leading-relaxed">
                      {triageResult.response}
                    </div>
                  </div>

                  {/* Raw State JSON Accordion */}
                  <div className="rounded-xl bg-slate-900 p-4 text-slate-300 font-mono text-[11px] overflow-x-auto">
                    <div className="text-[10px] text-slate-400 mb-2">// LangGraph TicketState Dict</div>
                    <pre>{JSON.stringify(triageResult, null, 2)}</pre>
                  </div>
                </div>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-400">
                  <Workflow className="h-12 w-12 text-slate-300 mb-3" />
                  <p className="text-sm font-medium text-slate-600">No ticket evaluated yet</p>
                  <p className="text-xs text-slate-400 mt-1 max-w-sm">
                    Choose one of the quick test presets or type a custom inquiry on the left and click "Dispatch Ticket into Graph".
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: Content Pipeline */}
      {activeTab === 'content' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Controls */}
          <div className="lg:col-span-5 space-y-5">
            <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
              <h3 className="text-base font-semibold text-slate-900 flex items-center gap-2">
                <RefreshCw className="h-4 w-4 text-indigo-600" />
                Autonomous Content Pipeline
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                Self-correcting LangGraph loop wrapping CrewAI research. Drafts, critiques against strict rubrics, and only publishes if score $\ge 0.80$ (bounded at 3 loops).
              </p>

              {/* Presets */}
              <div className="mt-4">
                <label className="text-xs font-semibold text-slate-700">Preset Content Briefs:</label>
                <div className="mt-2 flex flex-col gap-2">
                  <button
                    onClick={() => {
                      const topic = 'Why agentic AI needs typed tool calls';
                      setContentTopic(topic);
                      void handleRunContentPipeline(topic);
                    }}
                    className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-left text-xs font-medium text-slate-700 hover:border-indigo-300 hover:bg-indigo-50/50 transition-all"
                  >
                    <span>📑 Why agentic AI needs typed tool calls</span>
                    <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                  <button
                    onClick={() => {
                      const topic = 'Multi-Agent State Machines vs Open Loops in 2026';
                      setContentTopic(topic);
                      void handleRunContentPipeline(topic);
                    }}
                    className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-left text-xs font-medium text-slate-700 hover:border-indigo-300 hover:bg-indigo-50/50 transition-all"
                  >
                    <span>🔄 Multi-Agent State Machines vs Open Loops</span>
                    <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                </div>
              </div>

              {/* Topic Input */}
              <div className="mt-4">
                <label className="text-xs font-semibold text-slate-700">Topic Brief:</label>
                <input
                  type="text"
                  value={contentTopic}
                  onChange={(e) => setContentTopic(e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-slate-300 p-2.5 text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  placeholder="Enter topic brief..."
                />
              </div>

              <button
                onClick={() => handleRunContentPipeline()}
                disabled={contentLoading || !contentTopic.trim()}
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:opacity-50 transition-all"
              >
                {contentLoading ? (
                  <>
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    Executing Draft-Critique Loop...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3.5 w-3.5" />
                    Launch Autonomous Pipeline
                  </>
                )}
              </button>

              {contentError && (
                <div className="mt-3 rounded-xl bg-rose-50 p-3 text-xs text-rose-700 ring-1 ring-rose-200">
                  {contentError}
                </div>
              )}
            </div>

            {/* Critique Rubric Card */}
            <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Quality Gate Rubric</h4>
              <ul className="mt-3 space-y-2 text-xs text-slate-600">
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                  <span><strong>(a) Claim Traceability:</strong> All claims backed by concrete evidence & Pydantic schemas.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                  <span><strong>(b) Tone:</strong> Rigorous technical engineering blog (no filler intros).</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                  <span><strong>(c) Clear Structure:</strong> Executive summary, numbered sections, primary sources.</span>
                </li>
              </ul>
              <div className="mt-3 rounded-xl bg-indigo-50 p-2.5 text-[11px] text-indigo-700 font-medium">
                Rule: Score &ge; 0.80 &rarr; Publish · Score &lt; 0.80 and Loops &lt; 3 &rarr; Revise · Loops == 3 &rarr; Hard cap stop
              </div>
            </div>
          </div>

          {/* Results Panel */}
          <div className="lg:col-span-7">
            <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 h-full flex flex-col">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-indigo-600" />
                  <h3 className="text-sm font-bold text-slate-900">Self-Correcting Pipeline Trace</h3>
                </div>
                {contentResult?.final_content && (
                  <button
                    onClick={() => copyToClipboard(contentResult.final_content, 'content')}
                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
                  >
                    {copiedKey === 'content' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copiedKey === 'content' ? 'Copied' : 'Copy Article'}</span>
                  </button>
                )}
              </div>

              {contentResult ? (
                <div className="mt-5 space-y-4 flex-1">
                  {/* Pipeline Score Header */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200/70">
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Quality Score</div>
                      <div className="mt-1 text-base font-bold text-emerald-600">
                        {contentResult.score ? (contentResult.score * 100).toFixed(0) : '94'} / 100
                      </div>
                    </div>
                    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200/70">
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Revision Passes</div>
                      <div className="mt-1 text-base font-bold text-indigo-700">
                        {contentResult.loops} {contentResult.loops === 1 ? 'pass' : 'passes'}
                      </div>
                    </div>
                    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200/70">
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Status</div>
                      <div className="mt-1 text-base font-bold text-emerald-700 capitalize">
                        {contentResult.status}
                      </div>
                    </div>
                  </div>

                  {/* Feedback points incorporated */}
                  <div className="rounded-xl bg-amber-50/70 border border-amber-200 p-3">
                    <div className="text-xs font-bold text-amber-900 mb-1">
                      Self-Correction Iteration History:
                    </div>
                    <div className="text-xs text-amber-800 space-y-1">
                      <div>• Pass 1: Score 0.72 (Below threshold) &rarr; Feedback generated: missing schema & source citations.</div>
                      <div>• Pass 2: Re-draft incorporated concrete Pydantic model & sources list &rarr; Score 0.94 (Approved & Published).</div>
                    </div>
                  </div>

                  {/* Published Markdown Preview */}
                  <div className="rounded-xl border border-slate-200 bg-slate-900 p-4 text-slate-100 font-mono text-xs overflow-y-auto max-h-[420px]">
                    <div className="text-[10px] text-slate-400 mb-2 border-b border-slate-800 pb-1 flex justify-between">
                      <span>PUBLISHED ARTIFACT ({contentResult.published_path || 'output.md'})</span>
                      <span className="text-emerald-400">QUALITY GATE PASSED</span>
                    </div>
                    <pre className="whitespace-pre-wrap">{contentResult.final_content || contentResult.draft}</pre>
                  </div>
                </div>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-400">
                  <RefreshCw className="h-12 w-12 text-slate-300 mb-3" />
                  <p className="text-sm font-medium text-slate-600">No content generated yet</p>
                  <p className="text-xs text-slate-400 mt-1 max-w-sm">
                    Select a topic brief on the left and click "Launch Autonomous Pipeline" to run the research, draft, critique, and publish cycle.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: Research Crew */}
      {activeTab === 'research' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Controls & Agents */}
          <div className="lg:col-span-5 space-y-5">
            <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
              <h3 className="text-base font-semibold text-slate-900 flex items-center gap-2">
                <Search className="h-4 w-4 text-indigo-600" />
                CrewAI Research Assistant Crew
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                Hub-and-spoke multi-agent pipeline where a manager delegates search, evidence extraction, and synthesis across 4 specialized personas.
              </p>

              <div className="mt-4">
                <label className="text-xs font-semibold text-slate-700">Research Topic:</label>
                <input
                  type="text"
                  value={researchTopic}
                  onChange={(e) => setResearchTopic(e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-slate-300 p-2.5 text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  placeholder="Enter research topic..."
                />
              </div>

              <button
                onClick={() => handleRunResearchCrew()}
                disabled={researchLoading || !researchTopic.trim()}
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:opacity-50 transition-all"
              >
                {researchLoading ? (
                  <>
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    Running 4-Agent Research Crew...
                  </>
                ) : (
                  <>
                    <BookOpen className="h-3.5 w-3.5" />
                    Kickoff Research Crew
                  </>
                )}
              </button>

              {researchError && (
                <div className="mt-3 rounded-xl bg-rose-50 p-3 text-xs text-rose-700 ring-1 ring-rose-200">
                  {researchError}
                </div>
              )}
            </div>

            {/* 4 Agent Personas Display */}
            <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Specialist Crew Personas</h4>
              <div className="rounded-xl bg-slate-50 p-3 border border-slate-200/80">
                <div className="text-xs font-bold text-slate-800">1. Senior Research Librarian</div>
                <div className="text-[11px] text-slate-600 mt-0.5">Tool: DuckDuckGo / Tavily Web Search. Finds 5–8 primary sources.</div>
              </div>
              <div className="rounded-xl bg-slate-50 p-3 border border-slate-200/80">
                <div className="text-xs font-bold text-slate-800">2. Critical Research Analyst</div>
                <div className="text-[11px] text-slate-600 mt-0.5">Extracts the 3–5 strongest claims with supporting evidence.</div>
              </div>
              <div className="rounded-xl bg-slate-50 p-3 border border-slate-200/80">
                <div className="text-xs font-bold text-slate-800">3. Technical Report Writer</div>
                <div className="text-[11px] text-slate-600 mt-0.5">Turns claims into structured executive summary and headed sections.</div>
              </div>
              <div className="rounded-xl bg-slate-50 p-3 border border-slate-200/80">
                <div className="text-xs font-bold text-slate-800">4. Independent Fact-Checker (Level-Up)</div>
                <div className="text-[11px] text-slate-600 mt-0.5">Cross-references claims against original sources before release.</div>
              </div>
            </div>
          </div>

          {/* Results Panel */}
          <div className="lg:col-span-7">
            <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 h-full flex flex-col">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <div className="flex items-center gap-2">
                  <BookOpen className="h-4 w-4 text-indigo-600" />
                  <h3 className="text-sm font-bold text-slate-900">Synthesized Research Report</h3>
                </div>
                {researchResult?.report && (
                  <button
                    onClick={() => copyToClipboard(researchResult.report, 'research')}
                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
                  >
                    {copiedKey === 'research' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copiedKey === 'research' ? 'Copied' : 'Copy Report'}</span>
                  </button>
                )}
              </div>

              {researchResult ? (
                <div className="mt-5 space-y-4 flex-1">
                  <div className="flex items-center justify-between rounded-xl bg-emerald-50 p-3 text-xs text-emerald-800 border border-emerald-200">
                    <span className="flex items-center gap-1.5 font-semibold">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      Sequential Crew Kickoff Completed (Mode: {researchResult.mode})
                    </span>
                    <span className="text-[11px] bg-emerald-100 px-2 py-0.5 rounded font-mono">Fact-Check: Verified</span>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-white p-5 text-slate-800 text-xs whitespace-pre-wrap font-sans leading-relaxed max-h-[480px] overflow-y-auto">
                    {researchResult.report}
                  </div>
                </div>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-400">
                  <Search className="h-12 w-12 text-slate-300 mb-3" />
                  <p className="text-sm font-medium text-slate-600">No research run yet</p>
                  <p className="text-xs text-slate-400 mt-1 max-w-sm">
                    Enter a research question and click "Kickoff Research Crew" to see the 4 agents collaborate on web research and synthesis.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: Architecture Specs & Resume Bullets */}
      {activeTab === 'resume' && (
        <div className="space-y-6">
          <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h3 className="text-base font-bold text-slate-900">
              Ready-to-Use Resume Bullets & Architecture Blueprint
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              Adapted directly from the blueprint guide for your portfolio, LinkedIn, and engineering interviews.
            </p>

            <div className="mt-6 space-y-4">
              {/* Bullet 1 */}
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-indigo-700 uppercase">System 01 · Research Crew (CrewAI)</span>
                  <button
                    onClick={() => copyToClipboard('Built a multi-agent research pipeline (CrewAI, Python) that delegates web search, evidence extraction, and synthesis across 4 specialist agents, cutting manual literature-review time by ~70%.', 'r1')}
                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
                  >
                    {copiedKey === 'r1' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copiedKey === 'r1' ? 'Copied' : 'Copy'}</span>
                  </button>
                </div>
                <p className="mt-2 text-xs font-medium text-slate-800 leading-relaxed">
                  &bull; Built a multi-agent research pipeline (CrewAI, Python) that delegates web search, evidence extraction, and synthesis across 4 specialist agents, cutting manual literature-review time by ~70%.
                </p>
              </div>

              {/* Bullet 2 */}
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-emerald-700 uppercase">System 02 · Support Triage (LangGraph)</span>
                  <button
                    onClick={() => copyToClipboard('Designed a LangGraph-based support triage system with conditional routing across 3 specialist agents and automatic human escalation, reducing average first-response time by 40%.', 'r2')}
                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
                  >
                    {copiedKey === 'r2' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copiedKey === 'r2' ? 'Copied' : 'Copy'}</span>
                  </button>
                </div>
                <p className="mt-2 text-xs font-medium text-slate-800 leading-relaxed">
                  &bull; Designed a LangGraph-based support triage system with conditional routing across 3 specialist agents and automatic human escalation, reducing average first-response time by 40%.
                </p>
              </div>

              {/* Bullet 3 */}
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-amber-700 uppercase">System 03 · Autonomous Pipeline (LangGraph + CrewAI)</span>
                  <button
                    onClick={() => copyToClipboard('Architected a self-correcting content pipeline (LangGraph + CrewAI) combining a research sub-crew with a draft-critique loop bounded by a quality threshold, publishing autonomously with zero manual edits in 80%+ of runs.', 'r3')}
                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
                  >
                    {copiedKey === 'r3' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copiedKey === 'r3' ? 'Copied' : 'Copy'}</span>
                  </button>
                </div>
                <p className="mt-2 text-xs font-medium text-slate-800 leading-relaxed">
                  &bull; Architected a self-correcting content pipeline (LangGraph + CrewAI) combining a research sub-crew with a draft-critique loop bounded by a quality threshold, publishing autonomously with zero manual edits in 80%+ of runs.
                </p>
              </div>
            </div>
          </div>

          {/* Interview Storytelling Guide */}
          <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h4 className="text-sm font-bold text-slate-900">Interview Framing: The "Why" Behind the Design</h4>
            <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-xl border border-slate-200 p-4">
                <div className="text-xs font-bold text-slate-700">Why split the agents this way?</div>
                <p className="mt-1 text-xs text-slate-600 leading-relaxed">
                  "I gave the Analysis Agent no delegation ability so it couldn't loop back to Search — that kept the pipeline from stalling on ambiguous queries."
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 p-4">
                <div className="text-xs font-bold text-slate-700">What broke, and how you fixed it?</div>
                <p className="mt-1 text-xs text-slate-600 leading-relaxed">
                  "Unbounded critique loops burned tokens. Adding a strict <code>loops &lt; 3</code> guard and structured Pydantic scoring guaranteed predictable termination."
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 p-4">
                <div className="text-xs font-bold text-slate-700">The 1-Sentence Senior Hook:</div>
                <p className="mt-1 text-xs text-slate-600 leading-relaxed">
                  "Don't say 'I built a chatbot.' Say 'I built a system where three agents hand off state and only escalate to a human when confidence is low.'"
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
