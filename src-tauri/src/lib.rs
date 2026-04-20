use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{anyhow, bail, Context, Result};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, State};

pub mod customise;
pub mod util;

pub const CUSTOMISE_LOCKED_PATHS: &[&str] = &[
    "src-tauri/**",
    "codex-runner/**",
    "python-sidecar/src/sandflow_sidecar/contract.py",
    ".git/**",
    ".env",
    ".env.*",
    "*secret*",
    "*.key",
    "*.pem",
    "previews/**",
    ".context/**",
    ".conductor/**",
];

#[derive(Default)]
pub struct DesktopState {
    pub runtime: RuntimeState,
    pub preview: Option<customise::PreviewSession>,
}

#[derive(Default)]
pub struct RuntimeState {
    pub repo_path: Option<PathBuf>,
    pub runtime_root: Option<PathBuf>,
    pub sidecar_port: Option<u16>,
    pub sidecar_child: Option<Child>,
    pub cached_api_key: Option<String>,
    pub swap_in_progress: bool,
}

#[derive(Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeConfig {
    pub open_ai_api_key: String,
    pub open_ai_base_url: String,
    pub sandbox_model: String,
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
fn save_artifact_to_downloads(
    app: AppHandle,
    state: State<'_, Mutex<DesktopState>>,
    stored_path: String,
    filename: String,
) -> Result<String, String> {
    save_artifact_to_downloads_impl(&app, &state, &stored_path, &filename).map_err(|error| error.to_string())
}

#[tauri::command]
fn get_customise_status(
    state: State<'_, Mutex<DesktopState>>,
) -> Result<Option<customise::CustomiseStatus>, String> {
    customise::get_customise_status_impl(&state).map_err(|e| e.to_string())
}

#[tauri::command]
fn start_customise_run(
    app: AppHandle,
    state: State<'_, Mutex<DesktopState>>,
    payload: customise::StartCustomisePayload,
) -> Result<customise::CustomiseStatus, String> {
    customise::start_customise_run_impl(&app, &state, payload).map_err(|e| e.to_string())
}

#[tauri::command]
fn approve_customise_run(
    app: AppHandle,
    state: State<'_, Mutex<DesktopState>>,
) -> Result<customise::CustomiseStatus, String> {
    customise::approve_customise_run_impl(&app, &state).map_err(|e| e.to_string())
}

#[tauri::command]
fn discard_customise_run(
    app: AppHandle,
    state: State<'_, Mutex<DesktopState>>,
) -> Result<(), String> {
    customise::discard_customise_run_impl(&app, &state).map_err(|e| e.to_string())
}

#[tauri::command]
fn reveal_path_in_finder(path: String) -> Result<(), String> {
    Command::new("open")
        .arg("-R")
        .arg(path)
        .status()
        .map_err(|error| error.to_string())?;
    Ok(())
}

#[tauri::command]
fn open_external(url: String) -> Result<(), String> {
    if !(url.starts_with("http://127.0.0.1:") || url.starts_with("http://localhost:")) {
        return Err("only local preview URLs may be opened".into());
    }
    Command::new("open")
        .arg(url)
        .status()
        .map_err(|error| error.to_string())?;
    Ok(())
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
    let repo_path = app_data_dir.join("repo");
    fs::create_dir_all(&runtime_root)?;
    fs::create_dir_all(&logs_root)?;

    save_runtime_config(&runtime_root, &payload)?;
    {
        let mut guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        guard.runtime.cached_api_key = Some(payload.open_ai_api_key.clone());
    }

    if !docker_available() {
        bail!("Docker is not reachable. Start Docker Desktop or OrbStack and try again.");
    }

    if repo_needs_refresh(&repo_path) {
        if repo_path.exists() {
            fs::remove_dir_all(&repo_path)?;
        }
        clone_seed_repo(&repo_path)?;
    }

    run_checked(repo_path.as_path(), "uv", ["sync", "--project", "python-sidecar"])?;
    run_checked(repo_path.as_path(), "pnpm", ["install", "--dir", "web"])?;

    let sidecar_port = restart_sidecar(app, state, &repo_path, &runtime_root, &payload)?;

    let mut guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
    guard.runtime.repo_path = Some(repo_path.clone());
    guard.runtime.runtime_root = Some(runtime_root.clone());
    guard.runtime.sidecar_port = Some(sidecar_port);
    drop(guard);

    let has_api_key = {
        let guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        guard
            .runtime
            .cached_api_key
            .as_ref()
            .map(|value| !value.is_empty())
            .unwrap_or(false)
            || !load_runtime_config(&runtime_root)?.open_ai_api_key.is_empty()
    };

    build_runtime_status(
        &repo_path,
        Some(sidecar_port),
        load_runtime_config(&runtime_root)?,
        has_api_key,
    )
}

