"use client";

import clsx from "clsx";
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
      setApiKey(status.config.openAiApiKey);
      setBaseUrl(status.config.openAiBaseUrl);
      setSandboxModel(status.config.sandboxModel);
      if (!status.needsSetup) {
        window.dispatchEvent(new CustomEvent("sandflow:runtime-ready"));
      }
    });
  }, [mounted]);

  if (!mounted) {
    return null;
  }

  if (isTauriRuntime() && runtimeStatus === null) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(17,17,17,0.4)]">
        <div className="mono border border-[color:var(--line)] bg-white px-4 py-2 text-sm text-[color:var(--muted)]">
          Loading desktop runtime…
        </div>
      </div>
    );
  }

  if (!runtimeStatus?.needsSetup) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(17,17,17,0.5)] p-6">
      <div className="panel w-full max-w-[720px]">
        <div className="border-b border-[color:var(--line)] px-5 py-4">
          <div className="monoline">First run bootstrap</div>
          <div className="mt-1 text-2xl font-semibold tracking-[-0.02em]">Prepare the desktop runtime.</div>
          <p className="mt-2 max-w-[40rem] text-sm leading-6 text-[color:var(--muted)]">
            The desktop app needs Docker, your OpenAI credentials, and a writable runtime repo in app-data before
            workflows can run locally.
          </p>
        </div>
        <div className="space-y-5 px-5 py-5">
          <div className="grid gap-3 md:grid-cols-2">
            <StatusChip label="Docker" ok={runtimeStatus.dockerAvailable} />
            <StatusChip label="Repo Bootstrap" ok={runtimeStatus.bootstrapped} />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-2">
              <span className="monoline">OpenAI API Key</span>
              <input
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                className="w-full"
                placeholder="sk-..."
                type="password"
              />
            </label>
            <label className="flex flex-col gap-2">
              <span className="monoline">Sandbox Model</span>
              <input
                value={sandboxModel}
                onChange={(event) => setSandboxModel(event.target.value)}
                className="w-full"
                placeholder="gpt-5"
              />
            </label>
            <label className="flex flex-col gap-2 md:col-span-2">
              <span className="monoline">OpenAI Base URL</span>
              <input
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                className="w-full"
                placeholder="https://api.openai.com/v1"
              />
            </label>
          </div>
          {error ? (
            <div role="alert" className="border border-[color:var(--danger)] bg-[color:var(--danger-soft)] px-3 py-2 text-sm text-[color:var(--danger)]">
              {error}
            </div>
          ) : null}
        </div>
        <div className="flex items-center justify-between gap-4 border-t border-[color:var(--line)] px-5 py-4">
          <div className="text-sm text-[color:var(--muted)]">Bootstrap creates the managed runtime copy and installs its dependencies.</div>
          <button
            type="button"
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
                  if (!next.needsSetup) {
                    window.dispatchEvent(new CustomEvent("sandflow:runtime-ready"));
                  }
                } catch (event) {
                  setError(extractMessage(event));
                }
              })
            }
            className="btn btn-primary"
          >
            {isPending ? "Bootstrapping…" : "Bootstrap Runtime"}
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
      className={clsx(
        "flex items-center justify-between border px-3 py-3 text-sm",
        ok
          ? "border-[color:var(--success)] bg-[color:var(--success-soft)] text-[color:var(--success)]"
          : "border-[color:var(--danger)] bg-[color:var(--danger-soft)] text-[color:var(--danger)]",
      )}
    >
      <span className="monoline text-current">{label}</span>
      <span className="mono text-[12px] font-semibold">{ok ? "Ready" : "Action required"}</span>
    </div>
  );
}
