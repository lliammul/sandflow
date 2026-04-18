use std::collections::HashMap;
use std::fs;
use std::io::{BufRead, BufReader};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{anyhow, bail, Context, Result};
use keyring::Entry;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, State};

const KEYRING_SERVICE: &str = "com.sandflow.desktop";
const KEYRING_USER: &str = "openai_api_key";

#[derive(Default)]
struct DesktopState {
    runtime: RuntimeState,
}

#[derive(Default)]
struct RuntimeState {
    repo_path: Option<PathBuf>,
    runtime_root: Option<PathBuf>,
    sidecar_port: Option<u16>,
    sidecar_child: Option<Child>,
    #[allow(dead_code)]
    web_child: Option<Child>,
    previews: HashMap<String, PreviewRun>,
}

#[derive(Clone)]
struct PreviewRun {
    run_id: String,
    prompt: String,
    base_commit: String,
    diff: String,
    changed_paths: Vec<String>,
    allowed: bool,
    error: Option<String>,
    worktree_path: PathBuf,
}

#[derive(Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
struct RuntimeConfig {
    open_ai_base_url: String,
    sandbox_model: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeStatus {
    bootstrapped: bool,
    repo_path: Option<String>,
    sidecar_port: Option<u16>,
    sidecar_base_url: Option<String>,
    needs_setup: bool,
    docker_available: bool,
    config: RuntimeConfig,
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct BootstrapPayload {
    open_ai_api_key: String,
    open_ai_base_url: String,
    sandbox_model: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct CustomiseLogEvent {
    run_id: String,
    phase: String,
    message: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct CustomisePreview {
    run_id: String,
    prompt: String,
    base_commit: String,
    diff: String,
    changed_paths: Vec<String>,
    allowed: bool,
    error: Option<String>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct CustomiseHistoryEntry {
    sha: String,
    subject: String,
    committed_at: String,
}

#[tauri::command]
fn get_runtime_status(app: AppHandle, state: State<'_, Mutex<DesktopState>>) -> Result<RuntimeStatus, String> {
    load_runtime_status(&app, &state).map_err(|error| error.to_string())
}

#[tauri::command]
fn bootstrap_runtime(
    app: AppHandle,
    state: State<'_, Mutex<DesktopState>>,
    payload: BootstrapPayload,
) -> Result<RuntimeStatus, String> {
    bootstrap_runtime_impl(&app, &state, payload).map_err(|error| error.to_string())
}

#[tauri::command]
fn open_repo_in_editor(app: AppHandle, state: State<'_, Mutex<DesktopState>>) -> Result<(), String> {
    let repo_path = {
        let guard = state.lock().map_err(|_| "Runtime state is unavailable.".to_string())?;
        guard
            .runtime
            .repo_path
            .clone()
            .ok_or_else(|| "Runtime repo is not bootstrapped yet.".to_string())?
    };
    Command::new("open")
        .arg(repo_path)
        .status()
        .map_err(|error| error.to_string())?;
    let _ = app.emit(
        "customise-log",
        CustomiseLogEvent {
            run_id: "system".into(),
            phase: "editor".into(),
            message: "Opened the runtime repo in the default editor.".into(),
        },
    );
    Ok(())
}

#[tauri::command]
fn start_customise_run(
    app: AppHandle,
    state: State<'_, Mutex<DesktopState>>,
    prompt: String,
) -> Result<String, String> {
    start_customise_run_impl(&app, &state, prompt).map_err(|error| error.to_string())
}

#[tauri::command]
fn get_customise_preview(
    state: State<'_, Mutex<DesktopState>>,
    run_id: String,
) -> Result<CustomisePreview, String> {
    let guard = state.lock().map_err(|_| "Runtime state is unavailable.".to_string())?;
    let preview = guard
        .runtime
        .previews
        .get(&run_id)
        .cloned()
        .ok_or_else(|| "Customise preview not found.".to_string())?;
    Ok(preview.into())
}

#[tauri::command]
fn apply_customise_run(
    app: AppHandle,
    state: State<'_, Mutex<DesktopState>>,
    run_id: String,
) -> Result<CustomisePreview, String> {
    apply_customise_run_impl(&app, &state, &run_id).map_err(|error| error.to_string())
}

#[tauri::command]
fn discard_customise_run(
    app: AppHandle,
    state: State<'_, Mutex<DesktopState>>,
    run_id: String,
) -> Result<(), String> {
    discard_customise_run_impl(&app, &state, &run_id).map_err(|error| error.to_string())
}

#[tauri::command]
fn revert_custom_commit(
    app: AppHandle,
    state: State<'_, Mutex<DesktopState>>,
    commit_sha: String,
) -> Result<(), String> {
    revert_custom_commit_impl(&app, &state, &commit_sha).map_err(|error| error.to_string())
}

#[tauri::command]
fn reset_customisations(app: AppHandle, state: State<'_, Mutex<DesktopState>>) -> Result<(), String> {
    reset_customisations_impl(&app, &state).map_err(|error| error.to_string())
}

#[tauri::command]
fn get_customise_history(
    state: State<'_, Mutex<DesktopState>>,
) -> Result<Vec<CustomiseHistoryEntry>, String> {
    get_customise_history_impl(&state).map_err(|error| error.to_string())
}

fn bootstrap_runtime_impl(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    payload: BootstrapPayload,
) -> Result<RuntimeStatus> {
    let app_data_dir = app
        .path()
        .app_data_dir()
        .context("Failed to determine the app-data directory.")?;
    let runtime_root = app_data_dir.join("runtime");
    let logs_root = app_data_dir.join("logs");
    let customise_root = app_data_dir.join("customise");
    let repo_path = app_data_dir.join("repo");
    fs::create_dir_all(&runtime_root)?;
    fs::create_dir_all(&logs_root)?;
    fs::create_dir_all(&customise_root)?;

    save_runtime_config(&runtime_root, &payload)?;
    store_api_key(&payload.open_ai_api_key)?;

    if !docker_available() {
        bail!("Docker is not reachable. Start Docker Desktop or OrbStack and try again.");
    }

    if repo_needs_refresh(&repo_path) {
        if repo_path.exists() {
            emit_log(app, "bootstrap", "setup", "Existing runtime repo is stale; recreating it from the current seed.");
            fs::remove_dir_all(&repo_path)?;
        }
        emit_log(app, "bootstrap", "setup", "Cloning the writable seed repo into app-data.");
        clone_seed_repo(app, &repo_path)?;
    }
    ensure_custom_branch(&repo_path)?;

    emit_log(app, "bootstrap", "install", "Installing Python dependencies with uv.");
    run_checked(repo_path.as_path(), "uv", ["sync", "--project", "python-sidecar"])?;
    emit_log(app, "bootstrap", "install", "Installing web dependencies with npm.");
    run_checked(repo_path.as_path(), "npm", ["install", "--prefix", "web"])?;

    let sidecar_port = restart_sidecar(app, state, &repo_path, &runtime_root, &payload)?;

    let mut guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
    guard.runtime.repo_path = Some(repo_path.clone());
    guard.runtime.runtime_root = Some(runtime_root.clone());
    guard.runtime.sidecar_port = Some(sidecar_port);
    drop(guard);

    build_runtime_status(&repo_path, Some(sidecar_port), load_runtime_config(&runtime_root)?)
}

fn start_customise_run_impl(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    prompt: String,
) -> Result<String> {
    let (repo_path, runtime_root) = {
        let guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        (
            guard
                .runtime
                .repo_path
                .clone()
                .ok_or_else(|| anyhow!("Runtime repo is not bootstrapped yet."))?,
            guard
                .runtime
                .runtime_root
                .clone()
                .ok_or_else(|| anyhow!("Runtime directory is not ready."))?,
        )
    };

    let customise_root = runtime_root.parent().unwrap_or(runtime_root.as_path()).join("customise");
    fs::create_dir_all(&customise_root)?;

    let run_id = format!("customise_{}", unix_timestamp());
    let base_commit = git_output(&repo_path, ["rev-parse", "HEAD"])?;
    let worktree_path = customise_root.join(&run_id);
    emit_log(app, &run_id, "worktree", "Creating a temporary git worktree.");
    run_checked(
        repo_path.as_path(),
        "git",
        [
            "-C",
            repo_path.to_string_lossy().as_ref(),
            "worktree",
            "add",
            "--detach",
            worktree_path.to_string_lossy().as_ref(),
            base_commit.as_str(),
        ],
    )?;

    emit_log(app, &run_id, "codex", "Running Codex against the temporary worktree.");
    let config = load_runtime_config(&runtime_root)?;
    let api_key = load_api_key()?;
    let command_output = run_codex(app, &run_id, &worktree_path, &prompt, &config, &api_key)?;
    if !command_output.status.success() {
        emit_log(app, &run_id, "codex", "Codex exited with a non-zero status.");
    }

    let changed_paths = git_lines(worktree_path.as_path(), ["diff", "--name-only"])?;
    let diff = git_output(worktree_path.as_path(), ["diff", "--binary"])?;
    let denied = changed_paths.iter().any(|path| !path_allowed(path));
    let preview = PreviewRun {
        run_id: run_id.clone(),
        prompt,
        base_commit,
        diff,
        changed_paths,
        allowed: !denied && command_output.status.success(),
        error: if denied {
            Some("Codex touched one or more locked paths. The preview has been blocked.".into())
        } else if !command_output.status.success() {
            Some("Codex failed to complete successfully.".into())
        } else {
            None
        },
        worktree_path,
    };

    let mut guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
    guard.runtime.previews.insert(run_id.clone(), preview);
    Ok(run_id)
}

fn apply_customise_run_impl(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    run_id: &str,
) -> Result<CustomisePreview> {
    let (repo_path, runtime_root, preview) = {
        let guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        let preview = guard
            .runtime
            .previews
            .get(run_id)
            .cloned()
            .ok_or_else(|| anyhow!("Customise preview not found."))?;
        (
            guard
                .runtime
                .repo_path
                .clone()
                .ok_or_else(|| anyhow!("Runtime repo is not bootstrapped yet."))?,
            guard
                .runtime
                .runtime_root
                .clone()
                .ok_or_else(|| anyhow!("Runtime directory is not ready."))?,
            preview,
        )
    };

    if !preview.allowed {
        bail!(preview.error.unwrap_or_else(|| "This preview is blocked and cannot be applied.".into()));
    }
    let current_head = git_output(&repo_path, ["rev-parse", "HEAD"])?;
    if current_head != preview.base_commit {
        bail!("The live repo moved since the preview was created. Generate a fresh preview.");
    }

    emit_log(app, run_id, "apply", "Applying the approved patch to the live repo.");
    let patch_path = runtime_root.join(format!("{run_id}.patch"));
    fs::write(&patch_path, &preview.diff)?;
    if let Err(error) = run_checked(
        repo_path.as_path(),
        "git",
        [
            "-C",
            repo_path.to_string_lossy().as_ref(),
            "apply",
            "--3way",
            patch_path.to_string_lossy().as_ref(),
        ],
    ) {
        cleanup_preview_worktree(&repo_path, &preview.worktree_path).ok();
        bail!(error);
    }

    if preview.changed_paths.iter().any(|path| path == "python-sidecar/pyproject.toml") {
        emit_log(app, run_id, "install", "Refreshing Python dependencies with uv.");
        run_checked(repo_path.as_path(), "uv", ["sync", "--project", "python-sidecar"])?;
    }
    if preview.changed_paths.iter().any(|path| path == "web/package.json") {
        emit_log(app, run_id, "install", "Refreshing web dependencies with npm.");
        run_checked(repo_path.as_path(), "npm", ["install", "--prefix", "web"])?;
    }
    if preview.changed_paths.iter().any(|path| path.starts_with("python-sidecar/")) {
        emit_log(app, run_id, "restart", "Restarting the Python sidecar.");
        restart_sidecar_from_state(app, state, &repo_path, &runtime_root)?;
    }
    wait_for_health(state)?;

    emit_log(app, run_id, "git", "Creating a custom branch commit.");
    run_checked(repo_path.as_path(), "git", ["-C", repo_path.to_string_lossy().as_ref(), "add", "-A"])?;
    let commit_message = truncate_commit_message(&preview.prompt);
    if let Err(error) = run_checked(
        repo_path.as_path(),
        "git",
        [
            "-C",
            repo_path.to_string_lossy().as_ref(),
            "commit",
            "-m",
            commit_message.as_str(),
        ],
    ) {
        emit_log(app, run_id, "revert", "Commit failed; resetting the live repo to the preview base commit.");
        run_checked(
            repo_path.as_path(),
            "git",
            ["-C", repo_path.to_string_lossy().as_ref(), "reset", "--hard", preview.base_commit.as_str()],
        )?;
        return Err(error);
    }

    cleanup_preview_worktree(&repo_path, &preview.worktree_path)?;
    let mut guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
    let preview = guard
        .runtime
        .previews
        .remove(run_id)
        .ok_or_else(|| anyhow!("Customise preview disappeared before apply finished."))?;
    Ok(preview.into())
}

fn discard_customise_run_impl(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    run_id: &str,
) -> Result<()> {
    let (repo_path, worktree_path) = {
        let mut guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        let repo_path = guard
            .runtime
            .repo_path
            .clone()
            .ok_or_else(|| anyhow!("Runtime repo is not bootstrapped yet."))?;
        let preview = guard
            .runtime
            .previews
            .remove(run_id)
            .ok_or_else(|| anyhow!("Customise preview not found."))?;
        (repo_path, preview.worktree_path)
    };
    emit_log(app, run_id, "discard", "Removing the temporary worktree without applying changes.");
    cleanup_preview_worktree(&repo_path, &worktree_path)
}

fn revert_custom_commit_impl(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    commit_sha: &str,
) -> Result<()> {
    let (repo_path, runtime_root) = runtime_paths(state)?;
    emit_log(app, commit_sha, "revert", "Reverting the selected custom commit.");
    run_checked(
        repo_path.as_path(),
        "git",
        ["-C", repo_path.to_string_lossy().as_ref(), "revert", "--no-edit", commit_sha],
    )?;
    restart_sidecar_from_state(app, state, &repo_path, &runtime_root)?;
    wait_for_health(state)?;
    Ok(())
}

fn reset_customisations_impl(app: &AppHandle, state: &State<'_, Mutex<DesktopState>>) -> Result<()> {
    let (repo_path, runtime_root) = runtime_paths(state)?;
    emit_log(app, "system", "reset", "Resetting the custom branch back to local main.");
    run_checked(repo_path.as_path(), "git", ["-C", repo_path.to_string_lossy().as_ref(), "checkout", "custom"])?;
    run_checked(
        repo_path.as_path(),
        "git",
        ["-C", repo_path.to_string_lossy().as_ref(), "reset", "--hard", "main"],
    )?;
    run_checked(repo_path.as_path(), "git", ["-C", repo_path.to_string_lossy().as_ref(), "clean", "-fd"])?;
    restart_sidecar_from_state(app, state, &repo_path, &runtime_root)?;
    wait_for_health(state)?;
    Ok(())
}

fn get_customise_history_impl(state: &State<'_, Mutex<DesktopState>>) -> Result<Vec<CustomiseHistoryEntry>> {
    let guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
    let repo_path = guard
        .runtime
        .repo_path
        .clone()
        .ok_or_else(|| anyhow!("Runtime repo is not bootstrapped yet."))?;
    let output = git_output(
        &repo_path,
        ["log", "custom", "--pretty=format:%H\t%s\t%cI", "-n", "30"],
    )?;
    Ok(output
        .lines()
        .filter_map(|line| {
            let mut parts = line.splitn(3, '\t');
            Some(CustomiseHistoryEntry {
                sha: parts.next()?.to_string(),
                subject: parts.next()?.to_string(),
                committed_at: parts.next()?.to_string(),
            })
        })
        .collect())
}

fn load_runtime_status(app: &AppHandle, state: &State<'_, Mutex<DesktopState>>) -> Result<RuntimeStatus> {
    let app_data_dir = app.path().app_data_dir()?;
    let runtime_root = app_data_dir.join("runtime");
    let repo_path = app_data_dir.join("repo");
    let config = load_runtime_config(&runtime_root).unwrap_or_default();
    let bootstrapped = repo_path.exists();
    let docker = docker_available();
    let sidecar_port = {
        let mut guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        guard.runtime.repo_path.get_or_insert(repo_path.clone());
        guard.runtime.runtime_root.get_or_insert(runtime_root.clone());
        guard.runtime.sidecar_port
    };
    build_runtime_status(&repo_path, sidecar_port, config).map(|mut status| {
        status.docker_available = docker;
        status.needs_setup = !bootstrapped || !docker || load_api_key().is_err() || status.config.sandbox_model.is_empty();
        status
    })
}

fn build_runtime_status(repo_path: &Path, sidecar_port: Option<u16>, config: RuntimeConfig) -> Result<RuntimeStatus> {
    let bootstrapped = repo_path.exists();
    Ok(RuntimeStatus {
        bootstrapped,
        repo_path: bootstrapped.then(|| repo_path.display().to_string()),
        sidecar_port,
        sidecar_base_url: sidecar_port.map(|port| format!("http://127.0.0.1:{port}")),
        needs_setup: !bootstrapped || load_api_key().is_err() || config.sandbox_model.is_empty(),
        docker_available: docker_available(),
        config,
    })
}

fn save_runtime_config(runtime_root: &Path, payload: &BootstrapPayload) -> Result<()> {
    let config = RuntimeConfig {
        open_ai_base_url: payload.open_ai_base_url.clone(),
        sandbox_model: payload.sandbox_model.clone(),
    };
    fs::write(
        runtime_root.join("config.json"),
        serde_json::to_vec_pretty(&config)?,
    )?;
    Ok(())
}

fn load_runtime_config(runtime_root: &Path) -> Result<RuntimeConfig> {
    let config_path = runtime_root.join("config.json");
    if !config_path.exists() {
        return Ok(RuntimeConfig::default());
    }
    Ok(serde_json::from_slice(&fs::read(config_path)?)?)
}

fn store_api_key(value: &str) -> Result<()> {
    let entry = Entry::new(KEYRING_SERVICE, KEYRING_USER)?;
    entry.set_password(value)?;
    Ok(())
}

fn load_api_key() -> Result<String> {
    let entry = Entry::new(KEYRING_SERVICE, KEYRING_USER)?;
    Ok(entry.get_password()?)
}

fn clone_seed_repo(app: &AppHandle, repo_path: &Path) -> Result<()> {
    let source = std::env::var("SANDFLOW_SEED_REPO")
        .ok()
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .map(Path::to_path_buf)
                .expect("src-tauri must live inside the repo root")
        });
    if !source.join(".git").exists() {
        bail!("Seed repo source `{}` is not a git repository.", source.display());
    }
    emit_log(
        app,
        "bootstrap",
        "setup",
        &format!("Copying the current working tree from `{}` into app-data.", source.display()),
    );
    run_checked(
        source.as_path(),
        "rsync",
        [
            "-a",
            "--delete",
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
            &format!("{}/", source.display()),
            repo_path.to_string_lossy().as_ref(),
        ],
    )?;
    run_checked(repo_path, "git", ["init", "-b", "main"])?;
    run_checked(
        repo_path,
        "git",
        ["config", "user.email", "sandflow@local.invalid"],
    )?;
    run_checked(
        repo_path,
        "git",
        ["config", "user.name", "Sandflow Desktop"],
    )?;
    run_checked(repo_path, "git", ["add", "-A"])?;
    run_checked(
        repo_path,
        "git",
        ["commit", "-m", "Initial Sandflow desktop seed"],
    )?;
    Ok(())
}

fn repo_needs_refresh(repo_path: &Path) -> bool {
    if !repo_path.exists() {
        return true;
    }
    if !repo_path.join(".git").exists() {
        return true;
    }
    if !repo_path.join("web/package.json").exists() {
        return true;
    }
    if !repo_path.join("python-sidecar/pyproject.toml").exists() {
        return true;
    }
    false
}

fn ensure_custom_branch(repo_path: &Path) -> Result<()> {
    run_checked(repo_path, "git", ["-C", repo_path.to_string_lossy().as_ref(), "checkout", "-B", "main"])?;
    let _ = run_checked(repo_path, "git", ["-C", repo_path.to_string_lossy().as_ref(), "branch", "-D", "custom"]);
    run_checked(repo_path, "git", ["-C", repo_path.to_string_lossy().as_ref(), "checkout", "-B", "custom", "main"])?;
    let _ = run_checked(
        repo_path,
        "git",
        [
            "-C",
            repo_path.to_string_lossy().as_ref(),
            "config",
            "user.email",
            "sandflow@local.invalid",
        ],
    );
    let _ = run_checked(
        repo_path,
        "git",
        ["-C", repo_path.to_string_lossy().as_ref(), "config", "user.name", "Sandflow Desktop"],
    );
    Ok(())
}

fn restart_sidecar(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    repo_path: &Path,
    runtime_root: &Path,
    payload: &BootstrapPayload,
) -> Result<u16> {
    let config = RuntimeConfig {
        open_ai_base_url: payload.open_ai_base_url.clone(),
        sandbox_model: payload.sandbox_model.clone(),
    };
    restart_sidecar_with_config(app, state, repo_path, runtime_root, &config)
}

fn restart_sidecar_from_state(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    repo_path: &Path,
    runtime_root: &Path,
) -> Result<u16> {
    let config = load_runtime_config(runtime_root)?;
    restart_sidecar_with_config(app, state, repo_path, runtime_root, &config)
}

fn restart_sidecar_with_config(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    repo_path: &Path,
    runtime_root: &Path,
    config: &RuntimeConfig,
) -> Result<u16> {
    let port = pick_port()?;
    let port_file = runtime_root.join("sidecar-port.txt");
    let log_path = runtime_root.parent().unwrap_or(runtime_root).join("logs/sidecar.log");
    let api_key = load_api_key()?;

    {
        let mut guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        if let Some(mut child) = guard.runtime.sidecar_child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    let stdout = fs::OpenOptions::new().create(true).append(true).open(&log_path)?;
    let stderr = fs::OpenOptions::new().create(true).append(true).open(&log_path)?;
    emit_log(app, "system", "sidecar", &format!("Starting the Python sidecar on port {port}."));
    let child = Command::new("uv")
        .current_dir(repo_path)
        .env("OPENAI_API_KEY", api_key)
        .env("OPENAI_API_BASE", &config.open_ai_base_url)
        .env("OPENAI_SANDBOX_MODEL", &config.sandbox_model)
        .arg("run")
        .arg("--project")
        .arg("python-sidecar")
        .arg("python")
        .arg("-m")
        .arg("sandflow_sidecar")
        .arg("--port")
        .arg(port.to_string())
        .arg("--port-file")
        .arg(port_file)
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()
        .context("Failed to start the Python sidecar.")?;

    {
        let mut guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        guard.runtime.sidecar_child = Some(child);
        guard.runtime.sidecar_port = Some(port);
    }

    wait_for_health(state)?;
    Ok(port)
}

fn wait_for_health(state: &State<'_, Mutex<DesktopState>>) -> Result<()> {
    let port = {
        let guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        guard
            .runtime
            .sidecar_port
            .ok_or_else(|| anyhow!("Sidecar port is not configured."))?
    };
    let url = format!("http://127.0.0.1:{port}/health");
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(15) {
        let output = Command::new("curl")
            .arg("-fsS")
            .arg(url.as_str())
            .output();
        if let Ok(output) = output {
            if output.status.success() {
                return Ok(());
            }
        }
        thread::sleep(Duration::from_millis(350));
    }
    bail!("Timed out waiting for the Python sidecar health check.")
}

fn runtime_paths(state: &State<'_, Mutex<DesktopState>>) -> Result<(PathBuf, PathBuf)> {
    let guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
    Ok((
        guard
            .runtime
            .repo_path
            .clone()
            .ok_or_else(|| anyhow!("Runtime repo is not bootstrapped yet."))?,
        guard
            .runtime
            .runtime_root
            .clone()
            .ok_or_else(|| anyhow!("Runtime directory is not ready."))?,
    ))
}

fn run_codex(
    app: &AppHandle,
    run_id: &str,
    worktree_path: &Path,
    prompt: &str,
    config: &RuntimeConfig,
    api_key: &str,
) -> Result<std::process::Output> {
    let mut child = Command::new("codex")
        .current_dir(worktree_path)
        .env("OPENAI_API_KEY", api_key)
        .env("OPENAI_API_BASE", &config.open_ai_base_url)
        .env("OPENAI_SANDBOX_MODEL", &config.sandbox_model)
        .arg("exec")
        .arg("--json")
        .arg("--cd")
        .arg(worktree_path)
        .arg("--ask-for-approval")
        .arg("never")
        .arg("--sandbox")
        .arg("workspace-write")
        .arg("--")
        .arg(prompt)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .context("Failed to launch Codex.")?;

    let stdout = child.stdout.take().ok_or_else(|| anyhow!("Codex stdout was unavailable."))?;
    let stderr = child.stderr.take().ok_or_else(|| anyhow!("Codex stderr was unavailable."))?;
    let app_stdout = app.clone();
    let app_stderr = app.clone();
    let run_id_out = run_id.to_string();
    let run_id_err = run_id.to_string();

    let stdout_thread = thread::spawn(move || -> Result<()> {
        for line in BufReader::new(stdout).lines() {
            let line = line?;
            if !line.trim().is_empty() {
                emit_log(&app_stdout, &run_id_out, "codex", &line);
            }
        }
        Ok(())
    });
    let stderr_thread = thread::spawn(move || -> Result<()> {
        for line in BufReader::new(stderr).lines() {
            let line = line?;
            if !line.trim().is_empty() {
                emit_log(&app_stderr, &run_id_err, "codex", &line);
            }
        }
        Ok(())
    });

    let status = child.wait()?;
    stdout_thread.join().map_err(|_| anyhow!("Codex stdout thread panicked."))??;
    stderr_thread.join().map_err(|_| anyhow!("Codex stderr thread panicked."))??;

    Ok(std::process::Output {
        status,
        stdout: Vec::new(),
        stderr: Vec::new(),
    })
}

fn cleanup_preview_worktree(repo_path: &Path, worktree_path: &Path) -> Result<()> {
    let _ = run_checked(
        repo_path,
        "git",
        [
            "-C",
            repo_path.to_string_lossy().as_ref(),
            "worktree",
            "remove",
            "--force",
            worktree_path.to_string_lossy().as_ref(),
        ],
    );
    if worktree_path.exists() {
        fs::remove_dir_all(worktree_path)?;
    }
    Ok(())
}

fn docker_available() -> bool {
    Command::new("docker")
        .arg("info")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn git_output<const N: usize>(repo_path: &Path, args: [&str; N]) -> Result<String> {
    let output = Command::new("git")
        .current_dir(repo_path)
        .args(args)
        .output()
        .context("Failed to invoke git.")?;
    ensure_success("git", args.as_slice(), &output.status, &output.stderr)?;
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn git_lines<const N: usize>(repo_path: &Path, args: [&str; N]) -> Result<Vec<String>> {
    Ok(git_output(repo_path, args)?
        .lines()
        .map(|line| line.trim().to_string())
        .filter(|line| !line.is_empty())
        .collect())
}

fn run_checked<const N: usize>(cwd: &Path, command: &str, args: [&str; N]) -> Result<()> {
    let output = Command::new(command)
        .current_dir(cwd)
        .args(args)
        .output()
        .with_context(|| format!("Failed to invoke `{command}`."))?;
    ensure_success(command, args.as_slice(), &output.status, &output.stderr)
}

fn ensure_success(command: &str, args: &[&str], status: &ExitStatus, stderr: &[u8]) -> Result<()> {
    if status.success() {
        return Ok(());
    }
    let detail = String::from_utf8_lossy(stderr).trim().to_string();
    bail!(
        "`{command} {}` failed: {}",
        args.join(" "),
        if detail.is_empty() { "unknown error".into() } else { detail }
    )
}

fn path_allowed(path: &str) -> bool {
    if path.starts_with("src-tauri/") {
        return false;
    }
    if path == "python-sidecar/src/sandflow_sidecar/contract.py" {
        return false;
    }
    if path == ".env" || path.contains("secret") || path.ends_with(".key") || path.ends_with(".pem") {
        return false;
    }
    path == "AGENTS.md"
        || path == "python-sidecar/pyproject.toml"
        || path == "web/package.json"
        || path.starts_with("web/")
        || path.starts_with("python-sidecar/")
}

fn pick_port() -> Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

fn truncate_commit_message(prompt: &str) -> String {
    let trimmed = prompt.trim();
    let shortened = trimmed.chars().take(72).collect::<String>();
    format!("Customise: {shortened}")
}

fn unix_timestamp() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0)
}

fn emit_log(app: &AppHandle, run_id: &str, phase: &str, message: &str) {
    let _ = app.emit(
        "customise-log",
        CustomiseLogEvent {
            run_id: run_id.to_string(),
            phase: phase.to_string(),
            message: message.to_string(),
        },
    );
}

impl From<PreviewRun> for CustomisePreview {
    fn from(value: PreviewRun) -> Self {
        Self {
            run_id: value.run_id,
            prompt: value.prompt,
            base_commit: value.base_commit,
            diff: value.diff,
            changed_paths: value.changed_paths,
            allowed: value.allowed,
            error: value.error,
        }
    }
}

pub fn run() {
    tauri::Builder::default()
        .manage(Mutex::new(DesktopState::default()))
        .setup(|app| {
            let handle = app.handle().clone();
            let state = app.state::<Mutex<DesktopState>>();
            if let Ok(status) = load_runtime_status(&handle, &state) {
                if status.bootstrapped && !status.needs_setup {
                    if let Some(repo_path) = status.repo_path.clone().map(PathBuf::from) {
                        let app_data_dir = handle.path().app_data_dir()?;
                        let runtime_root = app_data_dir.join("runtime");
                        let _ = restart_sidecar_from_state(&handle, &state, &repo_path, &runtime_root);
                    }
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            bootstrap_runtime,
            discard_customise_run,
            get_customise_history,
            get_customise_preview,
            get_runtime_status,
            open_repo_in_editor,
            apply_customise_run,
            reset_customisations,
            revert_custom_commit,
            start_customise_run,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
