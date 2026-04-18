import {
  SidecarEvent,
  WorkflowDefinition,
  WorkflowProgressEvent,
  WorkflowRegistryEntry,
  WorkflowRunRecord,
  WorkflowRunTerminalEvent,
} from "./types";
import { getCachedRuntimeStatus, tauriClient } from "./tauri";

async function getBaseUrl() {
  const cached = getCachedRuntimeStatus();
  if (cached?.sidecarBaseUrl) {
    return cached.sidecarBaseUrl;
  }
  const runtimeStatus = await tauriClient.getRuntimeStatus();
  if (runtimeStatus?.sidecarBaseUrl) {
    return runtimeStatus.sidecarBaseUrl;
  }
  const fallback = process.env.NEXT_PUBLIC_SIDECAR_BASE_URL;
  if (fallback) {
    return fallback;
  }
  throw new Error("The Python sidecar is not available yet.");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const baseUrl = await getBaseUrl();
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const sidecar = {
  baseUrl: getBaseUrl,
  getHealth: () => request<{ status: string; version: string }>("/health"),
  getWorkflowEntries: (includeInactive = true) =>
    request<WorkflowRegistryEntry[]>(`/workflow-entries?include_inactive=${includeInactive ? 1 : 0}`),
  getWorkflows: (includeInactive = false) =>
    request<WorkflowDefinition[]>(`/workflows?include_inactive=${includeInactive ? 1 : 0}`),
  getWorkflow: (id: string) => request<WorkflowDefinition>(`/workflows/${id}`),
  saveWorkflow: (workflow: WorkflowDefinition) =>
    request<WorkflowDefinition>(`/workflows/${workflow.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(workflow),
    }),
  deleteWorkflow: (id: string) =>
    request<void>(`/workflows/${id}`, {
      method: "DELETE",
    }),
  getRuns: (limit = 10) => request<WorkflowRunRecord[]>(`/runs?limit=${limit}`),
  getRun: (runId: string) => request<WorkflowRunRecord>(`/runs/${runId}`),
  submitRun: async (workflowId: string, formData: FormData) => {
    const response = await request<{ run_id: string }>(`/workflows/${workflowId}/run`, {
      method: "POST",
      body: formData,
    });
    return response.run_id;
  },
  streamRun: async (
    runId: string,
    handlers: {
      onProgress: (event: WorkflowProgressEvent) => void;
      onTerminal: (event: WorkflowRunTerminalEvent) => void;
      onError?: (error: Event) => void;
    },
  ) => {
    const baseUrl = await getBaseUrl();
    const source = new EventSource(`${baseUrl}/runs/${runId}/events`);
    source.addEventListener("progress", (event) => {
      const parsed = JSON.parse((event as MessageEvent).data) as SidecarEvent<"progress", WorkflowProgressEvent>;
      handlers.onProgress(parsed.payload);
    });
    source.addEventListener("terminal", (event) => {
      const parsed = JSON.parse((event as MessageEvent).data) as SidecarEvent<"terminal", WorkflowRunTerminalEvent>;
      handlers.onTerminal(parsed.payload);
      source.close();
    });
    source.addEventListener("error", (event) => {
      handlers.onError?.(event);
      source.close();
    });
    return source;
  },
  artifactUrl: async (runId: string, artifactId: string) => `${await getBaseUrl()}/runs/${runId}/artifacts/${artifactId}`,
};
