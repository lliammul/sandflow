export type InputFieldType = "short_text" | "long_text" | "file";
export type OutputFieldType = "text" | "markdown" | "json" | "number" | "boolean";
export type ArtifactFormat = "csv" | "docx" | "xlsx" | "pptx" | "txt" | "md" | "json" | "html";
export type RunStatus = "running" | "complete" | "failed";
export type WorkflowProgressStage =
  | "preparing"
  | "starting_sandbox"
  | "running_workflow"
  | "validating_outputs"
  | "saving_outputs"
  | "complete"
  | "failed";
export type WorkflowProgressKind = "stage" | "tool_called" | "tool_output" | "message" | "agent" | "error";

export interface InputFieldDefinition {
  id: string;
  label: string;
  type: InputFieldType;
  required: boolean;
  help_text: string;
}

export interface OutputFieldDefinition {
  id: string;
  label: string;
  type: OutputFieldType;
  required: boolean;
  help_text: string;
}

export interface ArtifactOutputDefinition {
  id: string;
  label: string;
  format: ArtifactFormat;
  required: boolean;
  help_text: string;
}

export interface WorkflowDefinition {
  schema_version: 1;
  id: string;
  name: string;
  description: string;
  is_active: boolean;
  prompt: string;
  input_fields: InputFieldDefinition[];
  output_fields: OutputFieldDefinition[];
  artifact_outputs: ArtifactOutputDefinition[];
  created_at: string;
  updated_at: string;
}

export interface WorkflowRegistryEntry {
  id: string;
  name: string;
  description: string;
  is_active: boolean;
  has_error: boolean;
  error_message: string | null;
}

export interface WorkflowArtifactRef {
  artifact_id: string;
  label: string;
  format: ArtifactFormat;
  stored_path: string;
  filename: string;
  mime_type: string | null;
}

export interface WorkflowPersistedResult {
  summary: string;
  fields: Record<string, unknown>;
  artifacts: WorkflowArtifactRef[];
}

export interface WorkflowRunTimelineEntry {
  timestamp: string;
  stage: WorkflowProgressStage;
  title: string;
  detail: string;
}

export interface WorkflowDebugTraceEntry {
  timestamp: string;
  event_type: string;
  title: string;
  payload: string;
}

export interface WorkflowRunInputSummary {
  text_fields: Record<string, string>;
  files: Array<{
    input_id: string;
    original_name: string;
    stored_path: string;
  }>;
}

export interface WorkflowRunRecord {
  id: string;
  workflow_id: string;
  workflow_name: string;
  workflow_snapshot: WorkflowDefinition;
  status: RunStatus;
  started_at: string;
  completed_at: string | null;
  input_summary: WorkflowRunInputSummary;
  result: WorkflowPersistedResult | null;
  error: string | null;
  raw_result_json: string | null;
  progress_timeline: WorkflowRunTimelineEntry[];
  debug_enabled: boolean;
  debug_trace: WorkflowDebugTraceEntry[];
}

export interface WorkflowProgressEvent {
  timestamp: string;
  stage: WorkflowProgressStage;
  kind: WorkflowProgressKind;
  title: string;
  detail: string;
  persist: boolean;
}

export interface WorkflowRunTerminalEvent {
  status: "complete" | "failed";
  record: WorkflowRunRecord | null;
  error: string | null;
}

export interface SidecarEvent<TType extends "progress" | "terminal", TPayload> {
  type: TType;
  payload: TPayload;
}

export interface RuntimeStatus {
  bootstrapped: boolean;
  repoPath: string | null;
  sidecarPort: number | null;
  sidecarBaseUrl: string | null;
  needsSetup: boolean;
  dockerAvailable: boolean;
  config: {
    openAiApiKey: string;
    openAiBaseUrl: string;
    sandboxModel: string;
  };
}

export interface BootstrapPayload {
  openAiApiKey: string;
  openAiBaseUrl: string;
  sandboxModel: string;
}

export interface SidecarChangedEvent {
  swapId: number;
  oldPort: number | null;
  newPort: number;
  baseUrl: string;
}

export type CustomiseState =
  | "cloning"
  | "generating"
  | "ready_for_review"
  | "applying"
  | "applied"
  | "failed"
  | "cancelled";

export interface CustomiseLogEntry {
  ts: number;
  level: string;
  message: string;
}

export interface CustomiseStatus {
  runId: string;
  prompt: string;
  previewPath: string;
  previewSidecarUrl: string | null;
  previewWebUrl: string | null;
  state: CustomiseState;
  startedAt: number;
  log: CustomiseLogEntry[];
  changedPaths: string[];
  lockedViolations: string[];
  error: string | null;
}