fn load_runtime_status(app: &AppHandle, state: &State<'_, Mutex<DesktopState>>) -> Result<RuntimeStatus> {
    let app_data_dir = app.path().app_data_dir()?;
    let runtime_root = app_data_dir.join("runtime");
    let repo_path = app_data_dir.join("repo");
    let config = load_runtime_config(&runtime_root).unwrap_or_default();
    let bootstrapped = repo_path.exists();
    let docker = docker_available();
    let (sidecar_port, has_api_key) = {
        let mut guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        guard.runtime.repo_path.get_or_insert(repo_path.clone());
        guard.runtime.runtime_root.get_or_insert(runtime_root.clone());
        if guard.runtime.cached_api_key.is_none() && !config.open_ai_api_key.is_empty() {
            guard.runtime.cached_api_key = Some(config.open_ai_api_key.clone());
        }
        (
            guard.runtime.sidecar_port,
            guard
                .runtime
                .cached_api_key
                .as_ref()
                .map(|value| !value.is_empty())
                .unwrap_or(false)
                || !config.open_ai_api_key.is_empty(),
        )
    };

    build_runtime_status(&repo_path, sidecar_port, config, has_api_key).map(|mut status| {
        status.docker_available = docker;
        status.needs_setup = !bootstrapped || !docker || !has_api_key || status.config.sandbox_model.is_empty();
        status
    })
}

fn build_runtime_status(
    repo_path: &Path,
    sidecar_port: Option<u16>,
    config: RuntimeConfig,
    has_api_key: bool,
) -> Result<RuntimeStatus> {
    let bootstrapped = repo_path.exists();
    Ok(RuntimeStatus {
        bootstrapped,
        repo_path: bootstrapped.then(|| repo_path.display().to_string()),
        sidecar_port,
        sidecar_base_url: sidecar_port.map(|port| format!("http://127.0.0.1:{port}")),
        needs_setup: !bootstrapped || !has_api_key || config.sandbox_model.is_empty(),
        docker_available: docker_available(),
        config,
    })
}

fn save_runtime_config(runtime_root: &Path, payload: &BootstrapPayload) -> Result<()> {
    let config = RuntimeConfig {
        open_ai_api_key: payload.open_ai_api_key.clone(),
        open_ai_base_url: payload.open_ai_base_url.clone(),
        sandbox_model: payload.sandbox_model.clone(),
    };
    fs::create_dir_all(runtime_root)?;
    fs::write(
        runtime_root.join("config.json"),
        serde_json::to_vec_pretty(&config)?,
    )?;
    Ok(())
}

pub fn load_runtime_config(runtime_root: &Path) -> Result<RuntimeConfig> {
    let config_path = runtime_root.join("config.json");
    if !config_path.exists() {
        return Ok(RuntimeConfig::default());
    }
    Ok(serde_json::from_slice(&fs::read(config_path)?)?)
}

fn clone_seed_repo(repo_path: &Path) -> Result<()> {
    let source = source_repo_root();
    if !source.join(".git").exists() {
        bail!("Seed repo source `{}` is not a git repository.", source.display());
    }
    if let Some(parent) = repo_path.parent() {
        fs::create_dir_all(parent)?;
    }
    run_checked(
        source.as_path(),
        "rsync",
        [
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
            &format!("{}/", source.display()),
            repo_path.to_string_lossy().as_ref(),
        ],
    )?;
    let copied_git_file = repo_path.join(".git");
    if copied_git_file.exists() {
        if copied_git_file.is_dir() {
            fs::remove_dir_all(&copied_git_file)?;
        } else {
            fs::remove_file(&copied_git_file)?;
        }
    }
    run_checked(repo_path, "git", ["init", "-b", "main"])?;
    run_checked(repo_path, "git", ["config", "user.email", "sandflow@local.invalid"])?;
    run_checked(repo_path, "git", ["config", "user.name", "Sandflow Desktop"])?;
    run_checked(repo_path, "git", ["add", "-A"])?;
    run_checked(repo_path, "git", ["commit", "-m", "Initial Sandflow desktop runtime"])?;
    Ok(())
}

fn source_repo_root() -> PathBuf {
    std::env::var("SANDFLOW_SEED_REPO")
        .ok()
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .map(Path::to_path_buf)
                .expect("src-tauri must live inside the repo root")
        })
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

fn restart_sidecar(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    repo_path: &Path,
    runtime_root: &Path,
    payload: &BootstrapPayload,
) -> Result<u16> {
    let config = RuntimeConfig {
        open_ai_api_key: payload.open_ai_api_key.clone(),
        open_ai_base_url: payload.open_ai_base_url.clone(),
        sandbox_model: payload.sandbox_model.clone(),
    };
    hot_swap_sidecar_with_config(
        app,
        state,
        repo_path,
        runtime_root,
        &config,
        Some(payload.open_ai_api_key.as_str()),
    )
}

