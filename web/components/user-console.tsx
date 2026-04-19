"use client";

import clsx from "clsx";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import { sidecar } from "../lib/sidecar";
import { isTauriRuntime, tauriClient } from "../lib/tauri";
import type {
  InputFieldDefinition,
  WorkflowDefinition,
  WorkflowProgressEvent,
  WorkflowProgressStage,
  WorkflowRunRecord,
  WorkflowRunTerminalEvent,
} from "../lib/types";
import { AppShell, Banner } from "./app-shell";
import {
  Badge,
  Field,
  IconBug,
  IconCheck,
  IconDownload,
  IconPlay,
  IconUpload,
  IconX,
  Panel,
  PanelHeader,
} from "./shared";

const STEPS: { key: WorkflowProgressStage | "preparing"; label: string }[] = [
  { key: "preparing", label: "Preparing" },
  { key: "starting_sandbox", label: "Sandbox" },
  { key: "running_workflow", label: "Running" },
  { key: "validating_outputs", label: "Validating" },
  { key: "saving_outputs", label: "Saving" },
];

function stageIndex(stage: WorkflowProgressStage | null): number {
  switch (stage) {
    case "preparing":
      return 0;
    case "starting_sandbox":
      return 1;
    case "running_workflow":
      return 2;
    case "validating_outputs":
      return 3;
    case "saving_outputs":
      return 4;
    case "complete":
      return 5;
    case "failed":
      return -1;
    default:
      return -1;
  }
}

