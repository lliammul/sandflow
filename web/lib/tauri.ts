"use client";

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import type {
  BootstrapPayload,
  CustomiseHistoryEntry,
  CustomiseLogEvent,
  CustomisePreview,
  RuntimeStatus,
} from "./types";

export function isTauriRuntime() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

let runtimeStatusCache: RuntimeStatus | null = null;

export const tauriClient = {
  async getRuntimeStatus(): Promise<RuntimeStatus | null> {
    if (!isTauriRuntime()) {
      return null;
    }
    const status = await invoke<RuntimeStatus>("get_runtime_status");
    runtimeStatusCache = status;
    return status;
  },
  async bootstrapRuntime(payload: BootstrapPayload) {
    const status = await invoke<RuntimeStatus>("bootstrap_runtime", { payload });
    runtimeStatusCache = status;
    return status;
  },
  async openRepoInEditor() {
    return invoke<void>("open_repo_in_editor");
  },
  async startCustomiseRun(prompt: string) {
    return invoke<string>("start_customise_run", { prompt });
  },
  async getCustomisePreview(runId: string) {
    return invoke<CustomisePreview>("get_customise_preview", { runId });
  },
  async applyCustomiseRun(runId: string) {
    return invoke<CustomisePreview>("apply_customise_run", { runId });
  },
  async discardCustomiseRun(runId: string) {
    return invoke<void>("discard_customise_run", { runId });
  },
  async revertCustomCommit(commitSha: string) {
    return invoke<void>("revert_custom_commit", { commitSha });
  },
  async resetCustomisations() {
    return invoke<void>("reset_customisations");
  },
  async getCustomiseHistory() {
    return invoke<CustomiseHistoryEntry[]>("get_customise_history");
  },
  async listenToCustomiseLogs(onEvent: (event: CustomiseLogEvent) => void): Promise<UnlistenFn> {
    return listen<CustomiseLogEvent>("customise-log", (event) => onEvent(event.payload));
  },
};

export function getCachedRuntimeStatus() {
  return runtimeStatusCache;
}
