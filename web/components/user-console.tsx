"use client";

import { useDeferredValue, useEffect, useMemo, useState, useTransition } from "react";

import { sidecar } from "../lib/sidecar";
import type { WorkflowDefinition, WorkflowProgressEvent, WorkflowRunRecord, WorkflowRunTerminalEvent } from "../lib/types";
import { AppShell } from "./app-shell";
import { Badge, Field, Panel, SectionTitle } from "./shared";

export function UserConsole() {
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [runs, setRuns] = useState<WorkflowRunRecord[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [textInputs, setTextInputs] = useState<Record<string, string>>({});
  const [fileInputs, setFileInputs] = useState<Record<string, File | null>>({});
  const [progress, setProgress] = useState<WorkflowProgressEvent[]>([]);
  const [result, setResult] = useState<WorkflowRunRecord | null>(null);
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState("");
  const [debug, setDebug] = useState(false);
  const [isPending, startTransition] = useTransition();
  const deferredProgress = useDeferredValue(progress);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const [workflowItems, runItems] = await Promise.all([sidecar.getWorkflows(), sidecar.getRuns()]);
        if (!active) {
          return;
        }
        setWorkflows(workflowItems);
        setRuns(runItems);
        if (workflowItems[0]) {
          setSelectedWorkflowId((current) => current || workflowItems[0].id);
        }
      } catch (event) {
        if (!active) {
          return;
        }
        setError(event instanceof Error ? event.message : "Failed to load workflows.");
        setStatus("Waiting");
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const selectedWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === selectedWorkflowId) ?? null,
    [selectedWorkflowId, workflows],
  );

  const sidebar = (
    <div className="space-y-3">
      {workflows.map((workflow) => (
        <button
          key={workflow.id}
          onClick={() => setSelectedWorkflowId(workflow.id)}
          className={`w-full rounded-[22px] border px-4 py-4 text-left transition ${
            workflow.id === selectedWorkflowId
              ? "border-[color:var(--accent)] bg-[color:var(--accent-soft)]"
              : "border-[color:var(--line)] bg-white/60 hover:bg-[color:var(--surface-strong)]"
          }`}
        >
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold">{workflow.name}</div>
            <div className="monoline text-[10px] text-[color:var(--subtle)]">{workflow.id}</div>
          </div>
          <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">{workflow.description || "No description yet."}</p>
        </button>
      ))}
    </div>
  );

  return (
    <AppShell
      title="Run Workflows"
      subtitle="Submit text and files into the Python sandbox sidecar and watch the execution timeline arrive over SSE."
      sidebar={sidebar}
    >
      <Panel>
        <SectionTitle
          eyebrow="Current Workflow"
          title={selectedWorkflow?.name ?? "No active workflow"}
          detail={selectedWorkflow?.description ?? "Create or activate a workflow in Builder mode."}
          action={<Badge tone={status === "Complete" ? "success" : status === "Failed" ? "danger" : "accent"}>{status}</Badge>}
        />
        {selectedWorkflow ? (
          <div className="mt-6 grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-4">
              {selectedWorkflow.input_fields.map((field) => (
                <Field key={field.id} label={`${field.label}${field.required ? " *" : ""}`} hint={field.help_text}>
                  {field.type === "file" ? (
                    <input
                      type="file"
                      className="w-full rounded-[18px] border border-[color:var(--line)] bg-white px-4 py-3"
                      onChange={(event) =>
                        setFileInputs((current) => ({ ...current, [field.id]: event.currentTarget.files?.[0] ?? null }))
                      }
                    />
                  ) : field.type === "long_text" ? (
                    <textarea
                      className="min-h-[140px] w-full rounded-[18px] border border-[color:var(--line)] bg-white px-4 py-3"
                      value={textInputs[field.id] ?? ""}
                      onChange={(event) => setTextInputs((current) => ({ ...current, [field.id]: event.target.value }))}
                    />
                  ) : (
                    <input
                      className="w-full rounded-[18px] border border-[color:var(--line)] bg-white px-4 py-3"
                      value={textInputs[field.id] ?? ""}
                      onChange={(event) => setTextInputs((current) => ({ ...current, [field.id]: event.target.value }))}
                    />
                  )}
                </Field>
              ))}
              <div className="flex flex-wrap items-center gap-3">
                <button
                  disabled={isPending}
                  onClick={() =>
                    startTransition(async () => {
                      if (!selectedWorkflow) {
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
                        const source = await sidecar.streamRun(runId, {
                          onProgress: (event) => {
                            setStatus(event.title);
                            setProgress((current) => [...current, event].slice(-50));
                          },
                          onTerminal: async (event: WorkflowRunTerminalEvent) => {
                            if (event.status === "complete" && event.record) {
                              setStatus("Complete");
                              setResult(event.record);
                            } else {
                              setStatus("Failed");
                              setError(event.error ?? "Run failed.");
                            }
                            setRuns(await sidecar.getRuns());
                          },
                          onError: () => {
                            setStatus("Failed");
                            setError("Lost the run event stream.");
                          },
                        });
                        void source;
                      } catch (event) {
                        setStatus("Failed");
                        setError(event instanceof Error ? event.message : "Run failed.");
                      }
                    })
                  }
                  className="rounded-full bg-[color:var(--ink)] px-5 py-3 text-sm font-semibold text-white disabled:opacity-60"
                >
                  {isPending ? "Submitting..." : "Run Workflow"}
                </button>
                <button
                  onClick={() => {
                    setTextInputs({});
                    setFileInputs({});
                    setProgress([]);
                    setResult(null);
                    setError("");
                    setStatus("Ready");
                  }}
                  className="rounded-full border border-[color:var(--line)] px-5 py-3 text-sm font-semibold"
                >
                  Clear Inputs
                </button>
                <label className="flex items-center gap-2 text-sm text-[color:var(--muted)]">
                  <input type="checkbox" checked={debug} onChange={(event) => setDebug(event.target.checked)} />
                  Debug trace
                </label>
              </div>
              {error ? <div className="rounded-[20px] bg-[color:var(--danger-soft)] px-4 py-3 text-sm text-[color:var(--danger)]">{error}</div> : null}
            </div>
            <div className="rounded-[26px] border border-[color:var(--line)] bg-[color:var(--surface-strong)] p-5">
              <div className="monoline text-[11px] text-[color:var(--subtle)]">Runtime Feed</div>
              <div className="mt-4 space-y-3">
                {deferredProgress.length ? (
                  deferredProgress
                    .slice()
                    .reverse()
                    .map((event) => (
                      <div key={`${event.timestamp}-${event.title}`} className="rounded-[20px] bg-white px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-semibold">{event.title}</div>
                          <Badge tone={event.kind === "error" ? "danger" : "neutral"}>{event.stage}</Badge>
                        </div>
                        {event.detail ? <div className="mt-2 text-sm leading-6 text-[color:var(--muted)]">{event.detail}</div> : null}
                      </div>
                    ))
                ) : (
                  <div className="rounded-[20px] bg-white px-4 py-8 text-sm text-[color:var(--muted)]">
                    Run progress appears here as the sidecar streams SSE events.
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </Panel>
      <Panel>
        <SectionTitle eyebrow="Latest Result" title={result?.workflow_name ?? "No completed run yet"} />
        {result?.result ? (
          <div className="mt-5 grid gap-4 lg:grid-cols-[0.7fr_1fr]">
            <div className="rounded-[24px] bg-[color:var(--surface-strong)] p-5">
              <div className="monoline text-[11px] text-[color:var(--subtle)]">Summary</div>
              <p className="mt-4 text-sm leading-7 text-[color:var(--muted)]">{result.result.summary}</p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {result.workflow_snapshot.output_fields.map((field) => (
                <div key={field.id} className="rounded-[24px] border border-[color:var(--line)] bg-white p-5">
                  <div className="monoline text-[11px] text-[color:var(--subtle)]">{field.label}</div>
                  <pre className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[color:var(--ink)]">
                    {field.type === "json"
                      ? JSON.stringify(result.result?.fields[field.id] ?? null, null, 2)
                      : String(result.result?.fields[field.id] ?? "")}
                  </pre>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="mt-5 rounded-[24px] bg-[color:var(--surface-strong)] px-5 py-8 text-sm text-[color:var(--muted)]">
            Structured outputs and artifact download links will appear here after a successful run.
          </div>
        )}
        {result?.result?.artifacts?.length ? (
          <div className="mt-5 flex flex-wrap gap-3">
            {result.result.artifacts.map((artifact) => (
              <button
                key={artifact.artifact_id}
                onClick={async () => {
                  const href = await sidecar.artifactUrl(result.id, artifact.artifact_id);
                  window.open(href, "_blank", "noopener,noreferrer");
                }}
                className="rounded-full bg-[color:var(--accent-soft)] px-4 py-2 text-sm font-semibold text-[color:var(--accent)]"
              >
                Download {artifact.label}
              </button>
            ))}
          </div>
        ) : null}
      </Panel>
      <Panel>
        <SectionTitle eyebrow="Run History" title="Recent persisted runs" />
        <div className="mt-5 grid gap-3">
          {runs.map((run) => (
            <div key={run.id} className="rounded-[24px] border border-[color:var(--line)] bg-white px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold">{run.workflow_name}</div>
                  <div className="mt-1 text-xs text-[color:var(--muted)]">{run.id}</div>
                </div>
                <Badge tone={run.status === "complete" ? "success" : "danger"}>{run.status}</Badge>
              </div>
              <p className="mt-3 text-sm leading-6 text-[color:var(--muted)]">
                {run.result?.summary || run.error || "No summary captured."}
              </p>
            </div>
          ))}
        </div>
      </Panel>
    </AppShell>
  );
}
