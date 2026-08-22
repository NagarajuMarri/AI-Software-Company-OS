"""Command-line entry point for the unified ASCOS local UAT application."""

from __future__ import annotations

import argparse
from pathlib import Path
import threading
import webbrowser
from wsgiref.simple_server import make_server

from runtime.coding_providers import CodexAuthenticationMode
from runtime.customer_execution import CustomerExecutionConfiguration
from runtime.local_uat.application import create_local_uat_application


_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765


def main(argv: list[str] | None = None) -> int:
    """Run the loopback-only development server until the user presses Ctrl+C."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    origin = f"http://{_HOST}:{arguments.port}"
    try:
        execution = _execution_configuration(parser, arguments)
        application = create_local_uat_application(
            arguments.data_dir,
            origin,
            execution_configuration=execution,
        )
        server = make_server(_HOST, arguments.port, application)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    print("ASCOS V1 unified local UAT is ready.", flush=True)
    print(f"Open: {origin}", flush=True)
    print(f"Health: {origin}/healthz", flush=True)
    print(f"Local data: {arguments.data_dir.resolve()}", flush=True)
    print("Mode: LOCAL UAT ONLY — not a production server or deployment.", flush=True)
    if execution is None:
        print("Codex execution: NOT CONFIGURED", flush=True)
    else:
        state = "ENABLED" if execution.enabled and execution.live_operation_confirmed else "DISABLED"
        print(
            f"Codex execution: {state} · {execution.authentication_mode.value} · "
            f"{execution.model}",
            flush=True,
        )
        print("Product repository delivery: REVIEW ONLY — no commit, push, PR, or deploy.", flush=True)
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
    parser.add_argument(
        "--execution-workspace",
        type=Path,
        help="trusted local product Git workspace (operator-only; never entered in browser)",
    )
    parser.add_argument(
        "--execution-model",
        default="gpt-5.6-terra",
        help="approved Codex model (default: gpt-5.6-terra)",
    )
    parser.add_argument(
        "--execution-auth-mode",
        choices=tuple(value.value for value in CodexAuthenticationMode),
        default=CodexAuthenticationMode.CHATGPT_SUBSCRIPTION.value,
        help="Codex billing/authentication source (default: chatgpt-subscription)",
    )
    parser.add_argument(
        "--execution-allowed-path",
        action="append",
        default=[],
        help="approved product-relative write prefix; repeat for multiple paths",
    )
    parser.add_argument(
        "--execution-candidate-file",
        action="append",
        default=[],
        help="approved product-relative context file; repeat for multiple files",
    )
    parser.add_argument(
        "--enable-live-execution",
        action="store_true",
        help="enable customer-approved live Codex turns (may consume plan/API usage)",
    )
    parser.add_argument(
        "--confirm-live-operation",
        action="store_true",
        help="persistently confirm live provider use for this launcher process",
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


def _execution_configuration(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
) -> CustomerExecutionConfiguration | None:
    configured_values = bool(
        arguments.execution_workspace
        or arguments.execution_allowed_path
        or arguments.execution_candidate_file
        or arguments.enable_live_execution
        or arguments.confirm_live_operation
    )
    if not configured_values:
        return None
    if arguments.execution_workspace is None:
        parser.error("--execution-workspace is required for execution configuration")
    if not arguments.execution_allowed_path:
        parser.error("at least one --execution-allowed-path is required")
    if not arguments.execution_candidate_file:
        parser.error("at least one --execution-candidate-file is required")
    if arguments.confirm_live_operation and not arguments.enable_live_execution:
        parser.error("--confirm-live-operation requires --enable-live-execution")
    try:
        return CustomerExecutionConfiguration(
            arguments.execution_workspace,
            arguments.execution_model,
            CodexAuthenticationMode(arguments.execution_auth_mode),
            tuple(arguments.execution_allowed_path),
            tuple(arguments.execution_candidate_file),
            enabled=arguments.enable_live_execution,
            live_operation_confirmed=arguments.confirm_live_operation,
        )
    except ValueError as error:
        parser.error(str(error))
