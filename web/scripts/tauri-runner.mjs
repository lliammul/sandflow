import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDir, "..", "..");
const tauriConfigPath = resolve(projectRoot, "src-tauri", "tauri.conf.json");
const tauriConfig = JSON.parse(readFileSync(tauriConfigPath, "utf8"));
const tauriBinary =
  process.env.TAURI_CLI_PATH ??
  resolve(projectRoot, "web", "node_modules", ".bin", "tauri");
const rawArgs = process.argv.slice(2);
const resetState = rawArgs.includes("--reset-state");
const tauriArgs = rawArgs.filter((arg) => arg !== "--reset-state");

if (tauriArgs.length === 0) {
  console.error("Usage: node web/scripts/tauri-runner.mjs <tauri-args...>");
  process.exit(1);
}

if (tauriArgs[0] === "dev" && resetState) {
  reseedDevRuntimeRepo();
}

const childEnv = { ...process.env };
if (process.platform === "darwin" && tauriArgs[0] === "build" && !("CI" in childEnv)) {
  // DMG bundling falls back to a headless-safe path when CI is set, which avoids
  // Finder Apple Events during local terminal builds.
  childEnv.CI = "true";
}

const child = spawn(tauriBinary, tauriArgs, {
  cwd: projectRoot,
  detached: process.platform !== "win32",
  stdio: "inherit",
  env: childEnv,
});

let forwardedSignal = null;
let forcedKillTimer = null;

const signalExitCodes = {
  SIGHUP: 129,
  SIGINT: 130,
  SIGTERM: 143,
};

function forceKill() {
  if (child.exitCode !== null || child.signalCode !== null) {
    return;
  }

  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
      stdio: "inherit",
    });
    return;
  }

  try {
    process.kill(-child.pid, "SIGKILL");
  } catch (error) {
    if (error.code !== "ESRCH") {
      throw error;
    }
  }
}

function forwardSignal(signal) {
  if (forwardedSignal) {
    return;
  }

  forwardedSignal = signal;

  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
      stdio: "inherit",
    });
  } else {
    try {
      process.kill(-child.pid, signal);
    } catch (error) {
      if (error.code !== "ESRCH") {
        throw error;
      }
    }
  }

  forcedKillTimer = setTimeout(forceKill, 5000);
}

child.once("error", (error) => {
  console.error(error.message);
  process.exit(1);
});

child.once("exit", (code, signal) => {
  if (forcedKillTimer) {
    clearTimeout(forcedKillTimer);
  }

  if (forwardedSignal) {
    process.exit(signalExitCodes[forwardedSignal] ?? 1);
  }

  if (signal) {
    process.exit(signalExitCodes[signal] ?? 1);
  }

  process.exit(code ?? 0);
});

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, () => forwardSignal(signal));
}

function reseedDevRuntimeRepo() {
  const appDataDir = resolveAppDataDir(tauriConfig.identifier);
  const repoPath = resolve(appDataDir, "repo");

  console.log(`Reseeding dev runtime repo at ${repoPath}`);

  mkdirSync(appDataDir, { recursive: true });
  rmSync(repoPath, { recursive: true, force: true });
  mkdirSync(repoPath, { recursive: true });

  runOrThrow("rsync", [
    "-a",
    "--delete",
    "--exclude",
    ".git",
    "--exclude",
    ".git/",
    "--exclude",
    ".context/",
    "--exclude",
    ".application/",
    "--exclude",
    ".venv/",
    "--exclude",
    "python-sidecar/.venv/",
    "--exclude",
    "web/node_modules/",
    "--exclude",
    "web/.next/",
    "--exclude",
    "src-tauri/target/",
    "--exclude",
    "__pycache__/",
    "--exclude",
    "*.pyc",
    `${projectRoot}/`,
    `${repoPath}/`,
  ]);

  const copiedGitPath = resolve(repoPath, ".git");
  if (existsSync(copiedGitPath)) {
    rmSync(copiedGitPath, { recursive: true, force: true });
  }

  runOrThrow("git", ["init", "--quiet", "-b", "main"], repoPath);
  runOrThrow("git", ["config", "user.email", "sandflow@local.invalid"], repoPath);
  runOrThrow("git", ["config", "user.name", "Sandflow Desktop"], repoPath);
  runOrThrow("git", ["add", "-A"], repoPath);
  runOrThrow("git", ["commit", "--quiet", "-m", "Initial Sandflow desktop runtime"], repoPath);
}

function resolveAppDataDir(identifier) {
  if (process.platform === "darwin") {
    return resolve(homedir(), "Library", "Application Support", identifier);
  }
  if (process.platform === "win32") {
    const base = process.env.APPDATA ?? resolve(homedir(), "AppData", "Roaming");
    return resolve(base, identifier);
  }
  return resolve(process.env.XDG_DATA_HOME ?? resolve(homedir(), ".local", "share"), identifier);
}

function runOrThrow(command, args, cwd = projectRoot) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    stdio: "inherit",
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}
