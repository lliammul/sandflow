use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::Path;
use std::process::{Command, ExitStatus, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{anyhow, bail, Context, Result};

pub fn pick_port() -> Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

pub fn unix_timestamp() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0)
}

pub fn run_checked<I, S>(cwd: &Path, command: &str, args: I) -> Result<()>
where
    I: IntoIterator<Item = S>,
    S: AsRef<std::ffi::OsStr>,
{
    let args: Vec<_> = args.into_iter().collect();
    let output = Command::new(command)
        .current_dir(cwd)
        .args(args.iter().map(|a| a.as_ref()))
        .output()
        .with_context(|| format!("Failed to invoke `{command}`."))?;
    ensure_success(command, &output.status, &output.stderr)
}

pub fn run_output<I, S>(cwd: &Path, command: &str, args: I) -> Result<String>
where
    I: IntoIterator<Item = S>,
    S: AsRef<std::ffi::OsStr>,
{
    let args: Vec<_> = args.into_iter().collect();
    let output = Command::new(command)
        .current_dir(cwd)
        .args(args.iter().map(|a| a.as_ref()))
        .output()
        .with_context(|| format!("Failed to invoke `{command}`."))?;
    ensure_success(command, &output.status, &output.stderr)?;
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn ensure_success(command: &str, status: &ExitStatus, stderr: &[u8]) -> Result<()> {
    if status.success() {
        return Ok(());
    }
    let detail = String::from_utf8_lossy(stderr).trim().to_string();
    bail!(
        "`{command}` failed: {}",
        if detail.is_empty() { "unknown error".into() } else { detail }
    )
}

pub fn docker_available() -> bool {
    Command::new("docker")
        .arg("info")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

pub fn connect_local(port: u16, timeout: Duration) -> Result<TcpStream> {
    let addr = format!("127.0.0.1:{port}").parse::<SocketAddr>()?;
    Ok(TcpStream::connect_timeout(&addr, timeout)?)
}

pub fn http_probe(port: u16, path: &str, timeout: Duration) -> bool {
    let Ok(mut stream) = connect_local(port, timeout) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(timeout));
    let _ = stream.set_write_timeout(Some(timeout));
    let request = format!("GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n");
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 64];
    let Ok(n) = stream.read(&mut buf) else {
        return false;
    };
    buf[..n].starts_with(b"HTTP/1.1 2") || buf[..n].starts_with(b"HTTP/1.1 3")
}

pub fn http_request_body(port: u16, path: &str, method: &str) -> Result<String> {
    let mut stream = connect_local(port, Duration::from_millis(800))?;
    stream.set_read_timeout(Some(Duration::from_secs(3)))?;
    stream.set_write_timeout(Some(Duration::from_millis(800)))?;
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    );
    stream.write_all(request.as_bytes())?;
    let mut buf = Vec::new();
    stream.read_to_end(&mut buf)?;
    let text = String::from_utf8_lossy(&buf).to_string();
    let Some(body_start) = text.find("\r\n\r\n") else {
        bail!("malformed HTTP response");
    };
    Ok(text[body_start + 4..].to_string())
}

pub fn wait_for_http(port: u16, path: &str, timeout: Duration) -> Result<()> {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if http_probe(port, path, Duration::from_millis(500)) {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(300));
    }
    Err(anyhow!(
        "Timed out waiting for http://127.0.0.1:{port}{path} (after {:?})",
        timeout
    ))
}

pub fn git(repo_path: &Path, args: &[&str]) -> Result<String> {
    let mut full = vec!["-C", repo_path.to_str().unwrap_or(".")];
    full.extend_from_slice(args);
    run_output(repo_path, "git", full)
}

pub fn git_run(repo_path: &Path, args: &[&str]) -> Result<()> {
    let mut full = vec!["-C", repo_path.to_str().unwrap_or(".")];
    full.extend_from_slice(args);
    run_checked(repo_path, "git", full)
}

pub fn git_lines(repo_path: &Path, args: &[&str]) -> Result<Vec<String>> {
    Ok(git(repo_path, args)?
        .lines()
        .map(|line| line.trim().to_string())
        .filter(|line| !line.is_empty())
        .collect())
}

pub fn matches_locked_path(path: &str, patterns: &[String]) -> bool {
    for pattern in patterns {
        if glob_match(pattern, path) {
            return true;
        }
    }
    false
}

fn glob_match(pattern: &str, path: &str) -> bool {
    if let Some(prefix) = pattern.strip_suffix("/**") {
        return path == prefix || path.starts_with(&format!("{prefix}/"));
    }
    if let Some(prefix) = pattern.strip_suffix("/*") {
        if let Some(rest) = path.strip_prefix(&format!("{prefix}/")) {
            return !rest.contains('/');
        }
        return false;
    }
    if let Some(stripped) = pattern.strip_prefix("*") {
        return path.ends_with(stripped)
            || path.rsplit_once('/').map(|(_, name)| name.contains(stripped)).unwrap_or_else(|| path.contains(stripped));
    }
    if pattern.contains('*') {
        let (before, after) = pattern.split_once('*').unwrap_or((pattern, ""));
        return path.starts_with(before) && path.ends_with(after);
    }
    path == pattern
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn locked_path_globbing() {
        let patterns = vec![
            "src-tauri/**".to_string(),
            "codex-runner/**".to_string(),
            "python-sidecar/src/sandflow_sidecar/contract.py".to_string(),
            ".env".to_string(),
            "*.pem".to_string(),
            "*secret*".to_string(),
        ];
        assert!(matches_locked_path("src-tauri/src/lib.rs", &patterns));
        assert!(matches_locked_path(
            "python-sidecar/src/sandflow_sidecar/contract.py",
            &patterns
        ));
        assert!(matches_locked_path(".env", &patterns));
        assert!(matches_locked_path("certs/foo.pem", &patterns));
        assert!(matches_locked_path("config/my-secret-file", &patterns));
        assert!(!matches_locked_path("web/app/page.tsx", &patterns));
        assert!(!matches_locked_path(
            "python-sidecar/src/sandflow_sidecar/storage.py",
            &patterns
        ));
    }
}
