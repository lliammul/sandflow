import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const workspaceRoot = resolve(scriptDir, "..", "..");

const repoDir = process.env.SANDFLOW_REPO_DIR
  ? resolve(process.env.SANDFLOW_REPO_DIR)
  : workspaceRoot;
const webDir = resolve(repoDir, "web");
const port = process.env.SANDFLOW_WEB_PORT ?? "3100";

if (!existsSync(webDir)) {
  console.error(
    `[dev-web] web/ not found at ${webDir}. ` +
      `Set SANDFLOW_REPO_DIR to a seeded repo (run \`pnpm tauri:dev\` once to seed app-data), or unset it to use the workspace.`,
  );
  process.exit(1);
}

if (!existsSync(resolve(webDir, "node_modules"))) {
  console.log(`[dev-web] installing dependencies in ${webDir}`);
  const install = spawnSync("pnpm", ["install", "--dir", webDir], {
    stdio: "inherit",
    cwd: repoDir,
  });
  if (install.status !== 0) {
    process.exit(install.status ?? 1);
  }
}

console.log(`[dev-web] next dev in ${webDir} on port ${port}`);
const child = spawn("pnpm", ["--dir", webDir, "dev", "--port", port], {
  stdio: "inherit",
  cwd: repoDir,
  env: process.env,
});

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, () => {
    child.kill(signal);
  });
}

child.on("exit", (code, signal) => {
  if (signal) {
    process.exit(1);
  }
  process.exit(code ?? 0);
});
