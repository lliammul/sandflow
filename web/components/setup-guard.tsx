"use client";

import { useEffect, useState, useTransition } from "react";

import { isTauriRuntime, tauriClient } from "../lib/tauri";
import type { RuntimeStatus } from "../lib/types";

export function SetupGuard() {
  const [mounted, setMounted] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [sandboxModel, setSandboxModel] = useState("");
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) {
      return;
    }
    if (!isTauriRuntime()) {
      return;
    }
    tauriClient.getRuntimeStatus().then((status) => {
      if (!status) {
        return;
      }
      setRuntimeStatus(status);
      setBaseUrl(status.config.openAiBaseUrl);
      setSandboxModel(status.config.sandboxModel);
    });
  }, [mounted]);

  if (!mounted) {
    return null;
  }

  if (isTauriRuntime() && runtimeStatus === null) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(21,33,41,0.32)] backdrop-blur-sm">
        <div className="rounded-full bg-white px-5 py-3 text-sm font-medium text-[color:var(--muted)]">Loading desktop runtime…</div>
      </div>
    );
  }

  if (!runtimeStatus?.needsSetup) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(21,33,41,0.42)] p-6 backdrop-blur-md">
      <div className="panel w-full max-w-[760px] rounded-[32px] p-7">
        <div className="monoline text-[11px] text-[color:var(--subtle)]">First Run Bootstrap</div>
        <div className="mt-3 text-4xl font-semibold tracking-[-0.05em]">Prepare the writable local runtime.</div>
        <p className="mt-3 max-w-[42rem] text-sm leading-6 text-[color:var(--muted)]">
          The desktop app needs Docker, your OpenAI credentials, and a writable repo clone in app-data before the
          sandbox runner and Customise flow can start.
        </p>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <StatusChip label="Docker" ok={runtimeStatus.dockerAvailable} />
          <StatusChip label="Repo Bootstrap" ok={runtimeStatus.bootstrapped} />
        </div>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <label className="space-y-2">
            <span className="monoline text-[11px] text-[color:var(--subtle)]">OpenAI API Key</span>
            <input
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              className="w-full rounded-[20px] border border-[color:var(--line)] bg-white px-4 py-3"
              placeholder="sk-..."
              type="password"
            />
          </label>
          <label className="space-y-2">
            <span className="monoline text-[11px] text-[color:var(--subtle)]">Sandbox Model</span>
            <input
              value={sandboxModel}
              onChange={(event) => setSandboxModel(event.target.value)}
              className="w-full rounded-[20px] border border-[color:var(--line)] bg-white px-4 py-3"
              placeholder="gpt-5"
            />
          </label>
          <label className="space-y-2 md:col-span-2">
            <span className="monoline text-[11px] text-[color:var(--subtle)]">OpenAI Base URL</span>
            <input
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              className="w-full rounded-[20px] border border-[color:var(--line)] bg-white px-4 py-3"
              placeholder="https://api.openai.com/v1"
            />
          </label>
        </div>
        {error ? (
          <div className="mt-4 rounded-[20px] bg-[color:var(--danger-soft)] px-4 py-3 text-sm text-[color:var(--danger)]">
            {error}
          </div>
        ) : null}
        <div className="mt-6 flex items-center justify-between gap-4">
          <div className="text-sm text-[color:var(--muted)]">Bootstrap installs dependencies and creates the `custom` branch.</div>
          <button
            disabled={isPending}
            onClick={() =>
              startTransition(async () => {
                try {
                  setError("");
                  const next = await tauriClient.bootstrapRuntime({
                    openAiApiKey: apiKey,
                    openAiBaseUrl: baseUrl,
                    sandboxModel,
                  });
                  setRuntimeStatus(next);
                } catch (event) {
                  setError(extractMessage(event));
                }
              })
            }
            className="rounded-full bg-[color:var(--ink)] px-5 py-3 text-sm font-semibold text-white disabled:opacity-60"
          >
            {isPending ? "Bootstrapping..." : "Bootstrap Runtime"}
          </button>
        </div>
      </div>
    </div>
  );
}

function extractMessage(value: unknown) {
  if (value instanceof Error && value.message) {
    return value.message;
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const message = record.message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  return "Bootstrap failed.";
}

function StatusChip({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div
      className={`rounded-[22px] border px-4 py-4 text-sm ${ok ? "border-[color:var(--success)] bg-[color:var(--success-soft)] text-[color:var(--success)]" : "border-[color:var(--danger)] bg-[color:var(--danger-soft)] text-[color:var(--danger)]"}`}
    >
      <span className="monoline mr-2 text-[11px]">{label}</span>
      {ok ? "Ready" : "Action required"}
    </div>
  );
}
