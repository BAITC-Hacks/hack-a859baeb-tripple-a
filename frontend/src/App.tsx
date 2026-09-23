import Markdown from "react-markdown";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent, ReactNode } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleHelp,
  Clipboard,
  FileCheck2,
  FileSearch,
  FileText,
  Files,
  GitCompareArrows,
  LayoutDashboard,
  LoaderCircle,
  Network,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import type {
  Analysis,
  AnalysisResult,
  Evidence,
  Finding,
  FunctionMapping,
  Health,
  Mode,
  Side,
  SourceDocument,
  UnitMapping,
} from "./types";
import { api } from "./api";

type View = "dashboard" | "new" | "analysis";
type ResultTab =
  "overview" | "organization" | "functions" | "findings" | "report";
const stages = [
  "Reading documents",
  "Extracting organizational units",
  "Extracting functions",
  "Matching organizational units",
  "Comparing functions",
  "Reviewing losses, duplicates and conflicts",
  "Validating source evidence",
  "Generating the analytical report",
];
const labels: Record<string, string> = {
  unchanged: "Unchanged",
  renamed: "Renamed",
  reorganized: "Reorganized",
  removed: "Removed",
  created: "Created",
  uncertain: "Needs review",
  equivalent: "Equivalent",
  modified: "Modified",
  transferred: "Transferred",
  potential_loss: "Potential loss",
  new: "New function",
  queued: "Queued",
  running: "In progress",
  completed: "Completed",
  failed: "Failed",
  high: "High priority",
  medium: "Medium priority",
  low: "Low priority",
};
const categoryLabels: Record<Finding["category"], string> = {
  loss: "Lost functions",
  duplication: "Duplicated functions",
  overlap: "Responsibility overlaps",
  conflict: "Potential conflicts of interest",
  uncertain: "Uncertain findings",
};
const categoryOrder: Finding["category"][] = [
  "loss",
  "duplication",
  "overlap",
  "conflict",
  "uncertain",
];
const describeError = (e: unknown) =>
  e instanceof Error
    ? e.message
    : "An unexpected error occurred. Please try again.";
const date = (value: string) =>
  new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
const percent = (confidence: number) => `${Math.round(confidence * 100)}%`;
const fileKey = (file: File) =>
  `${file.name}-${file.size}-${file.lastModified}`;

