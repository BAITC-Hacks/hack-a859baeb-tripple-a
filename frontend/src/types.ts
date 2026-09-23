export type Side = "before" | "after";
export type Mode = "local" | "openai";
export type Chunk = {
  id: string;
  document_id: string;
  text: string;
  page?: number | null;
  section?: string | null;
  paragraph?: number | null;
  sheet?: string | null;
  row?: number | null;
};
export type SourceDocument = {
  id: string;
  filename: string;
  document_type: "pdf" | "docx" | "xlsx";
  side: Side;
  chunks: Chunk[];
  warnings: string[];
};
export type Evidence = { chunk_id: string; quote: string };
export type Unit = {
  id: string;
  name: string;
  side: Side;
  evidence: Evidence[];
};
export type FunctionItem = {
  id: string;
  unit_id: string;
  description: string;
  side: Side;
  evidence: Evidence[];
};
export type UnitMapping = {
  id: string;
  before_ids: string[];
  after_ids: string[];
  status:
    | "unchanged"
    | "renamed"
    | "reorganized"
    | "removed"
    | "created"
    | "uncertain";
  confidence: number;
  explanation: string;
  evidence: Evidence[];
};
export type FunctionMapping = {
  id: string;
  before_ids: string[];
  after_ids: string[];
  match_type:
    | "unchanged"
    | "equivalent"
    | "modified"
    | "transferred"
    | "potential_loss"
    | "new"
    | "uncertain";
  confidence: number;
  explanation: string;
  evidence: Evidence[];
};
export type Finding = {
  id: string;
  category: "loss" | "duplication" | "overlap" | "conflict" | "uncertain";
  title: string;
  explanation: string;
  severity: "high" | "medium" | "low";
  confidence: number;
  evidence: Evidence[];
  recommendation: string;
  requires_review: boolean;
};
export type AnalysisResult = {
  units: Unit[];
  functions: FunctionItem[];
  unit_mappings: UnitMapping[];
  function_mappings: FunctionMapping[];
  findings: Finding[];
  warnings: string[];
  summary: Record<string, number>;
  report: string;
};
export type Analysis = {
  id: string;
  title: string;
  created_at: string;
  status: "queued" | "running" | "completed" | "failed";
  mode: Mode;
  stage: number;
  stage_label: string;
  error: string | null;
  documents?: SourceDocument[];
  result?: AnalysisResult | null;
};
export type Health = {
  status: string;
  openai_configured: boolean;
  model: string;
};
