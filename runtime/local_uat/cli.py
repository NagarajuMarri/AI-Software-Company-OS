"""Command-line entry point for the unified ASCOS local UAT application."""

from __future__ import annotations

import argparse
from pathlib import Path
import threading
import webbrowser
from wsgiref.simple_server import make_server

from runtime.local_uat.application import create_local_uat_application


_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765


def main(argv: list[str] | None = None) -> int:
    """Run the loopback-only development server until the user presses Ctrl+C."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    origin = f"http://{_HOST}:{arguments.port}"
    try:
        application = create_local_uat_application(arguments.data_dir, origin)
        server = make_server(_HOST, arguments.port, application)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    print("ASCOS V1 unified local UAT is ready.", flush=True)
    print(f"Open: {origin}", flush=True)
    print(f"Health: {origin}/healthz", flush=True)
    print(f"Local data: {arguments.data_dir.resolve()}", flush=True)
    print("Mode: LOCAL UAT ONLY — not a production server or deployment.", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if not arguments.no_browser:
        threading.Timer(0.35, webbrowser.open, args=(origin,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nASCOS local UAT stopped.", flush=True)
    finally:
        server.server_close()
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ascos-local-uat",
        description="Run the unified ASCOS V1 customer journey on this computer.",
    )
    parser.add_argument(
        "--port",
        type=_port,
        default=_DEFAULT_PORT,
        help=f"loopback TCP port (default: {_DEFAULT_PORT})",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(".ascos-uat-data"),
        help="persistent local UAT data directory (default: .ascos-uat-data)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not automatically open the system browser",
    )
    return parser


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer") from None
    if not 1 <= port <= 65_535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port