function Badge({ value, children }: { value: string; children?: ReactNode }) {
  return (
    <span className={`badge badge-${value}`}>
      {children || labels[value] || value}
    </span>
  );
}
function ErrorMessage({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="notice error" role="alert">
      <CircleAlert size={18} />
      <div>{message}</div>
      {retry && (
        <button className="text-button" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
function ModeBadge({ mode }: { mode: Mode }) {
  return (
    <span className={`mode-badge ${mode}`}>
      <span className="mode-dot" />
      {mode === "openai" ? "OpenAI analysis" : "Local lexical review"}
    </span>
  );
}
function Loading({ text = "Loading analysis…" }: { text?: string }) {
  return (
    <div className="loading-state" role="status">
      <LoaderCircle className="spin" size={26} />
      <p>{text}</p>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("dashboard");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [listError, setListError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [initialLoading, setInitialLoading] = useState(true);
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoError, setDemoError] = useState("");
  const [tab, setTab] = useState<ResultTab>("overview");
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    const [healthResult, listResult] = await Promise.allSettled([
      api.health(),
      api.list(),
    ]);
    if (healthResult.status === "fulfilled") setHealth(healthResult.value);
    else setHealth(null);
    if (listResult.status === "fulfilled") {
      setAnalyses(listResult.value);
      setListError("");
    } else setListError(describeError(listResult.reason));
    setInitialLoading(false);
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    const route = () => {
      const hash = location.hash.slice(1);
      if (hash.startsWith("analysis/")) {
        setView("analysis");
        setSelectedId(decodeURIComponent(hash.slice(9)));
      } else {
        setView(hash === "new" ? "new" : "dashboard");
        setSelectedId(null);
      }
      setTab("overview");
      setDetailError("");
    };
    route();
    window.addEventListener("hashchange", route);
    return () => window.removeEventListener("hashchange", route);
  }, []);
  const navigate = (next: View, id?: string) => {
    location.hash =
      next === "analysis" && id
        ? `analysis/${encodeURIComponent(id)}`
        : next === "new"
          ? "new"
          : "";
  };
  useEffect(() => {
    if (view !== "analysis" || !selectedId) return;
    let alive = true;
    setAnalysis(null);
    setDetailError("");
    const poll = async () => {
      try {
        const next = await api.get(selectedId);
        if (!alive) return;
        setAnalysis(next);
        setDetailError("");
        if (next.status === "queued" || next.status === "running")
          pollTimer.current = setTimeout(() => void poll(), 1500);
        else void refresh();
      } catch (e) {
        if (!alive) return;
        setDetailError(describeError(e));
        pollTimer.current = setTimeout(() => void poll(), 5000);
      }
    };
    void poll();
    return () => {
      alive = false;
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [selectedId, view, refresh]);

  const startDemo = async () => {
    setDemoLoading(true);
    setDemoError("");
    try {
      const next = await api.demo("local");
      navigate("analysis", next.id);
      void refresh();
    } catch (e) {
      setDemoError(describeError(e));
    } finally {
      setDemoLoading(false);
    }
  };
  const onCreated = (created: Analysis) => {
    navigate("analysis", created.id);
    void refresh();
  };
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main navigation">
        <a className="brand" href="#" aria-label="AlemScope home">
          <span className="brand-mark">
            <Network size={24} />
          </span>
          <span>
            Alem<span className="brand-light">Scope</span>
            <small>Organizational intelligence</small>
          </span>
        </a>
        <div className="workspace-label">
          <span className="workspace-avatar">H</span>
          <span>
            HackAlem workspace<small>Local prototype</small>
          </span>
        </div>
        <nav>
          <button
            className={`nav-item ${view === "dashboard" ? "active" : ""}`}
            onClick={() => navigate("dashboard")}
          >
            <LayoutDashboard size={18} />
            <span>Overview</span>
          </button>
          <button
            className={`nav-item ${view === "new" ? "active" : ""}`}
            onClick={() => navigate("new")}
          >
            <GitCompareArrows size={18} />
            <span>New analysis</span>
            <Plus className="nav-plus" size={15} />
          </button>
        </nav>
        <div className="sidebar-recent">
          <div className="sidebar-label">Recent analyses</div>
          {analyses.slice(0, 4).map((item) => (
            <button
              key={item.id}
              title={item.title}
              onClick={() => navigate("analysis", item.id)}
              className={`recent-link ${selectedId === item.id ? "selected" : ""}`}
            >
              <FileSearch size={15} />
              <span>{item.title}</span>
            </button>
          ))}
          {!analyses.length && <p>Your analyses will appear here.</p>}
        </div>
        <div className="sidebar-bottom">
          <ShieldCheck size={20} />
          <div>
            Evidence first
            <small>Every recommendation needs human validation.</small>
          </div>
        </div>
        <div className="profile">
          <span className="profile-avatar">HA</span>
          <div>
            Analyst workspace<small>Hackathon edition</small>
          </div>
          <span className="profile-dot" />
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <strong>
              {view === "new"
                ? "New analysis"
                : view === "analysis"
                  ? "Analysis workspace"
                  : "Overview"}
            </strong>
          </div>
          <div className="service-state">
            <span className={health ? "online" : "offline"} />
            {health
              ? "Analysis service connected"
              : initialLoading
                ? "Connecting…"
                : "Service unavailable"}
            {!health && !initialLoading && (
              <button className="text-button" onClick={() => void refresh()}>
                Reconnect
              </button>
            )}
          </div>
        </header>
        <main className="main-content">
          {view === "dashboard" && (
            <Dashboard
              analyses={analyses}
              loading={initialLoading}
              error={listError}
              refresh={() => void refresh()}
              onNew={() => navigate("new")}
              onOpen={(id) => navigate("analysis", id)}
              onDemo={() => void startDemo()}
              demoLoading={demoLoading}
              demoError={demoError}
            />
          )}
          {view === "new" && (
            <NewAnalysis
              health={health}
              onCreated={onCreated}
              onBack={() => navigate("dashboard")}
            />
          )}
          {view === "analysis" && (
            <>
              {detailError && <ErrorMessage message={detailError} />}
              {!analysis ? (
                !detailError && <Loading />
              ) : (
                <AnalysisView
                  analysis={analysis}
                  tab={tab}
                  setTab={setTab}
                  onBack={() => navigate("dashboard")}
                  onNew={() => navigate("new")}
                />
              )}
            </>
          )}
        </main>
        <footer className="app-footer">
          <span>AlemScope · HackAlem AI prototype</span>
          <span>Source-backed recommendations. Human decisions.</span>
        </footer>
      </div>
    </div>
  );
}

function Dashboard({
  analyses,
  loading,
  error,
  refresh,
  onNew,
  onOpen,
  onDemo,
  demoLoading,
  demoError,
}: {
  analyses: Analysis[];
  loading: boolean;
  error: string;
  refresh: () => void;
  onNew: () => void;
  onOpen: (id: string) => void;
  onDemo: () => void;
  demoLoading: boolean;
  demoError: string;
}) {
  const completed = analyses.filter((a) => a.status === "completed").length;
  const active = analyses.filter(
    (a) => a.status === "running" || a.status === "queued",
  ).length;
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>
            See what changes.
            <br className="mobile-break" /> Keep what matters.
          </h1>
          <p>
            Compare organizational structures and responsibilities, with
            evidence for every conclusion.
          </p>
        </div>
        <button className="button primary" onClick={onNew}>
          <Plus size={17} />
          New analysis
        </button>
      </div>
      {error && <ErrorMessage message={error} retry={refresh} />}
      <section className="intro-panel" aria-label="How AlemScope works">
        <div className="intro-copy">
          <span className="feature-label">
            <GitCompareArrows size={16} /> Before and after, made clear
          </span>
          <h2>
            Organizational change.
            <br />
            An accountable review.
          </h2>
          <p>
            Find shifts in ownership, potentially lost functions, and
            overlapping responsibilities. Follow every finding back to its
            source.
          </p>
          <button
            className="button secondary"
            disabled={demoLoading}
            onClick={onDemo}
          >
            {demoLoading ? (
              <LoaderCircle size={17} className="spin" />
            ) : (
              <FileSearch size={17} />
            )}
            {demoLoading
              ? "Reading sample documents…"
              : "Explore the supplied documents"}
            <ArrowUpRight size={16} />
          </button>
          <small>
            Internal audit regulations · revisions 8 and 9 · local lexical
            review
          </small>
        </div>
        <div
          className="comparison-illustration"
          aria-label="Before documents are compared with after documents to create an evidence-backed review"
        >
          <div className="illustration-side">
            <span className="side-label before">Before</span>
            <div className="doc-illustration">
              <FileText size={22} />
              <span />
              <span />
              <span className="short" />
              <div className="mini-units">
                <i />
                <i />
                <i />
              </div>
            </div>
          </div>
          <div className="illustration-connector">
            <span />
            <div>
              <GitCompareArrows size={22} />
            </div>
            <span />
          </div>
          <div className="illustration-side">
            <span className="side-label after">After</span>
            <div className="doc-illustration after">
              <FileCheck2 size={22} />
              <span />
              <span />
              <span className="short" />
              <div className="mini-units">
                <i />
                <i />
                <i />
              </div>
            </div>
          </div>
          <div className="evidence-seal">
            <ShieldCheck size={16} />
            Traceable to the source
          </div>
        </div>
      </section>
      {demoError && <ErrorMessage message={demoError} />}
      <div className="workspace-statistics">
        <div>
          <span className="stat-icon">
            <Files size={19} />
          </span>
          <div>
            <strong>{analyses.length}</strong>
            <span>Total analyses</span>
          </div>
        </div>
        <div>
          <span className="stat-icon">
            <CheckCheck size={19} />
          </span>
          <div>
            <strong>{completed}</strong>
            <span>Completed reviews</span>
          </div>
        </div>
        <div>
          <span className="stat-icon">
            <GitCompareArrows size={19} />
          </span>
          <div>
            <strong>{active}</strong>
            <span>In progress</span>
          </div>
        </div>
      </div>
      <section className="panel recent-panel">
        <div className="panel-heading">
          <div>
            <h2>Recent analyses</h2>
            <p>Your document comparisons in one place.</p>
          </div>
          <span className="count-pill">{analyses.length}</span>
        </div>
        {loading ? (
          <Loading text="Loading your workspace…" />
        ) : analyses.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Analysis</th>
                  <th>Review mode</th>
                  <th>Created</th>
                  <th>Status</th>
                  <th>
                    <span className="sr-only">Open</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {analyses.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <button
                        className="analysis-link"
                        onClick={() => onOpen(item.id)}
                      >
                        <span className="file-icon">
                          <FileSearch size={20} />
                        </span>
                        <span>{item.title}</span>
                      </button>
                    </td>
                    <td>
                      <ModeBadge mode={item.mode} />
                    </td>
                    <td className="muted nowrap">{date(item.created_at)}</td>
                    <td>
                      <Badge value={item.status} />
                    </td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={`Open ${item.title}`}
                        onClick={() => onOpen(item.id)}
                      >
                        <ArrowUpRight size={17} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-icon">
              <Files size={26} />
            </div>
            <h3>Your first comparison starts here</h3>
            <p>
              Add documents from before and after a restructuring, or explore
              the supplied audit regulations.
            </p>
            <button className="text-button" onClick={onNew}>
              Create an analysis <ArrowRight size={16} />
            </button>
          </div>
        )}
      </section>
      <div className="method-note">
        <ShieldCheck size={19} />
        <p>
          <strong>Built for review, backed by evidence.</strong> Findings are
          recommendations, not confirmed organizational facts. Validate them
          against the source documents before taking action.
        </p>
      </div>
    </>
  );
}

function NewAnalysis({
  health,
  onCreated,
  onBack,
}: {
  health: Health | null;
  onCreated: (analysis: Analysis) => void;
  onBack: () => void;
}) {
  const [title, setTitle] = useState("");
  const [before, setBefore] = useState<File[]>([]);
  const [after, setAfter] = useState<File[]>([]);
  const [mode, setMode] = useState<Mode>("local");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (
      [...before, ...after].reduce((sum, file) => sum + file.size, 0) >
      60 * 1024 * 1024
    ) {
      setError(
        "The document sets exceed 60 MB in total. Remove some files before running the analysis.",
      );
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await api.create(
        title.trim() || "Organizational review",
        mode,
        before,
        after,
      );
      onCreated(result);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button className="back-link" onClick={onBack}>
        <ArrowLeft size={16} />
        Back to overview
      </button>
      <div className="page-heading">
        <div>
          <h1>New organizational analysis</h1>
          <p>
            Bring both sides of the change. AlemScope will connect
            responsibilities to their sources.
          </p>
        </div>
      </div>
      <div className="panel setup-panel">
        <label className="field-label" htmlFor="analysis-title">
          Analysis name <span>Optional</span>
        </label>
        <input
          id="analysis-title"
          className="text-input title-input"
          value={title}
          maxLength={160}
          disabled={busy}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Internal audit restructuring review"
        />
        <div className="field-hint">
          A clear name makes this review easier to find later.
        </div>
      </div>
      <div className="upload-comparison">
        <UploadZone
          side="before"
          files={before}
          setFiles={setBefore}
          disabled={busy}
        />
        <div className="upload-arrow">
          <ArrowRight size={21} />
        </div>
        <UploadZone
          side="after"
          files={after}
          setFiles={setAfter}
          disabled={busy}
        />
      </div>
      <section className="panel mode-panel">
        <div className="panel-heading">
          <div>
            <h2>Choose the review method</h2>
            <p>Both methods preserve references to your uploaded documents.</p>
          </div>
          <ShieldCheck size={21} />
        </div>
        <div className="mode-options">
          <label className={`mode-option ${mode === "local" ? "chosen" : ""}`}>
            <input
              type="radio"
              name="mode"
              checked={mode === "local"}
              disabled={busy}
              onChange={() => setMode("local")}
            />
            <div>
              <strong>
                <FileSearch size={17} />
                Local lexical review
              </strong>
              <p>
                Compare wording and explicit responsibility statements locally.
                Limited matching; not semantic AI.
              </p>
              <span className="option-tag">No API key required</span>
            </div>
          </label>
          <label
            className={`mode-option ${mode === "openai" ? "chosen" : ""} ${!health?.openai_configured ? "unavailable" : ""}`}
          >
            <input
              type="radio"
              name="mode"
              checked={mode === "openai"}
              disabled={!health?.openai_configured || busy}
              onChange={() => setMode("openai")}
            />
            <div>
              <strong>
                <Sparkles size={17} />
                OpenAI semantic analysis
              </strong>
              <p>
                Interpret functions and organizational changes through staged AI
                analysis with evidence checks.
              </p>
              <span className="option-tag">
                {health?.openai_configured
                  ? "Available"
                  : "API key required on the server"}
              </span>
            </div>
          </label>
        </div>
        {mode === "openai" && (
          <p className="privacy-note">
            Document text will be sent to OpenAI for this analysis. Use
            documents you are authorized to process.
          </p>
        )}
      </section>
      <div className="notice neutral">
        <ShieldCheck size={19} />
        <div>
          Every finding is a recommendation for human review. A missing match
          does not prove that a function was removed.
        </div>
      </div>
      {error && <ErrorMessage message={error} />}
      <div className="run-bar">
        <div>
          <strong>
            {before.length + after.length} document
            {before.length + after.length === 1 ? "" : "s"} selected
          </strong>
          <span>
            {before.length} before · {after.length} after
          </span>
        </div>
        <button
          className="button primary"
          onClick={() => void run()}
          disabled={busy || !before.length || !after.length || !health}
        >
          {busy ? (
            <LoaderCircle className="spin" size={18} />
          ) : (
            <GitCompareArrows size={18} />
          )}
          {busy ? "Uploading and reading documents…" : "Run analysis"}
        </button>
      </div>
      {busy && (
        <p className="upload-status" role="status">
          The server is validating and reading your files. The analysis
          workspace opens when ingestion finishes.
        </p>
      )}
    </>
  );
}

function UploadZone({
  side,
  files,
  setFiles,
  disabled,
}: {
  side: Side;
  files: File[];
  setFiles: (files: File[]) => void;
  disabled: boolean;
}) {
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState("");
  const add = (incoming: File[]) => {
    setError("");
    const accepted = [...files];
    const errors: string[] = [];
    for (const file of incoming) {
      if (!/\.(pdf|docx|xlsx)$/i.test(file.name)) {
        errors.push(`${file.name}: choose PDF, DOCX, or XLSX.`);
        continue;
      }
      if (!file.size) {
        errors.push(`${file.name}: this file is empty.`);
        continue;
      }
      if (file.size > 20 * 1024 * 1024) {
        errors.push(`${file.name}: maximum file size is 20 MB.`);
        continue;
      }
      if (accepted.some((f) => fileKey(f) === fileKey(file))) continue;
      if (accepted.length >= 10) {
        errors.push("You can add up to 10 files per document set.");
        break;
      }
      accepted.push(file);
    }
    setFiles(accepted);
    setError(errors.join(" "));
  };
  const inputChange = (event: ChangeEvent<HTMLInputElement>) => {
    add(Array.from(event.target.files || []));
    event.target.value = "";
  };
  const drop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDrag(false);
    if (!disabled) add(Array.from(event.dataTransfer.files));
  };
  return (
    <section className={`upload-panel ${side}`}>
      <div className="upload-panel-header">
        <span className={`side-label ${side}`}>
          {side === "before" ? "Before" : "After"}
        </span>
        <span className="muted">
          {side === "before"
            ? "Original organization"
            : "Restructured organization"}
        </span>
      </div>
      <div
        className={`dropzone ${drag ? "dragging" : ""} ${disabled ? "disabled" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={drop}
      >
        <span className="upload-icon">
          <Upload size={25} />
        </span>
        <h3>
          {side === "before"
            ? "Add the original documents"
            : "Add the updated documents"}
        </h3>
        <p>
          Drag files here or{" "}
          <label className="browse-link" htmlFor={`file-${side}`}>
            browse files
          </label>
        </p>
        <input
          className="file-input"
          id={`file-${side}`}
          type="file"
          multiple
          accept=".pdf,.docx,.xlsx"
          disabled={disabled}
          onChange={inputChange}
          aria-label={`Upload ${side} restructuring documents`}
        />
        <small>PDF, DOCX, XLSX · up to 20 MB each · 10 files</small>
      </div>
      {!!files.length && (
        <ul className="upload-file-list">
          {files.map((file) => (
            <li key={fileKey(file)}>
              <span className="file-icon small">
                <FileText size={18} />
              </span>
              <div>
                <strong title={file.name}>{file.name}</strong>
                <span>
                  {file.name.split(".").at(-1)?.toUpperCase()} ·{" "}
                  {(file.size / 1024).toFixed(0)} KB{" "}
                  <span className="ready-text">
                    <Check size={11} />
                    {disabled ? "Uploading" : "Ready"}
                  </span>
                </span>
              </div>
              <button
                className="icon-button"
                aria-label={`Remove ${file.name} from ${side}`}
                disabled={disabled}
                onClick={() =>
                  setFiles(files.filter((f) => fileKey(f) !== fileKey(file)))
                }
              >
                <X size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <div className="upload-error" role="alert">
          {error}
        </div>
      )}
    </section>
  );
}

function AnalysisView({
  analysis,
  tab,
  setTab,
  onBack,
  onNew,
}: {
  analysis: Analysis;
  tab: ResultTab;
  setTab: (tab: ResultTab) => void;
  onBack: () => void;
  onNew: () => void;
}) {
  const documents = analysis.documents || [];
  const result = analysis.result;
  return (
    <>
      <button className="back-link" onClick={onBack}>
        <ArrowLeft size={16} />
        All analyses
      </button>
      <div className="page-heading analysis-heading">
        <div>
          <div className="analysis-meta">
            <ModeBadge mode={analysis.mode} />
            <span>{date(analysis.created_at)}</span>
            <Badge value={analysis.status} />
          </div>
          <h1>{analysis.title}</h1>
          <p>
            {documents.filter((d) => d.side === "before").length} before
            document(s) <ArrowRight size={14} />{" "}
            {documents.filter((d) => d.side === "after").length} after
            document(s)
          </p>
        </div>
        {result && (
          <a
            className="button secondary"
            href={`/api/analyses/${encodeURIComponent(analysis.id)}/report`}
            download
          >
            <ArrowDownToLine size={16} />
            Export report
          </a>
        )}
      </div>
      {analysis.mode === "local" && (
        <div className="notice caution">
          <CircleHelp size={19} />
          <div>
            <strong>Local lexical review</strong>
            <span>
              “Unchanged” identifies matching names or wording only. It does not establish continuity of ownership or scope. Local mode does not assess contextual conflicts. All comparisons need human validation.
            </span>
          </div>
        </div>
      )}
      {analysis.status === "failed" ? (
        <section className="panel failed-panel">
          <CircleAlert size={30} />
          <h2>Analysis could not be completed</h2>
          <p>{analysis.error || "The analysis service returned an error."}</p>
          <button className="button primary" onClick={onNew}>
            <Plus size={17} />
            Start a new analysis
          </button>
        </section>
      ) : analysis.status !== "completed" ? (
        <Progress analysis={analysis} />
      ) : result ? (
        <>
          <div
            className="result-tabs"
            role="tablist"
            aria-label="Analysis results"
          >
            {(
              [
                "overview",
                "organization",
                "functions",
                "findings",
                "report",
              ] as ResultTab[]
            ).map((value) => (
              <button
                key={value}
                id={`tab-${value}`}
                role="tab"
                aria-selected={tab === value}
                aria-controls={`panel-${value}`}
                onClick={() => setTab(value)}
                className={tab === value ? "selected" : ""}
              >
                {value === "overview"
                  ? "Executive summary"
                  : value === "organization"
                    ? "Organizational changes"
                    : value === "functions"
                      ? "Function comparison"
                      : value === "findings"
                        ? "Findings"
                        : "Analytical report"}
                {value === "findings" && <span>{result.findings.length}</span>}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            id={`panel-${tab}`}
            aria-labelledby={`tab-${tab}`}
          >
            {tab === "overview" && (
              <Overview result={result} documents={documents} setTab={setTab} />
            )}
            {tab === "organization" && (
              <Mappings result={result} documents={documents} kind="units" />
            )}
            {tab === "functions" && (
              <Mappings
                result={result}
                documents={documents}
                kind="functions"
              />
            )}
            {tab === "findings" && (
              <Findings result={result} documents={documents} />
            )}
            {tab === "report" && <Report analysis={analysis} result={result} />}
          </div>
        </>
      ) : (
        <ErrorMessage message="This completed analysis has no stored results. Start a new analysis to retry." />
      )}
    </>
  );
}

function Progress({ analysis }: { analysis: Analysis }) {
  return (
    <section className="panel progress-panel">
      <div className="progress-heading">
        <div className="progress-symbol">
          <Network size={30} />
        </div>
        <h2>Your documents are being analyzed</h2>
        <p>
          Each stage preserves the link between a conclusion and its source.
        </p>
        <div className="progress-current" role="status">
          <LoaderCircle className="spin" size={16} />
          {analysis.stage_label || stages[analysis.stage]}
        </div>
      </div>
      <ol className="progress-stages">
        {stages.map((stage, index) => (
          <li
            key={stage}
            className={
              index < analysis.stage
                ? "done"
                : index === analysis.stage
                  ? "current"
                  : ""
            }
          >
            <span>
              {index < analysis.stage ? (
                <Check size={16} />
              ) : index === analysis.stage ? (
                <LoaderCircle size={16} className="spin" />
              ) : (
                index + 1
              )}
            </span>
            <div>
              {stage}
              <small>
                {index < analysis.stage
                  ? "Complete"
                  : index === analysis.stage
                    ? "In progress"
                    : "Waiting"}
              </small>
            </div>
          </li>
        ))}
      </ol>
      <p className="progress-note">
        Progress reflects server processing stages. You can leave this page and
        return from recent analyses.
      </p>
    </section>
  );
}

function Overview({
  result,
  documents,
  setTab,
}: {
  result: AnalysisResult;
  documents: SourceDocument[];
  setTab: (tab: ResultTab) => void;
}) {
  const before = result.units.filter((u) => u.side === "before").length;
  const after = result.units.filter((u) => u.side === "after").length;
  const count = (status: UnitMapping["status"]) =>
    result.unit_mappings.filter((m) => m.status === status).length;
  const total = (category: Finding["category"]) =>
    result.findings.filter((f) => f.category === category).length;
  const metrics: {
    label: string;
    value: number;
    detail: string;
    tone?: string;
  }[] = [
    {
      label: "Units before",
      value: before,
      detail: "Extracted from original documents",
    },
    {
      label: "Units after",
      value: after,
      detail: "Extracted from updated documents",
    },
    {
      label: "Created units",
      value: count("created"),
      detail: "Potential additions",
    },
    {
      label: "Removed units",
      value: count("removed"),
      detail: "Potential removals",
    },
    {
      label: "Reorganized units",
      value: count("reorganized") + count("renamed"),
      detail: `Includes ${count("renamed")} rename suggestion(s)`,
    },
    {
      label: "Potential losses",
      value: total("loss"),
      detail: "Functions requiring review",
      tone: "warning",
    },
    {
      label: "Potential duplications",
      value: total("duplication"),
      detail: "Shared function suggestions",
      tone: "warning",
    },
    {
      label: "Potential conflicts",
      value: total("conflict"),
      detail: "Evidence-supported concerns",
      tone: "warning",
    },
  ];
  return (
    <>
      <div className="section-intro">
        <h2>What the documents tell us</h2>
        <p>
          An evidence-backed starting point for your review. All findings
          require human validation; confidence scores are not calibrated
          probabilities.
        </p>
      </div>
      <div className="metrics-grid">
        {metrics.map((metric) => (
          <div className={`metric ${metric.tone || ""}`} key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <small>{metric.detail}</small>
          </div>
        ))}
      </div>
      <div className="overview-columns">
        <section className="panel attention-panel">
          <div className="panel-heading">
            <div>
              <h2>Review priorities</h2>
              <p>
                {result.findings.length} recommendation(s) across the
                comparison.
              </p>
            </div>
            <CircleAlert size={21} />
          </div>
          {result.findings.length ? (
            <div className="priority-list">
              {result.findings.slice(0, 4).map((finding) => (
                <button key={finding.id} onClick={() => setTab("findings")}>
                  <span className={`priority-dot ${finding.severity}`} />
                  <div>
                    <strong>{finding.title}</strong>
                    <small>
                      {categoryLabels[finding.category]} ·{" "}
                      {finding.evidence.length} source reference(s)
                    </small>
                  </div>
                  <ChevronRight size={17} />
                </button>
              ))}
            </div>
          ) : (
            <div className="compact-empty">
              <ShieldCheck size={26} />
              <h3>No evidence-backed issues detected</h3>
              <p>
                This does not confirm the absence of organizational risks.
                Review the comparisons and extraction limits.
              </p>
            </div>
          )}
          <button
            className="panel-footer-link"
            onClick={() => setTab("findings")}
          >
            Review all findings
            <ArrowRight size={16} />
          </button>
        </section>
        <section className="panel scope-panel">
          <div className="panel-heading">
            <div>
              <h2>Analysis coverage</h2>
              <p>The source material behind this review.</p>
            </div>
            <Files size={21} />
          </div>
          <div className="coverage-row">
            <span>Documents analyzed</span>
            <strong>{documents.length}</strong>
          </div>
          <div className="coverage-row">
            <span>Source fragments</span>
            <strong>
              {documents.reduce((sum, doc) => sum + doc.chunks.length, 0)}
            </strong>
          </div>
          <div className="coverage-row">
            <span>Functions before / after</span>
            <strong>
              {result.functions.filter((f) => f.side === "before").length} /{" "}
              {result.functions.filter((f) => f.side === "after").length}
            </strong>
          </div>
          <div className="coverage-row">
            <span>Responsibility overlaps</span>
            <strong>{total("overlap")}</strong>
          </div>
          <div className="coverage-row">
            <span>Uncertain findings</span>
            <strong>{total("uncertain")}</strong>
          </div>
          <button
            className="panel-footer-link"
            onClick={() => setTab("functions")}
          >
            Inspect function mappings
            <ArrowRight size={16} />
          </button>
        </section>
      </div>
      <Warnings warnings={result.warnings} documents={documents} />
      <SourceDocuments documents={documents} />
    </>
  );
}

function SourceDocuments({ documents }: { documents: SourceDocument[] }) {
  return (
    <section className="panel source-documents">
      <div className="panel-heading">
        <div>
          <h2>Source documents</h2>
          <p>Source text stays attached to its original location.</p>
        </div>
      </div>
      <div className="source-document-list">
        {documents.map((doc) => (
          <div key={doc.id}>
            <FileText size={20} />
            <div>
              <strong>{doc.filename}</strong>
              <span>
                {doc.document_type.toUpperCase()} · {doc.chunks.length}{" "}
                extracted fragments
              </span>
            </div>
            <span className={`side-label ${doc.side}`}>
              {doc.side === "before" ? "Before" : "After"}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
function Warnings({
  warnings,
  documents,
}: {
  warnings: string[];
  documents: SourceDocument[];
}) {
  const all = [
    ...new Set([
      ...warnings,
      ...documents.flatMap((doc) =>
        doc.warnings.map((warning) => `${doc.filename}: ${warning}`),
      ),
    ]),
  ];
  return all.length ? (
    <details className="warnings">
      <summary>
        <CircleAlert size={17} />
        <strong>Review limits and uncertainties</strong>
        <span className="count-pill">{all.length}</span>
        <ChevronDown size={16} />
      </summary>
      <ul>
        {all.map((warning, index) => (
          <li key={index}>{warning}</li>
        ))}
      </ul>
    </details>
  ) : null;
}

function Mappings({
  result,
  documents,
  kind,
}: {
  result: AnalysisResult;
  documents: SourceDocument[];
  kind: "units" | "functions";
}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const unitNames = (ids: string[]) =>
    ids.map(
      (id) =>
        result.units.find((unit) => unit.id === id)?.name || "Unknown unit",
    );
  const functionDescriptions = (ids: string[]) =>
    ids.map(
      (id) =>
        result.functions.find((func) => func.id === id)?.description ||
        "Unknown function",
    );
  const mappings =
    kind === "units" ? result.unit_mappings : result.function_mappings;
  const getStatus = (mapping: UnitMapping | FunctionMapping) =>
    "status" in mapping ? mapping.status : mapping.match_type;
  const visible = mappings.filter(
    (mapping) =>
      (status === "all" || getStatus(mapping) === status) &&
      [
        ...(kind === "units"
          ? unitNames(mapping.before_ids)
          : functionDescriptions(mapping.before_ids)),
        ...(kind === "units"
          ? unitNames(mapping.after_ids)
          : functionDescriptions(mapping.after_ids)),
        mapping.explanation,
      ]
        .join(" ")
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const statuses = [...new Set(mappings.map(getStatus))];
  return (
    <>
      <div className="section-intro">
        <h2>
          {kind === "units" ? "Organizational changes" : "Function comparison"}
        </h2>
        <p>
          {kind === "units"
            ? "Trace organizational continuity, renaming, and potential structural changes."
            : "Review how responsibilities carry forward, change ownership, or need closer inspection."}
        </p>
      </div>
      <div className="filter-bar">
        <label className="search-input">
          <Search size={17} />
          <span className="sr-only">
            Search {kind === "units" ? "units" : "functions"}
          </span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={
              kind === "units"
                ? "Search organizational units…"
                : "Search functions…"
            }
          />
        </label>
        <label className="filter-select">
          <span className="sr-only">Filter by status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="all">All statuses</option>
            {statuses.map((value) => (
              <option key={value} value={value}>
                {labels[value]}
              </option>
            ))}
          </select>
        </label>
        <span className="result-count">{visible.length} mapping(s)</span>
      </div>
      <div className="comparison-table panel">
        <div className="comparison-header">
          <span>Before {kind === "units" ? "unit" : "function"}</span>
          <span />
          <span>After {kind === "units" ? "unit" : "function"}</span>
          <span>Assessment & evidence</span>
        </div>
        {visible.length ? (
          visible.map((mapping) => (
            <div
              className={`mapping-row ${getStatus(mapping) === "potential_loss" ? "loss-row" : ""}`}
              key={mapping.id}
            >
              <div className="mapping-content">
                <span className="mobile-column-label">Before</span>
                {(kind === "units"
                  ? unitNames(mapping.before_ids)
                  : functionDescriptions(mapping.before_ids)
                ).map((text, index) => (
                  <p key={index}>{text}</p>
                ))}
                {!mapping.before_ids.length && (
                  <span className="missing-value">
                    No source counterpart identified
                  </span>
                )}
                {kind === "functions" && (
                  <small>
                    {[
                      ...new Set(
                        mapping.before_ids
                          .map(
                            (id) =>
                              result.functions.find((f) => f.id === id)
                                ?.unit_id,
                          )
                          .filter((id): id is string => !!id),
                      ),
                    ]
                      .map((id) => unitNames([id])[0])
                      .join("; ")}
                  </small>
                )}
              </div>
              <div className="mapping-arrow">
                <ArrowRight size={17} />
              </div>
              <div className="mapping-content">
                <span className="mobile-column-label">After</span>
                {(kind === "units"
                  ? unitNames(mapping.after_ids)
                  : functionDescriptions(mapping.after_ids)
                ).map((text, index) => (
                  <p key={index}>{text}</p>
                ))}
                {!mapping.after_ids.length && (
                  <span className="missing-value">
                    No source counterpart identified
                  </span>
                )}
                {kind === "functions" && (
                  <small>
                    {[
                      ...new Set(
                        mapping.after_ids
                          .map(
                            (id) =>
                              result.functions.find((f) => f.id === id)
                                ?.unit_id,
                          )
                          .filter((id): id is string => !!id),
                      ),
                    ]
                      .map((id) => unitNames([id])[0])
                      .join("; ")}
                  </small>
                )}
              </div>
              <div className="mapping-assessment">
                <Badge value={getStatus(mapping)} />
                <div className="confidence">
                  <span>Confidence</span>
                  <strong>{percent(mapping.confidence)}</strong>
                </div>
                <details className="mapping-details">
                  <summary>
                    View reasoning & sources <ChevronDown size={14} />
                  </summary>
                  <p>{mapping.explanation}</p>
                  <EvidenceList
                    evidence={mapping.evidence}
                    documents={documents}
                  />
                </details>
              </div>
            </div>
          ))
        ) : (
          <div className="empty-state">
            <Search size={25} />
            <h3>No matching comparisons</h3>
            <p>
              {mappings.length
                ? "Try a different search or status filter."
                : "No validated mappings were extracted. Review source documents and the reported limits."}
            </p>
          </div>
        )}
      </div>
      <Warnings warnings={result.warnings} documents={documents} />
    </>
  );
}

function EvidenceList({
  evidence,
  documents,
}: {
  evidence: Evidence[];
  documents: SourceDocument[];
}) {
  const resolved = evidence.map((reference, index) => {
    const doc = documents.find((document) =>
      document.chunks.some((chunk) => chunk.id === reference.chunk_id),
    );
    const chunk = doc?.chunks.find((item) => item.id === reference.chunk_id);
    if (!doc || !chunk || !chunk.text.includes(reference.quote))
      return (
        <div className="notice caution" key={index}>
          <CircleAlert size={15} />
          Source reference could not be verified. Treat this assessment as
          unsupported.
        </div>
      );
    const location = [
      chunk.page && `Page ${chunk.page}`,
      chunk.section && `Section ${chunk.section}`,
      chunk.paragraph && `Paragraph ${chunk.paragraph}`,
      chunk.sheet && `Sheet ${chunk.sheet}`,
      chunk.row && `Row ${chunk.row}`,
    ]
      .filter(Boolean)
      .join(" · ");
    return (
      <div
        className={`evidence-card ${doc.side}`}
        key={`${reference.chunk_id}-${index}`}
      >
        <div className="evidence-meta">
          <span className={`side-label ${doc.side}`}>
            {doc.side === "before" ? "Before" : "After"}
          </span>
          <span>
            <FileText size={13} />
            {doc.filename}
          </span>
        </div>
        <div className="evidence-location">
          {location || "Document fragment"}
        </div>
        <blockquote>{reference.quote}</blockquote>
        <details className="source-context">
          <summary>Read source context</summary>
          <p>{chunk.text}</p>
        </details>
      </div>
    );
  });
  const sides = new Set(
    evidence.flatMap((reference) =>
      documents
        .filter((doc) =>
          doc.chunks.some((chunk) => chunk.id === reference.chunk_id),
        )
        .map((doc) => doc.side),
    ),
  );
  return (
    <div className="evidence-list">
      {resolved.length ? (
        resolved
      ) : (
        <div className="notice caution">
          <CircleAlert size={15} />
          No validated source evidence is available. Human review is required.
        </div>
      )}
      {(["before", "after"] as Side[])
        .filter((side) => !sides.has(side))
        .map((side) => (
          <p key={side} className="missing-evidence">
            No {side} source fragment cited for this assessment.
          </p>
        ))}
    </div>
  );
}

function Findings({
  result,
  documents,
}: {
  result: AnalysisResult;
  documents: SourceDocument[];
}) {
  const [category, setCategory] = useState<Finding["category"] | "all">("all");
  const [search, setSearch] = useState("");
  const visible = result.findings.filter(
    (f) =>
      (category === "all" || f.category === category) &&
      `${f.title} ${f.explanation}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <>
      <div className="section-intro">
        <h2>Findings for human review</h2>
        <p>
          Inspect the explanation and supporting fragments before accepting any
          recommendation.
        </p>
      </div>
      <div className="finding-category-filters">
        <button
          className={category === "all" ? "selected" : ""}
          onClick={() => setCategory("all")}
        >
          All findings <span>{result.findings.length}</span>
        </button>
        {categoryOrder.map((value) => (
          <button
            className={category === value ? "selected" : ""}
            key={value}
            onClick={() => setCategory(value)}
          >
            {categoryLabels[value]}
            <span>
              {result.findings.filter((f) => f.category === value).length}
            </span>
          </button>
        ))}
      </div>
      <div className="filter-bar">
        <label className="search-input">
          <Search size={17} />
          <span className="sr-only">Search findings</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search findings…"
          />
        </label>
        <span className="result-count">{visible.length} finding(s)</span>
      </div>
      {visible.length ? (
        <div className="findings-list">
          {visible.map((finding) => (
            <article
              className={`panel finding-card severity-${finding.severity}`}
              key={finding.id}
            >
              <div className="finding-header">
                <div className="finding-type">
                  <CircleAlert size={16} />
                  {categoryLabels[finding.category]}
                </div>
                <div>
                  <Badge value={finding.severity} />
                  <span className="confidence-pill">
                    {percent(finding.confidence)} confidence
                  </span>
                </div>
              </div>
              <h3>{finding.title}</h3>
              <p className="finding-explanation">{finding.explanation}</p>
              <div className="finding-recommendation">
                <ShieldCheck size={18} />
                <div>
                  <strong>Recommended review</strong>
                  <p>{finding.recommendation}</p>
                </div>
              </div>
              <details className="finding-evidence" open={visible.length <= 2}>
                <summary>
                  <span>
                    <FileSearch size={17} />
                    Supporting evidence{" "}
                    <span className="count-pill">
                      {finding.evidence.length}
                    </span>
                  </span>
                  <span>
                    View sources <ChevronDown size={16} />
                  </span>
                </summary>
                <EvidenceList
                  evidence={finding.evidence}
                  documents={documents}
                />
              </details>
              <div className="human-review-label">
                <CircleHelp size={13} />
                Recommendation only · Requires human validation
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="panel empty-state">
          <ShieldCheck size={28} />
          <h3>
            {search
              ? "No findings match this search"
              : "No evidence-backed findings in this category"}
          </h3>
          <p>
            {search
              ? "Try a different phrase or category."
              : "An empty result does not prove that no risk exists. Check the document coverage and review limitations."}
          </p>
        </div>
      )}
      <Warnings warnings={result.warnings} documents={documents} />
    </>
  );
}

function Report({
  analysis,
  result,
}: {
  analysis: Analysis;
  result: AnalysisResult;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.report);
      setCopied(true);
      setError("");
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError(
        "Clipboard access is unavailable. Download the report or select and copy its text.",
      );
    }
  };
  return (
    <>
      <div className="section-intro report-title">
        <div>
          <h2>Final analytical report</h2>
          <p>
            A reviewable account of changes, source evidence, and recommended
            next steps.
          </p>
        </div>
        <div className="button-group">
          <button className="button secondary" onClick={() => void copy()}>
            {copied ? <Check size={16} /> : <Clipboard size={16} />}
            {copied ? "Copied" : "Copy report"}
          </button>
          <a
            className="button primary"
            href={`/api/analyses/${encodeURIComponent(analysis.id)}/report`}
            download
          >
            <ArrowDownToLine size={16} />
            Download .md
          </a>
        </div>
      </div>
      {error && <ErrorMessage message={error} />}
      <article className="report-paper">
        <div className="report-brand">
          <Network size={20} />
          <strong>AlemScope</strong>
          <span>Analytical memorandum</span>
        </div>
        <div className="report-content">
          <Markdown skipHtml disallowedElements={["img"]} components={{
            h1: ({ children }) => <h2>{children}</h2>,
            h2: ({ children }) => <h3>{children}</h3>,
            h3: ({ children }) => <h4>{children}</h4>,
            a: ({ children }) => <span>{children}</span>,
          }}>{result.report}</Markdown>
        </div>
        <div className="report-disclaimer">
          <ShieldCheck size={18} />
          Recommendations require human validation against the cited documents.
        </div>
      </article>
    </>
  );
}
