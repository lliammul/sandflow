import { Codex, type ThreadEvent } from "@openai/codex-sdk";

type RunnerInput = {
  runId: string;
  prompt: string;
  cwd: string;
  apiKey: string;
  baseUrl?: string;
  model?: string;
  lockedGlobs: string[];
};

type RunnerEvent =
  | { type: "runner.started"; runId: string; cwd: string }
  | { type: "runner.error"; runId: string; message: string }
  | { type: "runner.completed"; runId: string; status: "success" | "failed" }
  | { type: "sdk"; runId: string; event: ThreadEvent };

function emit(event: RunnerEvent) {
  process.stdout.write(JSON.stringify(event) + "\n");
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf-8");
}

function validateInput(payload: unknown): RunnerInput {
  if (!payload || typeof payload !== "object") {
    throw new Error("runner input must be a JSON object");
  }
  const record = payload as Record<string, unknown>;
  const requiredStrings = ["runId", "prompt", "cwd", "apiKey"] as const;
  for (const key of requiredStrings) {
    if (typeof record[key] !== "string" || !(record[key] as string).length) {
      throw new Error(`runner input missing string field: ${key}`);
    }
  }
  if (!Array.isArray(record.lockedGlobs)) {
    throw new Error("runner input missing array field: lockedGlobs");
  }
  for (const glob of record.lockedGlobs) {
    if (typeof glob !== "string") {
      throw new Error("lockedGlobs must contain strings only");
    }
  }
  return {
    runId: record.runId as string,
    prompt: record.prompt as string,
    cwd: record.cwd as string,
    apiKey: record.apiKey as string,
    baseUrl: typeof record.baseUrl === "string" ? (record.baseUrl as string) : undefined,
    model: typeof record.model === "string" ? (record.model as string) : undefined,
    lockedGlobs: record.lockedGlobs as string[],
  };
}

async function main() {
  let input: RunnerInput;
  try {
    const raw = await readStdin();
    input = validateInput(JSON.parse(raw));
  } catch (error) {
    emit({
      type: "runner.error",
      runId: "unknown",
      message: error instanceof Error ? error.message : String(error),
    });
    process.exit(2);
  }

  emit({ type: "runner.started", runId: input.runId, cwd: input.cwd });

  const codex = new Codex({
    apiKey: input.apiKey,
    baseUrl: input.baseUrl,
    env: {
      PATH: process.env.PATH ?? "/usr/local/bin:/usr/bin:/bin",
      HOME: process.env.HOME ?? "",
      TMPDIR: process.env.TMPDIR ?? "/tmp",
    },
  });

  const thread = codex.startThread({
    workingDirectory: input.cwd,
    sandboxMode: "workspace-write",
    approvalPolicy: "never",
    skipGitRepoCheck: false,
    model: input.model,
    networkAccessEnabled: false,
    webSearchEnabled: false,
  });

  try {
    const { events } = await thread.runStreamed(input.prompt);
    let sawFailure = false;
    for await (const event of events) {
      emit({ type: "sdk", runId: input.runId, event });
      if (event.type === "turn.failed") {
        sawFailure = true;
      }
    }
    emit({
      type: "runner.completed",
      runId: input.runId,
      status: sawFailure ? "failed" : "success",
    });
    process.exit(sawFailure ? 1 : 0);
  } catch (error) {
    emit({
      type: "runner.error",
      runId: input.runId,
      message: error instanceof Error ? error.message : String(error),
    });
    emit({ type: "runner.completed", runId: input.runId, status: "failed" });
    process.exit(1);
  }
}

main().catch((error) => {
  emit({
    type: "runner.error",
    runId: "unknown",
    message: error instanceof Error ? error.message : String(error),
  });
  process.exit(1);
});
