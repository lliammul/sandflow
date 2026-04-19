"use client";

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import type {
  BootstrapPayload,
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
};

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