export function UserConsole() {
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [runs, setRuns] = useState<WorkflowRunRecord[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [textInputs, setTextInputs] = useState<Record<string, string>>({});
  const [fileInputs, setFileInputs] = useState<Record<string, File | null>>({});
  const [progress, setProgress] = useState<WorkflowProgressEvent[]>([]);
  const [result, setResult] = useState<WorkflowRunRecord | null>(null);
  const [status, setStatus] = useState<"Ready" | "Starting" | "Running" | "Complete" | "Failed" | "Waiting">("Ready");
  const [reconnecting, setReconnecting] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [debug, setDebug] = useState(false);
  const [isPending, startTransition] = useTransition();
  const recentProgress = progress.slice(-5).slice().reverse();

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [workflowItems, runItems] = await Promise.all([sidecar.getWorkflows(), sidecar.getRuns()]);
        if (!active) {
          return;
        }
        setWorkflows(workflowItems);
        setRuns(runItems);
        setLoadError("");
        if (workflowItems[0]) {
          setSelectedWorkflowId((current) => current || workflowItems[0].id);
        }
      } catch (event) {
        if (!active) {
          return;
        }
        setLoadError(event instanceof Error ? event.message : "Failed to load workflows.");
        setStatus("Waiting");
      }
    };
    void load();
    const onReady = () => {
      void load();
    };
    window.addEventListener("sandflow:runtime-ready", onReady);
    return () => {
      active = false;
      window.removeEventListener("sandflow:runtime-ready", onReady);
    };
  }, []);

  const selectedWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === selectedWorkflowId) ?? null,
    [selectedWorkflowId, workflows],
  );

  const latestStage = progress.length ? progress[progress.length - 1].stage : null;
  const currentStepIdx = status === "Complete" ? STEPS.length : stageIndex(latestStage);

  const sidebar = (
    <>
      <div className="panel">
        <div className="border-b border-[color:var(--line)] px-4 py-3">
          <div className="monoline">Workflows</div>
        </div>
        <div className="divide-y divide-[color:var(--line-soft)]">
          {workflows.length ? (
            workflows.map((workflow) => (
              <button
                key={workflow.id}
                onClick={() => setSelectedWorkflowId(workflow.id)}
                className={clsx(
                  "block w-full px-4 py-3 text-left transition",
                  workflow.id === selectedWorkflowId ? "bg-[color:var(--accent-soft)]" : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="truncate text-sm font-semibold">{workflow.name}</div>
                  <span className="mono truncate text-[10px] text-[color:var(--subtle)]">{workflow.id}</span>
                </div>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-[color:var(--muted)]">
                  {workflow.description || "No description yet."}
                </p>
              </button>
            ))
          ) : (
            <div className="px-4 py-6 text-sm text-[color:var(--muted)]">No workflows available.</div>
          )}
        </div>
      </div>
    </>
  );

  const banner = loadError ? <Banner tone="danger">{loadError}</Banner> : null;

  const runWorkflow = () =>
    startTransition(async () => {
      if (!selectedWorkflow) {
        return;
      }
      const missing = selectedWorkflow.input_fields.find((field) =>
        field.required && (field.type === "file" ? !fileInputs[field.id] : !(textInputs[field.id] ?? "").trim()),
      );
      if (missing) {
        setError(`Missing required field: ${missing.label}`);
        return;
      }
      try {
        setError("");
        setResult(null);
        setProgress([]);
        setStatus("Starting");
        const formData = new FormData();
        formData.set("debug", String(debug));
        for (const field of selectedWorkflow.input_fields) {
          if (field.type === "file") {
            const file = fileInputs[field.id];
            if (file) {
              formData.set(`file.${field.id}`, file);
            }
            continue;
          }
          const value = textInputs[field.id]?.trim();
          if (value) {
            formData.set(`text.${field.id}`, value);
          }
        }
        const runId = await sidecar.submitRun(selectedWorkflow.id, formData);
        await sidecar.streamRun(runId, {
          onProgress: (event) => {
            setReconnecting(false);
            setStatus("Running");
            setProgress((current) => [...current, event].slice(-50));
          },
          onTerminal: async (event: WorkflowRunTerminalEvent) => {
            setReconnecting(false);
            if (event.status === "complete" && event.record) {
              setStatus("Complete");
              setResult(event.record);
            } else {
              setStatus("Failed");
              setError(event.error ?? "Run failed.");
            }
            setRuns(await sidecar.getRuns());
          },
          onReconnecting: () => {
            setReconnecting(true);
          },
        });
      } catch (event) {
        setStatus("Failed");
        setError(event instanceof Error ? event.message : "Run failed.");
      }
    });

  const clearInputs = () => {
    setTextInputs({});
    setFileInputs({});
    setProgress([]);
    setResult(null);
    setError("");
    setStatus("Ready");
    setDebug(false);
  };

  return (
    <AppShell sidebar={sidebar} banner={banner}>
      <Panel>
        <PanelHeader
          eyebrow={selectedWorkflow ? selectedWorkflow.id : undefined}
          title={selectedWorkflow?.name ?? "No active workflow"}
          detail={selectedWorkflow?.description ?? "Create or activate a workflow in Builder mode."}
          action={
            <div className="flex items-center gap-2">
              {reconnecting ? (
                <Badge tone="accent">Reconnecting…</Badge>
              ) : null}
              <Badge
                tone={status === "Complete" ? "success" : status === "Failed" ? "danger" : status === "Running" || status === "Starting" ? "accent" : "ghost"}
              >
                {status}
              </Badge>
            </div>
          }
        />
        {selectedWorkflow ? (
          <div className="grid gap-6 px-5 py-5 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-5">
              {selectedWorkflow.input_fields.map((field) => (
                <InputControl
                  key={field.id}
                  field={field}
                  textValue={textInputs[field.id] ?? ""}
                  fileValue={fileInputs[field.id] ?? null}
                  onText={(value) => setTextInputs((current) => ({ ...current, [field.id]: value }))}
                  onFile={(file) => setFileInputs((current) => ({ ...current, [field.id]: file }))}
                />
              ))}
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" className="btn btn-primary" disabled={isPending} onClick={runWorkflow}>
                  <IconPlay size={12} />
                  {isPending ? "Submitting…" : "Run Workflow"}
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setDebug((value) => !value)}
                  aria-pressed={debug}
                >
                  <IconBug size={13} />
                  Debug {debug ? "On" : "Off"}
                </button>
                <button type="button" className="btn" onClick={clearInputs}>
                  <IconX size={13} />
                  Clear
                </button>
              </div>
              {error ? (
                <div role="alert" className="border border-[color:var(--danger)] bg-[color:var(--danger-soft)] px-3 py-2 text-sm text-[color:var(--danger)]">
                  {error}
                </div>
              ) : null}
            </div>
            <div className="panel-muted min-h-[240px] p-4">
              <div className="flex items-center justify-between">
                <div className="monoline">Runtime Feed</div>
                {recentProgress.length ? (
                  <span className="mono text-[10px] text-[color:var(--subtle)]">
                    {recentProgress.length} recent
                  </span>
                ) : null}
              </div>
              <div className="mt-3 space-y-2">
                {recentProgress.length ? (
                  recentProgress.map((event, index) => (
                      <div
                        key={`${event.timestamp}-${event.title}-${event.detail}-${index}`}
                        className="border border-[color:var(--line-soft)] bg-[color:var(--surface)] px-3 py-2"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="truncate text-sm font-semibold">{event.title}</div>
                          <Badge tone={event.kind === "error" ? "danger" : "ghost"}>{event.stage}</Badge>
                        </div>
                        {event.detail ? <div className="mt-1 text-xs leading-5 text-[color:var(--muted)]">{event.detail}</div> : null}
                      </div>
                    ))
                ) : (
                  <div className="text-sm text-[color:var(--muted)]">
                    Run progress appears here as the sidecar streams SSE events.
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </Panel>

      <Panel>
        <PanelHeader
          title="Runtime"
          action={
            <span className="mono text-[11px] text-[color:var(--subtle)]">
              {status === "Complete" ? "Done" : status === "Failed" ? "Failed" : currentStepIdx >= 0 ? STEPS[Math.min(currentStepIdx, STEPS.length - 1)]?.label : "Idle"}
            </span>
          }
        />
        <div className="px-5 py-6">
          <Stepper current={currentStepIdx} failed={status === "Failed"} />
        </div>
      </Panel>

      <Panel>
        <PanelHeader eyebrow="Latest Result" title={result?.workflow_name ?? "No completed run yet"} />
        <div className="px-5 py-5">
          {result?.result ? (
            <div className="grid gap-4 lg:grid-cols-[0.7fr_1fr]">
              <div className="panel-muted p-4">
                <div className="monoline">Summary</div>
                <p className="mt-3 text-sm leading-6 text-[color:var(--ink)]">{result.result.summary}</p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {result.workflow_snapshot.output_fields.map((field) => (
                  <div key={field.id} className="border border-[color:var(--line-soft)] p-4">
                    <div className="monoline">{field.label}</div>
                    <pre className="mono mt-2 max-h-[220px] overflow-auto whitespace-pre-wrap text-[12px] leading-5 text-[color:var(--ink)]">
                      {field.type === "json"
                        ? JSON.stringify(result.result?.fields[field.id] ?? null, null, 2)
                        : String(result.result?.fields[field.id] ?? "")}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-sm text-[color:var(--muted)]">
              Structured outputs and artifact download links will appear here after a successful run.
            </div>
          )}
          {result?.result?.artifacts?.length ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {result.result.artifacts.map((artifact) => (
                <ArtifactLink
                  key={artifact.artifact_id}
                  runId={result.id}
                  artifactId={artifact.artifact_id}
                  label={artifact.label}
                  filename={artifact.filename}
                  storedPath={artifact.stored_path}
                />
              ))}
            </div>
          ) : null}
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Run History"
          action={<span className="mono text-[11px] text-[color:var(--subtle)]">{runs.length} run{runs.length === 1 ? "" : "s"}</span>}
        />
        {runs.length ? (
          <div className="divide-y divide-[color:var(--line-soft)]">
            {runs.map((run) => (
              <div key={run.id} className="px-5 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">{run.workflow_name}</div>
                    <div className="mono mt-0.5 truncate text-[11px] text-[color:var(--subtle)]">{run.id.slice(0, 8)} · {run.started_at}</div>
                  </div>
                  <Badge tone={run.status === "complete" ? "success" : "danger"}>{run.status}</Badge>
                </div>
                <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">
                  {run.result?.summary || run.error || "No summary captured."}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <div className="px-5 py-6 text-sm text-[color:var(--muted)]">
            No runs recorded yet. Fill the form above and press Run Workflow to see results here.
          </div>
        )}
      </Panel>
    </AppShell>
  );
}

function Stepper({ current, failed }: { current: number; failed: boolean }) {
  return (
    <ol className="flex items-center">
      {STEPS.map((step, index) => {
        const state: "done" | "active" | "pending" | "failed" =
          failed && index === Math.max(0, current)
            ? "failed"
            : index < current
              ? "done"
              : index === current
                ? "active"
                : "pending";
        return (
          <li key={step.key} className={clsx("flex flex-1 items-center", index === STEPS.length - 1 && "flex-none")}>
            <div className="flex flex-col items-center gap-2">
              <span
                className={clsx(
                  "mono flex h-8 w-8 items-center justify-center border text-[12px] font-semibold",
                  state === "done" && "border-[color:var(--ink)] bg-[color:var(--ink)] text-white",
                  state === "active" && "border-[color:var(--accent)] bg-[color:var(--accent)] text-white",
                  state === "failed" && "border-[color:var(--danger)] bg-[color:var(--danger)] text-white",
                  state === "pending" && "border-[color:var(--line-soft)] bg-white text-[color:var(--subtle)]",
                )}
                aria-current={state === "active" ? "step" : undefined}
              >
                {state === "done" ? <IconCheck size={14} /> : index + 1}
              </span>
              <span
                className={clsx(
                  "mono text-[11px]",
                  state === "pending" ? "text-[color:var(--subtle)]" : "text-[color:var(--ink)]",
                )}
              >
                {step.label}
              </span>
            </div>
            {index < STEPS.length - 1 ? (
              <div
                aria-hidden
                className={clsx(
                  "mx-2 h-px flex-1",
                  state === "done" ? "bg-[color:var(--ink)]" : "bg-[color:var(--line-soft)]",
                )}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function InputControl({
  field,
  textValue,
  fileValue,
  onText,
  onFile,
}: {
  field: InputFieldDefinition;
  textValue: string;
  fileValue: File | null;
  onText: (value: string) => void;
  onFile: (file: File | null) => void;
}) {
  return (
    <Field label={field.label} hint={field.help_text} required={field.required}>
      {field.type === "file" ? (
        <FileDrop value={fileValue} onChange={onFile} />
      ) : field.type === "long_text" ? (
        <textarea className="min-h-[120px] w-full" value={textValue} onChange={(event) => onText(event.target.value)} />
      ) : (
        <input className="w-full" value={textValue} onChange={(event) => onText(event.target.value)} />
      )}
    </Field>
  );
}

function FileDrop({ value, onChange }: { value: File | null; onChange: (file: File | null) => void }) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);
  return (
    <div
      className="dropzone relative"
      data-active={dragging}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        const file = event.dataTransfer.files?.[0];
        if (file) {
          onChange(file);
        }
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          inputRef.current?.click();
        }
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.doc,.docx,.txt,.md,.markdown,application/pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0"
        onChange={(event) => onChange(event.currentTarget.files?.[0] ?? null)}
      />
      <div className="flex flex-col items-center gap-1">
        <IconUpload size={18} />
        {value ? (
          <>
            <div className="text-sm font-semibold">{value.name}</div>
            <div className="mono text-[11px] text-[color:var(--subtle)]">
              {(value.size / 1024).toFixed(1)} KB · click to replace
            </div>
            <div className="mono text-[11px] text-[color:var(--subtle)]">Press Run Workflow after selecting the file.</div>
          </>
        ) : (
          <>
            <div className="text-sm font-semibold">Drop a file here, or click to browse</div>
            <div className="mono text-[11px] text-[color:var(--subtle)]">Accepts PDF, DOCX, TXT, or Markdown</div>
            <div className="mono text-[11px] text-[color:var(--subtle)]">Press Run Workflow after selecting the file.</div>
          </>
        )}
      </div>
    </div>
  );
}

function ArtifactLink({
  runId,
  artifactId,
  label,
  filename,
  storedPath,
}: {
  runId: string;
  artifactId: string;
  label: string;
  filename: string;
  storedPath: string;
}) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState("");
  const [savedPath, setSavedPath] = useState("");
  const desktopMode = isTauriRuntime();
  return (
    <button
      type="button"
      className={clsx("btn", error && "border-[color:var(--danger)] text-[color:var(--danger)]")}
      aria-label={`${desktopMode ? (savedPath ? "Reveal" : "Save") : "Download"} ${label}`}
      disabled={isPending}
      onClick={() =>
        startTransition(async () => {
          try {
            setError("");
            if (desktopMode) {
              if (savedPath) {
                await tauriClient.revealPathInFinder(savedPath);
                return;
              }
              const nextSavedPath = await tauriClient.saveArtifactToDownloads(
                storedPath,
                filename || `${artifactId}.bin`,
              );
              setSavedPath(nextSavedPath);
              return;
            }
            const blob = await sidecar.downloadArtifact(runId, artifactId);
            const objectUrl = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = objectUrl;
            anchor.download = filename || `${artifactId}.bin`;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
          } catch (event) {
            setError(event instanceof Error ? event.message : "Download failed.");
          }
        })
      }
    >
      <IconDownload size={13} />
      {isPending
        ? desktopMode
          ? savedPath
            ? "Opening…"
            : "Saving…"
          : "Downloading…"
        : desktopMode
          ? savedPath
            ? "Reveal In Finder"
            : "Save To Downloads"
          : label}
    </button>
  );
}