pub fn hot_swap_sidecar(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    repo_path: &Path,
    runtime_root: &Path,
) -> Result<u16> {
    let config = load_runtime_config(runtime_root)?;
    hot_swap_sidecar_with_config(app, state, repo_path, runtime_root, &config, None)
}

fn hot_swap_sidecar_with_config(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    repo_path: &Path,
    runtime_root: &Path,
    config: &RuntimeConfig,
    api_key_override: Option<&str>,
) -> Result<u16> {
    let api_key = resolve_api_key(state, config, api_key_override)?;

    {
        let mut guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        if guard.runtime.swap_in_progress {
            bail!("A sidecar swap is already in progress; try again in a moment.");
        }
        guard.runtime.swap_in_progress = true;
    }

    let result = hot_swap_sidecar_inner(app, state, repo_path, runtime_root, config, &api_key);

    {
        let mut guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        guard.runtime.swap_in_progress = false;
    }

    result
}

fn hot_swap_sidecar_inner(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    repo_path: &Path,
    runtime_root: &Path,
    config: &RuntimeConfig,
    api_key: &str,
) -> Result<u16> {
    let (new_child, new_port) = spawn_sidecar_child(repo_path, runtime_root, config, api_key)?;
    let guard = ChildGuard::new(new_child);
    wait_for_ready(new_port, Duration::from_secs(30))?;
    let new_child = guard.defuse();

    let (old_child, old_port) = {
        let mut state_guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        let old_child = state_guard.runtime.sidecar_child.take();
        let old_port = state_guard.runtime.sidecar_port;
        state_guard.runtime.sidecar_child = Some(new_child);
        state_guard.runtime.sidecar_port = Some(new_port);
        (old_child, old_port)
    };

    emit_sidecar_changed(app, old_port, new_port);

    if let Some(old_child) = old_child {
        drain_old_sidecar(old_child, old_port);
    }

    Ok(new_port)
}

fn resolve_api_key(
    state: &State<'_, Mutex<DesktopState>>,
    config: &RuntimeConfig,
    api_key_override: Option<&str>,
) -> Result<String> {
    if let Some(value) = api_key_override {
        return Ok(value.to_string());
    }
    let cached = {
        let guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
        guard.runtime.cached_api_key.clone()
    };
    if let Some(value) = cached.filter(|v| !v.is_empty()) {
        return Ok(value);
    }
    if !config.open_ai_api_key.is_empty() {
        return Ok(config.open_ai_api_key.clone());
    }
    bail!("OpenAI API key is missing from runtime config.");
}

fn spawn_sidecar_child(
    repo_path: &Path,
    runtime_root: &Path,
    config: &RuntimeConfig,
    api_key: &str,
) -> Result<(Child, u16)> {
    let port = pick_port()?;
    let logs_root = runtime_root.parent().unwrap_or(runtime_root).join("logs");
    fs::create_dir_all(runtime_root)?;
    fs::create_dir_all(&logs_root)?;
    let port_file = runtime_root.join("sidecar-port.txt");
    let log_path = logs_root.join("sidecar.log");
    let stdout = fs::OpenOptions::new().create(true).append(true).open(&log_path)?;
    let stderr = fs::OpenOptions::new().create(true).append(true).open(&log_path)?;
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
    Ok((child, port))
}

struct ChildGuard {
    child: Option<Child>,
}

impl ChildGuard {
    fn new(child: Child) -> Self {
        Self { child: Some(child) }
    }

    fn defuse(mut self) -> Child {
        self.child.take().expect("child already taken")
    }
}

