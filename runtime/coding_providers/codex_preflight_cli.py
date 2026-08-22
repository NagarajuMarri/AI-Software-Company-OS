"""Secret-safe operator CLI for the Codex SDK execution preflight."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from runtime.coding_providers.codex_sdk_preflight import (
    CodexAuthenticationMode,
    CodexSdkPreflight,
    CodexSdkPreflightConfiguration,
)
from runtime.coding_providers.errors import CodingProviderError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ascos-codex-preflight")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--auth-mode",
        choices=tuple(mode.value for mode in CodexAuthenticationMode),
        required=True,
    )
    parser.add_argument("--credential-environment", default="OPENAI_API_KEY")
    parser.add_argument("--enable-live-provider", action="store_true")
    parser.add_argument("--confirm-live-operation", action="store_true")
    parser.add_argument("--live-check", action="store_true")
    parser.add_argument("--confirm-usage-consumption", action="store_true")
    return parser


def run(argv=None, *, preflight=None):
    arguments = build_parser().parse_args(argv)
    configuration = CodexSdkPreflightConfiguration(
        workspace_root=arguments.workspace,
        model=arguments.model,
        authentication_mode=CodexAuthenticationMode(arguments.auth_mode),
        enabled=arguments.enable_live_provider,
        live_operation_confirmed=arguments.confirm_live_operation,
        api_key_environment=arguments.credential_environment,
    )
    checker = preflight or CodexSdkPreflight()
    if arguments.live_check:
        result = checker.run_live_check(
            configuration,
            confirm_usage_consumption=arguments.confirm_usage_consumption,
        )
    else:
        result = checker.inspect(configuration)
    value = asdict(result)
    value["status"] = result.status.value
    value["authentication_mode"] = result.authentication_mode.value
    value["billing_source"] = result.billing_source.value
    value["checked_at"] = result.checked_at.isoformat()
    return value


def main(argv=None) -> int:
    try:
        value = run(argv)
    except CodingProviderError as error:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error_type": type(error).__name__,
                    "message": str(error),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0
