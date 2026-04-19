"use client";

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import type {
  BootstrapPayload,
  CustomiseLogEntry,
  CustomiseStatus,
  RuntimeStatus,
  SidecarChangedEvent,
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
  async saveArtifactToDownloads(storedPath: string, filename: string) {
    return invoke<string>("save_artifact_to_downloads", { storedPath, filename });
  },
  async revealPathInFinder(path: string) {
    return invoke<void>("reveal_path_in_finder", { path });
  },
  async openExternal(url: string) {
    return invoke<void>("open_external", { url });
  },
  async getCustomiseStatus() {
    if (!isTauriRuntime()) {
      return null;
    }
    return invoke<CustomiseStatus | null>("get_customise_status");
  },
  async startCustomiseRun(prompt: string) {
    return invoke<CustomiseStatus>("start_customise_run", { payload: { prompt } });
  },
  async approveCustomiseRun() {
    return invoke<CustomiseStatus>("approve_customise_run");
  },
  async discardCustomiseRun() {
    return invoke<void>("discard_customise_run");
  },
};

export async function listenToCustomiseRunUpdated(
  onEvent: (status: CustomiseStatus | { cleared: true }) => void,
): Promise<UnlistenFn> {
  if (!isTauriRuntime()) {
    return () => {};
  }
  return listen<CustomiseStatus | { cleared: true }>("customise-run-updated", (event) => {
    onEvent(event.payload);
  });
}

export async function listenToCustomiseLog(
  onEvent: (entry: CustomiseLogEntry) => void,
): Promise<UnlistenFn> {
  if (!isTauriRuntime()) {
    return () => {};
  }
  return listen<CustomiseLogEntry>("customise-log", (event) => {
    onEvent(event.payload);
  });
}

export async function listenToSidecarChanged(
  onEvent: (event: SidecarChangedEvent) => void,
): Promise<UnlistenFn> {
  if (!isTauriRuntime()) {
    return () => {};
  }
  return listen<SidecarChangedEvent>("sidecar-changed", (event) => {
    runtimeStatusCache = runtimeStatusCache
      ? { ...runtimeStatusCache, sidecarBaseUrl: event.payload.baseUrl, sidecarPort: event.payload.newPort }
      : runtimeStatusCache;
    onEvent(event.payload);
  });
}

export function getCachedRuntimeStatus() {
  return runtimeStatusCache;
}
