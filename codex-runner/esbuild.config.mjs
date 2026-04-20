import { build } from "esbuild";

await build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  platform: "node",
  target: "node20",
  format: "esm",
  outfile: "dist/index.mjs",
  external: ["@openai/codex"],
  banner: {
    js: "#!/usr/bin/env node",
  },
  logLevel: "info",
});
