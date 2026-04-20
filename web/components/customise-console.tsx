"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  listenToCustomiseLog,
  listenToCustomiseRunUpdated,
  tauriClient,
  isTauriRuntime,
} from "../lib/tauri";
import type { CustomiseLogEntry, CustomiseState, CustomiseStatus } from "../lib/types";
import { Badge, Field, Panel, PanelHeader } from "./shared";

const STATE_LABEL: Record<CustomiseState, string> = {
  cloning: "Cloning repo",
  generating: "Generating with Codex",
  ready_for_review: "Ready for review",
  applying: "Applying to live",
  applied: "Applied",
  failed: "Failed",
  cancelled: "Cancelled",
};

const TERMINAL_STATES: CustomiseState[] = ["applied", "failed", "cancelled"];

export function CustomiseConsole() {
  const [status, setStatus] = useState<CustomiseStatus | null>(null);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await tauriClient.getCustomiseStatus();
      setStatus(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
    let unlistenStatus: (() => void) | null = null;
    let unlistenLog: (() => void) | null = null;
    void listenToCustomiseRunUpdated((payload) => {
      if ("cleared" in payload) {
        setStatus(null);
      } else {
        setStatus(payload);
      }
    }).then((fn) => {
      unlistenStatus = fn;
    });
    void listenToCustomiseLog((entry: CustomiseLogEntry) => {
      setStatus((prev) => {
        if (!prev) return prev;
        if (prev.log[prev.log.length - 1]?.ts === entry.ts && prev.log[prev.log.length - 1]?.message === entry.message) {
          return prev;
        }
        return { ...prev, log: [...prev.log, entry] };
      });
    }).then((fn) => {
      unlistenLog = fn;
    });
    return () => {
      unlistenStatus?.();
      unlistenLog?.();
    };
  }, [refresh]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [status?.log.length]);

  const handleStart = useCallback(async () => {
    if (!prompt.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const next = await tauriClient.startCustomiseRun(prompt.trim());
      setStatus(next);
      setPrompt("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [prompt]);

  const handleApprove = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await tauriClient.approveCustomiseRun();
      setStatus(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, []);

  const handleDiscard = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await tauriClient.discardCustomiseRun();
      setStatus(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, []);

  const handleOpenExternal = useCallback(async (url: string, label: string) => {
    setError(null);
    try {
      await tauriClient.openExternal(url);
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      setError(`Failed to open ${label}: ${detail}`);
    }
  }, []);

  const isActive = status && !TERMINAL_STATES.includes(status.state);
  const canApprove =
    status?.state === "ready_for_review" && status.lockedViolations.length === 0;
  const hasViolations = (status?.lockedViolations ?? []).length > 0;

  const tauri = useMemo(() => isTauriRuntime(), []);

  return (
    <div className="space-y-6">
      <Panel>
        <PanelHeader
          eyebrow="customise"
          title="Describe a change, review a preview, approve into live."
          detail="Codex clones your runtime into an isolated preview, makes the requested change, and spins up a parallel sidecar + web so you can verify before applying."
        />
        <div className="space-y-4 p-5">
          {!tauri ? (
            <Badge tone="danger">Customise only works inside the Tauri desktop app.</Badge>
          ) : null}
          {error ? <Badge tone="danger">{error}</Badge> : null}
          <Field label="What would you like to change?" hint="Describe a concrete change. Locked areas (runtime shell, contracts, secrets) are off-limits.">
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              rows={4}
              disabled={!tauri || busy || !!isActive}
              className="min-h-[120px] w-full"
              placeholder="e.g. Add a dark-mode toggle to the user console header."
            />
          </Field>
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="btn btn-primary"
              disabled={!tauri || busy || !!isActive || !prompt.trim()}
              onClick={handleStart}
            >
              Start customise run
            </button>
            {status ? (
              <button
                type="button"
                className="btn"
                disabled={busy || status.state === "applying"}
                onClick={handleDiscard}
              >
                Discard
              </button>
            ) : null}
          </div>
        </div>
      </Panel>

      {status ? (
        <Panel>
          <PanelHeader
            eyebrow={`run ${status.runId}`}
            title={STATE_LABEL[status.state]}
            detail={status.prompt}
            action={
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={status.state === "failed" ? "danger" : status.state === "applied" ? "success" : "accent"}>
                  {STATE_LABEL[status.state]}
                </Badge>
                {status.previewWebUrl ? (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => void handleOpenExternal(status.previewWebUrl!, "preview web")}
                  >
                    Open preview web →
                  </button>
                ) : null}
                {status.previewSidecarUrl ? (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() =>
                      void handleOpenExternal(`${status.previewSidecarUrl}/health`, "preview sidecar")
                    }
                  >
                    Preview sidecar →
                  </button>
                ) : null}
              </div>
            }
          />
          <div className="grid gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
            <div className="space-y-4">
              <section>
                <h3 className="monoline mb-2">Changed files</h3>
                {status.changedPaths.length === 0 ? (
                  <p className="text-sm text-[color:var(--muted)]">No changes yet.</p>
                ) : (
                  <ul className="space-y-1 text-sm font-mono">
                    {status.changedPaths.map((path) => {
                      const locked = status.lockedViolations.includes(path);
                      return (
                        <li
                          key={path}
                          className={locked ? "text-[color:var(--danger)]" : "text-[color:var(--ink)]"}
                        >
                          {locked ? "✗ " : "• "}
                          {path}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
              {hasViolations ? (
                <Badge tone="danger">
                  Locked paths were modified. Apply is disabled until the run is regenerated.
                </Badge>
              ) : null}
              {status.error ? <Badge tone="danger">{status.error}</Badge> : null}
              {canApprove ? (
                <button type="button" className="btn btn-primary" disabled={busy} onClick={handleApprove}>
                  Approve & apply to live
                </button>
              ) : null}
            </div>
            <div>
              <h3 className="monoline mb-2">Activity log</h3>
              <div className="max-h-[28rem] overflow-auto rounded border border-[color:var(--line-soft)] bg-[color:var(--surface-muted)] p-3 font-mono text-xs leading-5">
                {status.log.map((entry, index) => (
                  <div key={index} className={entryTone(entry.level)}>
                    <span className="text-[color:var(--subtle)]">{formatTs(entry.ts)} </span>
                    <span>[{entry.level}]</span> {entry.message}
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            </div>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

function entryTone(level: string): string {
  if (level === "error") return "text-[color:var(--danger)]";
  if (level === "warn") return "text-[color:var(--accent)]";
  if (level === "debug") return "text-[color:var(--subtle)]";
  return "text-[color:var(--ink)]";
}

function formatTs(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleTimeString();
  } catch {
    return "";
  }
}
