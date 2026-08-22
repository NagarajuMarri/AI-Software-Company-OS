"""Command-line entry point for the unified ASCOS local UAT application."""

from __future__ import annotations

import argparse
from pathlib import Path
import threading
import webbrowser
from wsgiref.simple_server import make_server

from runtime.coding_providers import CodexAuthenticationMode
from runtime.customer_acceptance import (
    CustomerAcceptanceConfiguration,
    canonical_origin,
    load_acceptance_plan,
)
from runtime.customer_delivery import CustomerDeliveryConfiguration
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
        delivery = _delivery_configuration(parser, arguments, execution)
        acceptance = _acceptance_configuration(parser, arguments, delivery)
        application = create_local_uat_application(
            arguments.data_dir,
            origin,
            execution_configuration=execution,
            delivery_configuration=delivery,
            acceptance_configuration=acceptance,
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
        print("Codex stop: HUMAN PATCH REVIEW before any separate repository effect.", flush=True)
    if delivery is None:
        print("Draft delivery: NOT CONFIGURED", flush=True)
    else:
        state = (
            "ENABLED"
            if delivery.enabled and delivery.product_write_confirmed
            else "REVIEW ONLY"
        )
        print(
            f"Draft delivery: {state} · {delivery.repository_full_name} · "
            f"{delivery.base_branch} ← product agent branch",
            flush=True,
        )
        print("Delivery stop: OPEN DRAFT PR — no approval, merge, deploy, or release.", flush=True)
    if acceptance is None:
        print("Preview acceptance: NOT CONFIGURED", flush=True)
    else:
        state = "ENABLED" if acceptance.live_enabled else "PLAN ONLY"
        print(
            f"Preview acceptance: {state} · {acceptance.preview_environment_id} · "
            f"{len(acceptance.journeys)} browser journey(s)",
            flush=True,
        )
        print(
            "Acceptance stop: EVIDENCE ACCEPT/REVISE — no PR merge, production, release, or FamilyVault.",
            flush=True,
        )
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
    parser.add_argument(
        "--delivery-repository",
        help="trusted GitHub repository in owner/name form (operator-only)",
    )
    parser.add_argument(
        "--delivery-base-branch",
        help="approved integration branch targeted by the draft PR",
    )
    parser.add_argument(
        "--delivery-remote-name",
        default="origin",
        help="trusted Git remote name (default: origin)",
    )
    parser.add_argument(
        "--enable-product-delivery",
        action="store_true",
        help="enable one reviewed commit, non-force branch push, and draft PR",
    )
    parser.add_argument(
        "--confirm-product-repository-write",
        action="store_true",
        help="confirm product repository writes for this launcher process",
    )
    parser.add_argument(
        "--preview-url",
        help="trusted canonical isolated-preview origin (operator-only)",
    )
    parser.add_argument(
        "--preview-environment",
        help="preview-* non-production environment identity",
    )
    parser.add_argument(
        "--preview-workflow",
        help="preview-only .github/workflows/*.yml workflow file",
    )
    parser.add_argument(
        "--preview-test-job",
        help="exact required automated-test workflow job name",
    )
    parser.add_argument(
        "--preview-security-job",
        help="exact required security workflow job name",
    )
    parser.add_argument(
        "--browser-journey-plan",
        type=Path,
        help="trusted operator-owned declarative browser journey JSON",
    )
    parser.add_argument(
        "--browser-cdp-reference",
        help="optional opaque environment-variable name containing a cloud-browser CDP endpoint",
    )
    parser.add_argument(
        "--enable-preview-acceptance",
        action="store_true",
        help="enable one isolated preview workflow and one browser run",
    )
    parser.add_argument(
        "--confirm-preview-deployment",
        action="store_true",
        help="confirm one non-production preview deployment for this launcher process",
    )
    parser.add_argument(
        "--confirm-browser-execution",
        action="store_true",
        help="confirm one locked Playwright execution for this launcher process",
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


def _delivery_configuration(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    execution: CustomerExecutionConfiguration | None,
) -> CustomerDeliveryConfiguration | None:
    configured_values = bool(
        arguments.delivery_repository
        or arguments.delivery_base_branch
        or arguments.enable_product_delivery
        or arguments.confirm_product_repository_write
    )
    if not configured_values:
        return None
    if execution is None:
        parser.error("delivery configuration requires execution configuration")
    if not arguments.delivery_repository:
        parser.error("--delivery-repository is required for delivery configuration")
    if not arguments.delivery_base_branch:
        parser.error("--delivery-base-branch is required for delivery configuration")
    if arguments.confirm_product_repository_write and not arguments.enable_product_delivery:
        parser.error(
            "--confirm-product-repository-write requires --enable-product-delivery"
        )
    try:
        return CustomerDeliveryConfiguration(
            execution.workspace_root,
            arguments.delivery_repository,
            arguments.delivery_base_branch,
            arguments.delivery_remote_name,
            enabled=arguments.enable_product_delivery,
            product_write_confirmed=arguments.confirm_product_repository_write,
        )
    except ValueError as error:
        parser.error(str(error))


def _acceptance_configuration(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    delivery: CustomerDeliveryConfiguration | None,
) -> CustomerAcceptanceConfiguration | None:
    configured_values = bool(
        arguments.preview_url
        or arguments.preview_environment
        or arguments.preview_workflow
        or arguments.preview_test_job
        or arguments.preview_security_job
        or arguments.browser_journey_plan
        or arguments.browser_cdp_reference
        or arguments.enable_preview_acceptance
        or arguments.confirm_preview_deployment
        or arguments.confirm_browser_execution
    )
    if not configured_values:
        return None
    if delivery is None:
        parser.error("preview acceptance configuration requires delivery configuration")
    required = {
        "--preview-url": arguments.preview_url,
        "--preview-environment": arguments.preview_environment,
        "--preview-workflow": arguments.preview_workflow,
        "--preview-test-job": arguments.preview_test_job,
        "--preview-security-job": arguments.preview_security_job,
        "--browser-journey-plan": arguments.browser_journey_plan,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error(f"{', '.join(missing)} required for preview acceptance")
    confirmations = (
        arguments.confirm_preview_deployment,
        arguments.confirm_browser_execution,
    )
    if any(confirmations) and not arguments.enable_preview_acceptance:
        parser.error("preview effect confirmations require --enable-preview-acceptance")
    if arguments.enable_preview_acceptance and not all(confirmations):
        parser.error(
            "--enable-preview-acceptance requires both preview and browser confirmations"
        )
    try:
        profile_id, profile_version, origins, journeys, inputs = load_acceptance_plan(
            arguments.browser_journey_plan
        )
        preview_url = canonical_origin(arguments.preview_url)
        return CustomerAcceptanceConfiguration(
            preview_environment_id=arguments.preview_environment,
            preview_url=preview_url,
            workflow_file=arguments.preview_workflow,
            automated_test_job=arguments.preview_test_job,
            security_job=arguments.preview_security_job,
            acceptance_profile_id=profile_id,
            acceptance_profile_version=profile_version,
            allowed_origins=origins,
            journeys=journeys,
            inputs=inputs,
            browser_cdp_reference=arguments.browser_cdp_reference,
            enabled=arguments.enable_preview_acceptance,
            preview_deployment_confirmed=arguments.confirm_preview_deployment,
            browser_execution_confirmed=arguments.confirm_browser_execution,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
