"use client";

import { useEffect, useMemo, useState, useTransition } from "react";

import { tauriClient } from "../lib/tauri";
import type { CustomiseHistoryEntry, CustomiseLogEvent, CustomisePreview } from "../lib/types";
import { AppShell } from "./app-shell";
import { Badge, Panel, SectionTitle } from "./shared";

export function CustomiseConsole() {
  const [prompt, setPrompt] = useState("");
  const [runId, setRunId] = useState("");
  const [preview, setPreview] = useState<CustomisePreview | null>(null);
  const [history, setHistory] = useState<CustomiseHistoryEntry[]>([]);
  const [logs, setLogs] = useState<CustomiseLogEvent[]>([]);
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    void tauriClient.getCustomiseHistory().then(setHistory).catch(() => undefined);
    let unlisten: (() => void) | undefined;
    void tauriClient.listenToCustomiseLogs((event) => {
      setLogs((current) => [...current, event].slice(-100));
    }).then((value) => {
      unlisten = value;
    }).catch(() => undefined);
    return () => {
      unlisten?.();
    };
  }, []);

  const sidebar = (
    <div className="space-y-3">
      <button
        onClick={() => tauriClient.openRepoInEditor().catch(() => undefined)}
        className="w-full rounded-[22px] bg-[color:var(--ink)] px-4 py-3 text-sm font-semibold text-white"
      >
        View Source In Editor
      </button>
      <button
        onClick={async () => {
          await tauriClient.resetCustomisations();
          setHistory(await tauriClient.getCustomiseHistory());
          setPreview(null);
        }}
        className="w-full rounded-[22px] border border-[color:var(--line)] px-4 py-3 text-sm font-semibold"
      >
        Reset To Defaults
      </button>
      <div className="rounded-[22px] border border-[color:var(--line)] bg-white/60 px-4 py-4">
        <div className="monoline text-[11px] text-[color:var(--subtle)]">Branch History</div>
        <div className="mt-3 space-y-3">
          {history.length ? (
            history.map((entry) => (
              <div key={entry.sha} className="rounded-[18px] bg-white px-3 py-3">
                <div className="text-sm font-semibold">{entry.subject}</div>
                <div className="mt-1 text-xs text-[color:var(--muted)]">{entry.sha.slice(0, 8)} · {entry.committedAt}</div>
                <button
                  onClick={async () => {
                    await tauriClient.revertCustomCommit(entry.sha);
                    setHistory(await tauriClient.getCustomiseHistory());
                  }}
                  className="mt-3 rounded-full border border-[color:var(--line)] px-3 py-2 text-xs font-semibold"
                >
                  Revert
                </button>
              </div>
            ))
          ) : (
            <div className="text-sm leading-6 text-[color:var(--muted)]">No custom commits yet.</div>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <AppShell
      title="Customise"
      subtitle="Run Codex against a temporary worktree, preview the diff, and only apply changes after validation."
      sidebar={sidebar}
    >
      <Panel>
        <SectionTitle eyebrow="Prompt" title="Describe the change you want" />
        <textarea
          className="mt-5 min-h-[180px] w-full rounded-[24px] border border-[color:var(--line)] bg-white px-5 py-4"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Change the header color to navy, add a greeting, and preserve the current layout density."
        />
        {error ? <div className="mt-4 rounded-[20px] bg-[color:var(--danger-soft)] px-4 py-3 text-sm text-[color:var(--danger)]">{error}</div> : null}
        <div className="mt-5 flex flex-wrap gap-3">
          <button
            disabled={isPending || !prompt.trim()}
            onClick={() =>
              startTransition(async () => {
                try {
                  setError("");
                  setPreview(null);
                  setLogs([]);
                  const nextRunId = await tauriClient.startCustomiseRun(prompt);
                  setRunId(nextRunId);
                  setPreview(await tauriClient.getCustomisePreview(nextRunId));
                  setHistory(await tauriClient.getCustomiseHistory());
                } catch (event) {
                  setError(event instanceof Error ? event.message : "Customise run failed.");
                }
              })
            }
            className="rounded-full bg-[color:var(--ink)] px-5 py-3 text-sm font-semibold text-white disabled:opacity-60"
          >
            {isPending ? "Running..." : "Generate Preview"}
          </button>
          <button
            disabled={!preview}
            onClick={async () => {
              if (!preview) {
                return;
              }
              await tauriClient.applyCustomiseRun(preview.runId);
              setHistory(await tauriClient.getCustomiseHistory());
            }}
            className="rounded-full border border-[color:var(--line)] px-5 py-3 text-sm font-semibold disabled:opacity-60"
          >
            Apply
          </button>
          <button
            disabled={!runId}
            onClick={async () => {
              if (!runId) {
                return;
              }
              await tauriClient.discardCustomiseRun(runId);
              setPreview(null);
            }}
            className="rounded-full border border-[color:var(--line)] px-5 py-3 text-sm font-semibold disabled:opacity-60"
          >
            Discard
          </button>
        </div>
      </Panel>
      <div className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
        <Panel>
          <SectionTitle
            eyebrow="Event Log"
            title="Host orchestration"
            action={runId ? <Badge tone="accent">{runId}</Badge> : undefined}
          />
          <div className="mt-5 space-y-3">
            {logs.length ? (
              logs
                .slice()
                .reverse()
                .map((log, index) => (
                  <div key={`${log.phase}-${index}`} className="rounded-[22px] bg-[color:var(--surface-strong)] px-4 py-4">
                    <div className="monoline text-[11px] text-[color:var(--subtle)]">{log.phase}</div>
                    <div className="mt-2 text-sm leading-6">{log.message}</div>
                  </div>
                ))
            ) : (
              <div className="rounded-[22px] bg-[color:var(--surface-strong)] px-4 py-8 text-sm text-[color:var(--muted)]">
                Tauri orchestration logs stream here during the preview, install, restart, and revert phases.
              </div>
            )}
          </div>
        </Panel>
        <Panel>
          <SectionTitle eyebrow="Diff Preview" title="Git patch against the custom branch" />
          {preview ? (
            <>
              <div className="mt-5 flex flex-wrap gap-2">
                <Badge tone={preview.allowed ? "success" : "danger"}>{preview.allowed ? "allowed" : "blocked"}</Badge>
                <Badge>{preview.changedPaths.length} files</Badge>
              </div>
              {preview.error ? (
                <div className="mt-4 rounded-[20px] bg-[color:var(--danger-soft)] px-4 py-3 text-sm text-[color:var(--danger)]">{preview.error}</div>
              ) : null}
              <pre className="mt-5 overflow-x-auto rounded-[24px] bg-[color:var(--ink)] px-5 py-5 text-sm leading-6 text-white">
                {preview.diff || "No diff produced."}
              </pre>
            </>
          ) : (
            <div className="mt-5 rounded-[22px] bg-[color:var(--surface-strong)] px-4 py-8 text-sm text-[color:var(--muted)]">
              Start a customise run to generate a diff preview in a temporary worktree before touching the live repo.
            </div>
          )}
        </Panel>
      </div>
    </AppShell>
  );
}
