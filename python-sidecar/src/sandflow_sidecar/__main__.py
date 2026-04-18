from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

import uvicorn

from .contract import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Sandflow sidecar.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--port-file", type=Path, default=None)
    args = parser.parse_args()

    port = args.port if args.port != 0 else _pick_free_port()
    if args.port_file is not None:
        args.port_file.parent.mkdir(parents=True, exist_ok=True)
        args.port_file.write_text(str(port), encoding="utf-8")
    print(f"PORT={port}", file=sys.stderr, flush=True)
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
