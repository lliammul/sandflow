use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use anyhow::{anyhow, bail, Context, Result};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, State};

use crate::util::{
    docker_available, git_lines, git_run, matches_locked_path, pick_port, run_checked,
    unix_timestamp, wait_for_http,
};
use crate::{DesktopState, RuntimeConfig, CUSTOMISE_LOCKED_PATHS};

const DEFAULT_CODEX_MODEL: &str = "gpt-5-codex";

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CustomiseStatus {
    pub run_id: String,
    pub prompt: String,
    pub preview_path: String,
    pub preview_sidecar_url: Option<String>,
    pub preview_web_url: Option<String>,
    pub state: CustomiseState,
    pub started_at: u64,
    pub log: Vec<CustomiseLogEntry>,
    pub changed_paths: Vec<String>,
    pub locked_violations: Vec<String>,
    pub error: Option<String>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CustomiseState {
    Cloning,
    Generating,
    ReadyForReview,
    Applying,
    Applied,
    Failed,
    Cancelled,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CustomiseLogEntry {
    pub ts: u64,
    pub level: String,
    pub message: String,
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StartCustomisePayload {
    pub prompt: String,
}

pub struct PreviewSession {
    pub run_id: String,
    pub prompt: String,
    pub preview_path: PathBuf,
    pub preview_sidecar_port: Option<u16>,
    pub preview_sidecar_child: Option<Child>,
    pub preview_web_port: Option<u16>,
    pub preview_web_child: Option<Child>,
    pub codex_child: Option<Child>,
    pub state: CustomiseState,
    pub started_at: u64,
    pub log: Vec<CustomiseLogEntry>,
    pub changed_paths: Vec<String>,
    pub locked_violations: Vec<String>,
    pub error: Option<String>,
}

impl PreviewSession {
    fn to_status(&self) -> CustomiseStatus {
        CustomiseStatus {
            run_id: self.run_id.clone(),
            prompt: self.prompt.clone(),
            preview_path: self.preview_path.display().to_string(),
            preview_sidecar_url: self
                .preview_sidecar_port
                .map(|p| format!("http://127.0.0.1:{p}")),
            preview_web_url: self.preview_web_port.map(|p| format!("http://127.0.0.1:{p}")),
            state: self.state.clone(),
            started_at: self.started_at,
            log: self.log.clone(),
            changed_paths: self.changed_paths.clone(),
            locked_violations: self.locked_violations.clone(),
            error: self.error.clone(),
        }
    }
}

pub fn get_customise_status_impl(state: &State<'_, Mutex<DesktopState>>) -> Result<Option<CustomiseStatus>> {
    let guard = state.lock().map_err(|_| anyhow!("state unavailable"))?;
    Ok(guard.preview.as_ref().map(|p| p.to_status()))
}

pub fn start_customise_run_impl(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    payload: StartCustomisePayload,
) -> Result<CustomiseStatus> {
    if payload.prompt.trim().is_empty() {
        bail!("Customise prompt must not be empty.");
    }
    if !docker_available() {
        bail!("Docker must be running to start a customise run.");
    }

    let (repo_path, runtime_root, api_key, config) = {
        let guard = state.lock().map_err(|_| anyhow!("state unavailable"))?;
        if guard.preview.is_some() {
            bail!("A customise run is already in progress. Approve or discard it first.");
        }
        let repo_path = guard
            .runtime
            .repo_path
            .clone()
            .ok_or_else(|| anyhow!("Runtime has not been bootstrapped."))?;
        let runtime_root = guard
            .runtime
            .runtime_root
            .clone()
            .ok_or_else(|| anyhow!("Runtime root is missing."))?;
        let api_key = guard
            .runtime
            .cached_api_key
            .clone()
            .ok_or_else(|| anyhow!("OpenAI API key is missing."))?;
        let config = crate::load_runtime_config(&runtime_root).unwrap_or_default();
        (repo_path, runtime_root, api_key, config)
    };

    let run_id = format!("cust_{}", uuid_like());
    let previews_root = runtime_root.join("previews");
    fs::create_dir_all(&previews_root)?;
    let preview_path = previews_root.join(&run_id);
    let started_at = unix_timestamp();

    let session = PreviewSession {
        run_id: run_id.clone(),
        prompt: payload.prompt.clone(),
        preview_path: preview_path.clone(),
        preview_sidecar_port: None,
        preview_sidecar_child: None,
        preview_web_port: None,
        preview_web_child: None,
        codex_child: None,
        state: CustomiseState::Cloning,
        started_at,
        log: vec![log_entry("info", format!("Preparing preview workspace at {}", preview_path.display()))],
        changed_paths: Vec::new(),
        locked_violations: Vec::new(),
        error: None,
    };

    {
        let mut guard = state.lock().map_err(|_| anyhow!("state unavailable"))?;
        guard.preview = Some(session);
    }
    emit_status(app, state);

    let app_clone = app.clone();
    let state_handle = app.state::<Mutex<DesktopState>>();
    let _ = state_handle;
    let run_id_bg = run_id.clone();
    thread::spawn(move || {
        let state = app_clone.state::<Mutex<DesktopState>>();
        if let Err(error) = run_customise_pipeline(
            &app_clone,
            &state,
            &run_id_bg,
            &repo_path,
            &preview_path,
            &payload.prompt,
            &api_key,
            &config,
        ) {
            mark_failed(&app_clone, &state, &run_id_bg, error.to_string());
        }
    });

    get_customise_status_impl(state).map(|opt| opt.expect("session was just created"))
}

fn run_customise_pipeline(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    run_id: &str,
    repo_path: &Path,
    preview_path: &Path,
    prompt: &str,
    api_key: &str,
    config: &RuntimeConfig,
) -> Result<()> {
    // 1. Clone live repo.
    append_log(app, state, run_id, "info", "Cloning live repo into preview.".to_string());
    clone_live_repo(repo_path, preview_path)?;

    // 2. Install deps in preview (best-effort reuse via clone).
    append_log(app, state, run_id, "info", "Installing preview dependencies.".to_string());
    install_preview_deps(preview_path)?;

    // 3. Spawn preview sidecar + preview web.
    append_log(app, state, run_id, "info", "Starting preview sidecar and web.".to_string());
    let (sidecar_child, sidecar_port) = spawn_preview_sidecar(preview_path, api_key, config)?;
    let (web_child, web_port) = spawn_preview_web(preview_path, sidecar_port, run_id)?;

    {
        let mut guard = state.lock().map_err(|_| anyhow!("state unavailable"))?;
        if let Some(session) = guard.preview.as_mut() {
            session.preview_sidecar_port = Some(sidecar_port);
            session.preview_sidecar_child = Some(sidecar_child);
            session.preview_web_port = Some(web_port);
            session.preview_web_child = Some(web_child);
        }
    }
    emit_status(app, state);

    // 4. Wait for preview sidecar ready.
    append_log(app, state, run_id, "info", "Waiting for preview sidecar health.".to_string());
    wait_for_http(sidecar_port, "/health", Duration::from_secs(90))
        .context("preview sidecar did not become healthy")?;
    append_log(app, state, run_id, "info", "Waiting for preview web to start.".to_string());
    wait_for_http(web_port, "/", Duration::from_secs(120))
        .context("preview web did not start")?;

    // 5. Transition to Generating, spawn codex-runner.
    set_state(app, state, run_id, CustomiseState::Generating);
    append_log(app, state, run_id, "info", "Starting Codex runner.".to_string());
    run_codex_runner(app, state, run_id, preview_path, prompt, api_key, config)?;

    // 6. Inspect diff.
    append_log(app, state, run_id, "info", "Inspecting generated diff.".to_string());
    let (changed, violations) = summarise_diff(preview_path)?;
    {
        let mut guard = state.lock().map_err(|_| anyhow!("state unavailable"))?;
        if let Some(session) = guard.preview.as_mut() {
            session.changed_paths = changed;
            session.locked_violations = violations;
        }
    }
    set_state(app, state, run_id, CustomiseState::ReadyForReview);
    emit_status(app, state);
    Ok(())
}

fn clone_live_repo(repo_path: &Path, preview_path: &Path) -> Result<()> {
    if preview_path.exists() {
        fs::remove_dir_all(preview_path)?;
    }
    if let Some(parent) = preview_path.parent() {
        fs::create_dir_all(parent)?;
    }
    run_checked(
        repo_path,
        "git",
        [
            "clone",
            "--local",
            repo_path.to_str().unwrap(),
            preview_path.to_str().unwrap(),
        ],
    )?;
    git_run(preview_path, &["config", "user.email", "sandflow@local.invalid"])?;
    git_run(preview_path, &["config", "user.name", "Sandflow Customise"])?;
    Ok(())
}

fn install_preview_deps(preview_path: &Path) -> Result<()> {
    // Best-effort. If the live repo already has node_modules/venv, clone --local
    // won't copy them. Run the standard installers so preview is runnable.
    run_checked(preview_path, "uv", ["sync", "--project", "python-sidecar"])?;
    run_checked(preview_path, "pnpm", ["install", "--dir", "web"])?;
    Ok(())
}

fn spawn_preview_sidecar(
    preview_path: &Path,
    api_key: &str,
    config: &RuntimeConfig,
) -> Result<(Child, u16)> {
    let port = pick_port()?;
    let log_path = preview_path.join(".sandflow-sidecar.log");
    let stdout = fs::OpenOptions::new().create(true).append(true).open(&log_path)?;
    let stderr = fs::OpenOptions::new().create(true).append(true).open(&log_path)?;
    let child = Command::new("uv")
        .current_dir(preview_path)
        .env("OPENAI_API_KEY", api_key)
        .env("OPENAI_API_BASE", &config.open_ai_base_url)
        .env("OPENAI_SANDBOX_MODEL", &config.sandbox_model)
        .args([
            "run",
            "--project",
            "python-sidecar",
            "python",
            "-m",
            "sandflow_sidecar",
            "--port",
            &port.to_string(),
        ])
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()
        .context("failed to spawn preview sidecar")?;
    Ok((child, port))
}

fn spawn_preview_web(preview_path: &Path, sidecar_port: u16, run_id: &str) -> Result<(Child, u16)> {
    let port = pick_port()?;
    let log_path = preview_path.join(".sandflow-web.log");
    let stdout = fs::OpenOptions::new().create(true).append(true).open(&log_path)?;
    let stderr = fs::OpenOptions::new().create(true).append(true).open(&log_path)?;
    let child = Command::new("pnpm")
        .current_dir(preview_path)
        .env(
            "NEXT_PUBLIC_SIDECAR_BASE_URL",
            format!("http://127.0.0.1:{sidecar_port}"),
        )
        .env("NEXT_PUBLIC_SANDFLOW_PREVIEW_RUN_ID", run_id)
        .args(["--dir", "web", "exec", "next", "dev", "--port", &port.to_string()])
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()
        .context("failed to spawn preview next dev")?;
    Ok((child, port))
}

fn run_codex_runner(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    run_id: &str,
    preview_path: &Path,
    prompt: &str,
    api_key: &str,
    config: &RuntimeConfig,
) -> Result<()> {
    let runner_path = locate_codex_runner()?;
    let locked: Vec<String> = CUSTOMISE_LOCKED_PATHS.iter().map(|s| s.to_string()).collect();
    let model = if config.sandbox_model.is_empty() {
        DEFAULT_CODEX_MODEL.to_string()
    } else {
        config.sandbox_model.clone()
    };
    let input = serde_json::json!({
        "runId": run_id,
        "prompt": prompt,
        "cwd": preview_path.to_string_lossy(),
        "apiKey": api_key,
        "baseUrl": config.open_ai_base_url,
        "model": model,
        "lockedGlobs": locked,
    });

    let mut child = Command::new("node")
        .arg(&runner_path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .context("failed to spawn codex-runner")?;

    {
        use std::io::Write;
        let stdin = child.stdin.as_mut().ok_or_else(|| anyhow!("codex stdin missing"))?;
        stdin.write_all(serde_json::to_vec(&input)?.as_slice())?;
    }
    drop(child.stdin.take());

    {
        let mut guard = state.lock().map_err(|_| anyhow!("state unavailable"))?;
        if let Some(session) = guard.preview.as_mut() {
            // We don't keep the child — we will wait inline. Store None to preserve API shape.
            session.codex_child = None;
        }
    }

    let stdout = child.stdout.take().ok_or_else(|| anyhow!("codex stdout missing"))?;
    let stderr = child.stderr.take().ok_or_else(|| anyhow!("codex stderr missing"))?;

    let app_clone = app.clone();
    let run_id_bg = run_id.to_string();
    let stderr_thread = thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines().flatten() {
            eprintln!("[codex-runner stderr] {line}");
            let state = app_clone.state::<Mutex<DesktopState>>();
            append_log(&app_clone, &state, &run_id_bg, "warn", line);
        }
    });

    let reader = BufReader::new(stdout);
    let mut final_status: Option<String> = None;
    for line in reader.lines() {
        let line = match line {
            Ok(value) if !value.trim().is_empty() => value,
            _ => continue,
        };
        eprintln!("[codex-runner] {line}");
        if let Ok(event) = serde_json::from_str::<serde_json::Value>(&line) {
            if let Some(event_type) = event.get("type").and_then(|v| v.as_str()) {
                match event_type {
                    "runner.started" => {
                        append_log(app, state, run_id, "info", "Codex session started.".to_string());
                    }
                    "runner.error" => {
                        let msg = event
                            .get("message")
                            .and_then(|v| v.as_str())
                            .unwrap_or("codex error")
                            .to_string();
                        append_log(app, state, run_id, "error", msg);
                    }
                    "runner.completed" => {
                        final_status = event
                            .get("status")
                            .and_then(|v| v.as_str())
                            .map(|s| s.to_string());
                        append_log(
                            app,
                            state,
                            run_id,
                            "info",
                            format!(
                                "Codex runner completed: {}",
                                final_status.as_deref().unwrap_or("unknown")
                            ),
                        );
                    }
                    "sdk" => {
                        if let Some(inner) = event.get("event") {
                            if let Some(summary) = summarise_sdk_event(inner) {
                                append_log(app, state, run_id, "info", summary);
                            }
                        }
                    }
                    _ => {}
                }
            }
        } else {
            append_log(app, state, run_id, "debug", line);
        }
    }

    let status = child.wait().context("codex runner wait failed")?;
    let _ = stderr_thread.join();

    match final_status.as_deref() {
        Some("success") if status.success() => Ok(()),
        Some(other) => bail!("codex run ended with status {other}"),
        None if status.success() => Ok(()),
        None => bail!("codex runner exited with status {:?}", status.code()),
    }
}

fn locate_codex_runner() -> Result<PathBuf> {
    let manifest = Path::new(env!("CARGO_MANIFEST_DIR"));
    let candidate = manifest
        .parent()
        .ok_or_else(|| anyhow!("cannot find repo root"))?
        .join("codex-runner/dist/index.mjs");
    if !candidate.exists() {
        bail!(
            "codex-runner build missing at {}. Run `pnpm --dir codex-runner build`.",
            candidate.display()
        );
    }
    Ok(candidate)
}

fn summarise_sdk_event(event: &serde_json::Value) -> Option<String> {
    let event_type = event.get("type")?.as_str()?;
    match event_type {
        "item.started" | "item.completed" => {
            let item = event.get("item")?;
            let item_type = item.get("type").and_then(|v| v.as_str()).unwrap_or("item");
            let text = item
                .get("text")
                .and_then(|v| v.as_str())
                .or_else(|| item.get("summary").and_then(|v| v.as_str()))
                .unwrap_or("");
            let snippet = text.chars().take(160).collect::<String>();
            if snippet.is_empty() {
                Some(format!("[{event_type}] {item_type}"))
            } else {
                Some(format!("[{item_type}] {snippet}"))
            }
        }
        "turn.completed" => Some("Codex turn completed.".to_string()),
        "turn.failed" => {
            let reason = event
                .get("error")
                .and_then(|v| v.get("message"))
                .and_then(|v| v.as_str())
                .unwrap_or("unknown failure");
            Some(format!("Codex turn failed: {reason}"))
        }
        "error" => {
            let message = event
                .get("message")
                .and_then(|v| v.as_str())
                .unwrap_or("codex error");
            Some(format!("Codex error: {message}"))
        }
        _ => None,
    }
}

fn summarise_diff(preview_path: &Path) -> Result<(Vec<String>, Vec<String>)> {
    let _ = git_run(preview_path, &["add", "-A"]);
    let changed = git_lines(
        preview_path,
        &["diff", "--cached", "--name-only"],
    )?;
    let locked: Vec<String> = CUSTOMISE_LOCKED_PATHS.iter().map(|s| s.to_string()).collect();
    let violations: Vec<String> = changed
        .iter()
        .filter(|path| matches_locked_path(path, &locked))
        .cloned()
        .collect();
    Ok((changed, violations))
}

pub fn approve_customise_run_impl(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
) -> Result<CustomiseStatus> {
    let (run_id, preview_path, repo_path, runtime_root, violations) = {
        let guard = state.lock().map_err(|_| anyhow!("state unavailable"))?;
        let session = guard
            .preview
            .as_ref()
            .ok_or_else(|| anyhow!("no customise run is active"))?;
        if !matches!(session.state, CustomiseState::ReadyForReview) {
            bail!("run is not ready for review yet");
        }
        let repo_path = guard
            .runtime
            .repo_path
            .clone()
            .ok_or_else(|| anyhow!("runtime repo missing"))?;
        let runtime_root = guard
            .runtime
            .runtime_root
            .clone()
            .ok_or_else(|| anyhow!("runtime root missing"))?;
        (
            session.run_id.clone(),
            session.preview_path.clone(),
            repo_path,
            runtime_root,
            session.locked_violations.clone(),
        )
    };

    if !violations.is_empty() {
        bail!(
            "refusing to apply: locked paths were modified: {}",
            violations.join(", ")
        );
    }

    set_state(app, state, &run_id, CustomiseState::Applying);
    append_log(app, state, &run_id, "info", "Pausing live sidecar.".to_string());

    let live_sidecar_port = {
        let guard = state.lock().map_err(|_| anyhow!("state unavailable"))?;
        guard.runtime.sidecar_port
    };
    if let Some(port) = live_sidecar_port {
        let _ = crate::util::http_request_body(port, "/runs/pause", "POST");
    }

    let patch_result = apply_patch_to_live(&preview_path, &repo_path);
    match patch_result {
        Ok(_) => {
            append_log(app, state, &run_id, "info", "Patch applied; running installers.".to_string());
            if let Err(error) = run_checked(repo_path.as_path(), "uv", ["sync", "--project", "python-sidecar"])
            {
                append_log(app, state, &run_id, "warn", format!("uv sync failed: {error}"));
            }
            if let Err(error) = run_checked(repo_path.as_path(), "pnpm", ["install", "--dir", "web"]) {
                append_log(app, state, &run_id, "warn", format!("pnpm install failed: {error}"));
            }

            append_log(app, state, &run_id, "info", "Hot-swapping live sidecar.".to_string());
            let swap_result =
                crate::hot_swap_sidecar(app, state, &repo_path, &runtime_root);
            match swap_result {
                Ok(_) => {
                    append_log(app, state, &run_id, "info", "Swap complete; committing.".to_string());
                    let commit_message = format!("Customise apply {run_id}");
                    let _ = git_run(&repo_path, &["add", "-A"]);
                    let _ = git_run(&repo_path, &["commit", "-m", &commit_message]);
                    finalise_success(app, state, &run_id);
                }
                Err(error) => {
                    append_log(
                        app,
                        state,
                        &run_id,
                        "error",
                        format!("Hot-swap failed, rolling back: {error}"),
                    );
                    let _ = git_run(&repo_path, &["reset", "--hard", "HEAD"]);
                    let _ = crate::hot_swap_sidecar(app, state, &repo_path, &runtime_root);
                    mark_failed(app, state, &run_id, format!("apply failed: {error}"));
                }
            }
        }
        Err(error) => {
            append_log(
                app,
                state,
                &run_id,
                "error",
                format!("apply failed before swap: {error}"),
            );
            let _ = git_run(&repo_path, &["reset", "--hard", "HEAD"]);
            mark_failed(app, state, &run_id, format!("apply failed: {error}"));
        }
    }

    if let Some(port) = live_sidecar_port {
        let _ = crate::util::http_request_body(port, "/runs/resume", "POST");
    }

    get_customise_status_impl(state).map(|opt| opt.unwrap_or_else(|| empty_status(&run_id)))
}

fn apply_patch_to_live(preview_path: &Path, repo_path: &Path) -> Result<()> {
    let output = Command::new("git")
        .current_dir(preview_path)
        .args(["diff", "--cached", "--binary"])
        .output()
        .context("failed to invoke `git diff --cached --binary` in preview")?;
    if !output.status.success() {
        let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
        bail!(
            "`git diff` failed in preview: {}",
            if detail.is_empty() { "unknown error".into() } else { detail }
        );
    }
    if output.stdout.is_empty() {
        bail!("preview has no staged changes to apply");
    }
    let patch_path = repo_path.join(".sandflow-apply.patch");
    fs::write(&patch_path, &output.stdout)?;
    let result = run_checked(
        repo_path,
        "git",
        ["apply", "--whitespace=nowarn", patch_path.to_str().unwrap()],
    );
    let _ = fs::remove_file(&patch_path);
    result
}

pub fn discard_customise_run_impl(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
) -> Result<()> {
    let preview_opt = {
        let mut guard = state.lock().map_err(|_| anyhow!("state unavailable"))?;
        guard.preview.take()
    };
    let Some(mut session) = preview_opt else {
        return Ok(());
    };
    terminate_session(&mut session);
    if session.preview_path.exists() {
        let _ = fs::remove_dir_all(&session.preview_path);
    }
    let _ = app.emit("customise-run-updated", serde_json::json!({ "cleared": true }));
    Ok(())
}

fn finalise_success(app: &AppHandle, state: &State<'_, Mutex<DesktopState>>, run_id: &str) {
    let preview_opt = {
        let mut guard = match state.lock() {
            Ok(g) => g,
            Err(_) => return,
        };
        if guard.preview.as_ref().map(|s| s.run_id.as_str()) != Some(run_id) {
            return;
        }
        let mut session = guard.preview.take().unwrap();
        session.state = CustomiseState::Applied;
        let final_status = session.to_status();
        let final_preview = Some(session);
        let _ = app.emit("customise-run-updated", &final_status);
        final_preview
    };
    if let Some(mut session) = preview_opt {
        terminate_session(&mut session);
        if session.preview_path.exists() {
            let _ = fs::remove_dir_all(&session.preview_path);
        }
    }
}

fn terminate_session(session: &mut PreviewSession) {
    if let Some(mut child) = session.codex_child.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    if let Some(mut child) = session.preview_web_child.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    if let Some(mut child) = session.preview_sidecar_child.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn mark_failed(app: &AppHandle, state: &State<'_, Mutex<DesktopState>>, run_id: &str, message: String) {
    {
        let mut guard = match state.lock() {
            Ok(g) => g,
            Err(_) => return,
        };
        if let Some(session) = guard.preview.as_mut() {
            if session.run_id == run_id {
                session.state = CustomiseState::Failed;
                session.error = Some(message.clone());
                session.log.push(log_entry("error", message));
            }
        }
    }
    emit_status(app, state);
}

fn set_state(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    run_id: &str,
    next: CustomiseState,
) {
    eprintln!("[customise {run_id}] state -> {:?}", state_label(&next));
    {
        let mut guard = match state.lock() {
            Ok(g) => g,
            Err(_) => return,
        };
        if let Some(session) = guard.preview.as_mut() {
            if session.run_id == run_id {
                session.state = next;
            }
        }
    }
    emit_status(app, state);
}

fn state_label(state: &CustomiseState) -> &'static str {
    match state {
        CustomiseState::Cloning => "cloning",
        CustomiseState::Generating => "generating",
        CustomiseState::ReadyForReview => "ready_for_review",
        CustomiseState::Applying => "applying",
        CustomiseState::Applied => "applied",
        CustomiseState::Failed => "failed",
        CustomiseState::Cancelled => "cancelled",
    }
}

fn append_log(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    run_id: &str,
    level: &str,
    message: String,
) {
    eprintln!("[customise {run_id}] [{level}] {message}");
    let entry = log_entry(level, message);
    {
        let mut guard = match state.lock() {
            Ok(g) => g,
            Err(_) => return,
        };
        if let Some(session) = guard.preview.as_mut() {
            if session.run_id == run_id {
                session.log.push(entry.clone());
            }
        }
    }
    let _ = app.emit("customise-log", &entry);
}

fn log_entry(level: &str, message: String) -> CustomiseLogEntry {
    CustomiseLogEntry {
        ts: unix_timestamp(),
        level: level.to_string(),
        message,
    }
}

fn emit_status(app: &AppHandle, state: &State<'_, Mutex<DesktopState>>) {
    if let Ok(Some(status)) = get_customise_status_impl(state) {
        let _ = app.emit("customise-run-updated", &status);
    }
}

fn empty_status(run_id: &str) -> CustomiseStatus {
    CustomiseStatus {
        run_id: run_id.to_string(),
        prompt: String::new(),
        preview_path: String::new(),
        preview_sidecar_url: None,
        preview_web_url: None,
        state: CustomiseState::Cancelled,
        started_at: unix_timestamp(),
        log: Vec::new(),
        changed_paths: Vec::new(),
        locked_violations: Vec::new(),
        error: None,
    }
}

fn uuid_like() -> String {
    use std::time::SystemTime;
    let now = SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("{now:x}")
}