impl Drop for ChildGuard {
    fn drop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn drain_old_sidecar(mut child: Child, port: Option<u16>) {
    thread::spawn(move || {
        let pid = child.id();
        let start = Instant::now();
        let drain_limit = Duration::from_secs(300);
        if let Some(port) = port {
            loop {
                let runs = query_active_runs(port);
                if runs.is_empty() {
                    break;
                }
                if start.elapsed() >= drain_limit {
                    break;
                }
                thread::sleep(Duration::from_millis(750));
            }
        }
        #[cfg(unix)]
        {
            let _ = Command::new("kill").arg("-TERM").arg(pid.to_string()).status();
            thread::sleep(Duration::from_millis(500));
        }
        #[cfg(windows)]
        let _ = pid;
        if child.try_wait().ok().flatten().is_none() {
            let _ = child.kill();
        }
        let _ = child.wait();
    });
}

fn emit_sidecar_changed(app: &AppHandle, old_port: Option<u16>, new_port: u16) {
    let _ = app.emit(
        "sidecar-changed",
        serde_json::json!({
            "swapId": unix_timestamp(),
            "oldPort": old_port,
            "newPort": new_port,
            "baseUrl": format!("http://127.0.0.1:{new_port}"),
        }),
    );
}

fn health_probe(port: u16) -> Result<bool> {
    let mut stream = connect_local(port, Duration::from_millis(500))?;
    stream.set_read_timeout(Some(Duration::from_millis(750)))?;
    stream.set_write_timeout(Some(Duration::from_millis(500)))?;
    stream.write_all(b"GET /health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")?;
    let mut buf = [0u8; 64];
    let n = stream.read(&mut buf)?;
    Ok(buf[..n].starts_with(b"HTTP/1.1 200"))
}

fn ready_probe(port: u16) -> Result<bool> {
    let mut stream = connect_local(port, Duration::from_millis(500))?;
    stream.set_read_timeout(Some(Duration::from_millis(1500)))?;
    stream.set_write_timeout(Some(Duration::from_millis(500)))?;
    stream.write_all(b"GET /ready HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")?;
    let mut buf = [0u8; 128];
    let n = stream.read(&mut buf)?;
    Ok(buf[..n].starts_with(b"HTTP/1.1 200"))
}

fn wait_for_ready(port: u16, timeout: Duration) -> Result<()> {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if ready_probe(port).unwrap_or(false) {
            if health_probe(port).unwrap_or(false) {
                return Ok(());
            }
        }
        thread::sleep(Duration::from_millis(250));
    }
    bail!("Timed out waiting for the sidecar to become ready.")
}

fn query_active_runs(port: u16) -> Vec<String> {
    let Ok(mut stream) = connect_local(port, Duration::from_millis(500)) else {
        return Vec::new();
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(1500)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
    if stream
        .write_all(b"GET /runs/active HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return Vec::new();
    }
    let mut buf = Vec::new();
    if stream.read_to_end(&mut buf).is_err() {
        return Vec::new();
    }
    let text = String::from_utf8_lossy(&buf);
    let Some(body_start) = text.find("\r\n\r\n") else {
        return Vec::new();
    };
    let body = &text[body_start + 4..];
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|value| value.get("run_ids").cloned())
        .and_then(|value| value.as_array().cloned())
        .map(|items| {
            items
                .into_iter()
                .filter_map(|value| value.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default()
}

fn connect_local(port: u16, timeout: Duration) -> Result<TcpStream> {
    let addr = format!("127.0.0.1:{port}").parse::<std::net::SocketAddr>()?;
    Ok(TcpStream::connect_timeout(&addr, timeout)?)
}

fn save_artifact_to_downloads_impl(
    app: &AppHandle,
    state: &State<'_, Mutex<DesktopState>>,
    stored_path: &str,
    filename: &str,
) -> Result<String> {
    let guard = state.lock().map_err(|_| anyhow!("Runtime state is unavailable."))?;
    let repo_path = guard
        .runtime
        .repo_path
        .clone()
        .ok_or_else(|| anyhow!("Runtime repo is not bootstrapped yet."))?;
    drop(guard);

    let source = PathBuf::from(stored_path);
    if !source.exists() {
        bail!("Artifact file does not exist.");
    }

    let repo_root = repo_path.canonicalize()?;
    let source_path = source.canonicalize()?;
    if !source_path.starts_with(&repo_root) {
        bail!("Artifact path is outside the runtime repo.");
    }

    let downloads_dir = app
        .path()
        .download_dir()
        .or_else(|_| std::env::var("HOME").map(PathBuf::from).map(|home| home.join("Downloads")))
        .context("Failed to determine the Downloads directory.")?;
    fs::create_dir_all(&downloads_dir)?;

    let safe_name = if filename.trim().is_empty() {
        source_path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("artifact.bin")
            .to_string()
    } else {
        filename.to_string()
    };

    let destination = unique_destination_path(&downloads_dir, &safe_name);
    fs::copy(&source_path, &destination)?;
    Ok(destination.display().to_string())
}

fn unique_destination_path(downloads_dir: &Path, filename: &str) -> PathBuf {
    let candidate = downloads_dir.join(filename);
    if !candidate.exists() {
        return candidate;
    }

    let stem = Path::new(filename)
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("artifact");
    let extension = Path::new(filename)
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| format!(".{value}"))
        .unwrap_or_default();

    for index in 2..1000 {
        let candidate = downloads_dir.join(format!("{stem}-{index}{extension}"));
        if !candidate.exists() {
            return candidate;
        }
    }

    downloads_dir.join(format!("{stem}-copy{extension}"))
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

fn pick_port() -> Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

fn unix_timestamp() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0)
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
                        let _ = hot_swap_sidecar(&handle, &state, &repo_path, &runtime_root);
                    }
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            bootstrap_runtime,
            get_runtime_status,
            reveal_path_in_finder,
            open_external,
            save_artifact_to_downloads,
            get_customise_status,
            start_customise_run,
            approve_customise_run,
            discard_customise_run,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
