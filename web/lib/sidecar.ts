import {
  SidecarEvent,
  WorkflowDefinition,
  WorkflowProgressEvent,
  WorkflowRegistryEntry,
  WorkflowRunRecord,
  WorkflowRunTerminalEvent,
} from "./types";
import {
  getCachedRuntimeStatus,
  listenToSidecarChanged,
  tauriClient,
} from "./tauri";

type Subscriber = (baseUrl: string) => void;

class SidecarClient {
  private currentBaseUrl: string | null = null;
  private reconnectSubscribers = new Set<Subscriber>();
  private listenerAttached = false;

  private ensureListener() {
    if (this.listenerAttached) return;
    this.listenerAttached = true;
    void listenToSidecarChanged((event) => {
      this.currentBaseUrl = event.baseUrl;
      for (const sub of this.reconnectSubscribers) {
        try {
          sub(event.baseUrl);
        } catch {}
      }
    }).catch(() => {
      this.listenerAttached = false;
    });
  }

  async getBaseUrl(forceFresh = false): Promise<string> {
    this.ensureListener();
    if (!forceFresh && this.currentBaseUrl) {
      return this.currentBaseUrl;
    }
    const cached = getCachedRuntimeStatus();
    if (!forceFresh && cached?.sidecarBaseUrl) {
      this.currentBaseUrl = cached.sidecarBaseUrl;
      return this.currentBaseUrl;
    }
    const runtimeStatus = await tauriClient.getRuntimeStatus();
    if (runtimeStatus?.sidecarBaseUrl) {
      this.currentBaseUrl = runtimeStatus.sidecarBaseUrl;
      return this.currentBaseUrl;
    }
    const fallback = process.env.NEXT_PUBLIC_SIDECAR_BASE_URL;
    if (fallback) {
      this.currentBaseUrl = fallback;
      return fallback;
    }
    throw new Error("The Python sidecar is not available yet.");
  }

  subscribeToReconnect(fn: Subscriber): () => void {
    this.ensureListener();
    this.reconnectSubscribers.add(fn);
    return () => this.reconnectSubscribers.delete(fn);
  }

  async fetchWithRetry(path: string, init?: RequestInit): Promise<Response> {
    const delays = [0, 50, 200, 800];
    let lastError: unknown;
    for (let attempt = 0; attempt < delays.length; attempt++) {
      if (delays[attempt] > 0) {
        await sleep(delays[attempt]);
      }
      const forceFresh = attempt > 0;
      try {
        const baseUrl = await this.getBaseUrl(forceFresh);
        return await fetch(`${baseUrl}${path}`, {
          ...init,
          cache: "no-store",
        });
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError instanceof Error ? lastError : new Error("Network error talking to sidecar.");
  }
}

const client = new SidecarClient();

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await client.fetchWithRetry(path, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function subscribeToSidecarReconnect(fn: (baseUrl: string) => void) {
  return client.subscribeToReconnect(fn);
}

export const sidecar = {
  baseUrl: () => client.getBaseUrl(),
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
      onReconnecting?: () => void;
    },
  ) => {
    let terminated = false;
    let reconnecting = false;
    let currentSource: EventSource | null = null;
    const originBaseUrl = await client.getBaseUrl();
    let lastSuccessfulBaseUrl = originBaseUrl;

    const wire = (source: EventSource, baseUrl: string, fallbackBaseUrls: string[] = []) => {
      source.addEventListener("progress", (event) => {
        lastSuccessfulBaseUrl = baseUrl;
        const parsed = JSON.parse((event as MessageEvent).data) as SidecarEvent<"progress", WorkflowProgressEvent>;
        handlers.onProgress(parsed.payload);
      });
      source.addEventListener("terminal", (event) => {
        const parsed = JSON.parse((event as MessageEvent).data) as SidecarEvent<"terminal", WorkflowRunTerminalEvent>;
        terminated = true;
        reconnecting = false;
        lastSuccessfulBaseUrl = baseUrl;
        handlers.onTerminal(parsed.payload);
        source.close();
      });
      source.addEventListener("error", (event) => {
        source.close();
        if (terminated || reconnecting) {
          return;
        }
        reconnecting = true;
        handlers.onReconnecting?.();
        if (fallbackBaseUrls.length > 0) {
          const [nextBaseUrl, ...rest] = fallbackBaseUrls;
          void openStream(nextBaseUrl, rest);
        } else {
          void reconnect();
        }
        handlers.onError?.(event);
      });
    };

    const openStream = async (baseUrl: string, fallbackBaseUrls: string[] = []) => {
      if (terminated) {
        return;
      }
      const next = new EventSource(`${baseUrl}/runs/${runId}/events`);
      currentSource = next;
      wire(next, baseUrl, fallbackBaseUrls);
      reconnecting = false;
    };

    const reconnect = async () => {
      if (terminated) {
        return;
      }

      const latestBaseUrl = await client.getBaseUrl(true).catch(() => null);
      const candidates = dedupeBaseUrls([lastSuccessfulBaseUrl, latestBaseUrl]);
      if (candidates.length === 0) {
        return;
      }
      const [baseUrl, ...fallbackBaseUrls] = candidates;
      await openStream(baseUrl, fallbackBaseUrls);
    };

    currentSource = new EventSource(`${originBaseUrl}/runs/${runId}/events`);
    wire(currentSource, originBaseUrl);

    return currentSource;
  },
  artifactUrl: async (runId: string, artifactId: string) => `${await client.getBaseUrl()}/runs/${runId}/artifacts/${artifactId}`,
  downloadArtifact: async (runId: string, artifactId: string) => {
    const response = await client.fetchWithRetry(`/runs/${runId}/artifacts/${artifactId}`);
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `Request failed with ${response.status}`);
    }
    return response.blob();
  },
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function dedupeBaseUrls(values: Array<string | null>): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))];
}
