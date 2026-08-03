"""Deterministic Codex CLI adapter smoke test with an injected fake runner."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.coding_providers import CodexCliCodingProvider, CodexCliProviderConfiguration
from runtime.tools.models import CommandResult


class FakeRunner:
    def execute(self, request):
        now = datetime.now(timezone.utc)
        if request.arguments == ("--version",):
            output = "codex-cli 0.146.0"
        elif request.arguments == ("exec", "--help"):
            output = "Run Codex non-interactively"
        else:
            path = Path(request.arguments[request.arguments.index("--output-last-message") + 1])
            path.write_text(json.dumps({
                "status": "SUCCEEDED", "summary": "fixture proposal",
                "file_operations": [{
                    "operation_type": "CREATE", "path": "docs/ascos-codex-smoke.txt",
                    "content": "ASCOS_CODEX_PROVIDER_SMOKE_TEST_OK\n",
                    "expected_prior_digest": None,
                }],
                "progress": ["structured proposal created"], "diagnostics": [],
            }), encoding="utf-8")
            output = "bounded fake runner"
        return CommandResult(request.executable, request.arguments, 0, output, "",
                             now, now, 0.01, False)


def main() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        receipts = []
        provider = CodexCliCodingProvider(CodexCliProviderConfiguration(
            enabled=True, allowed_workspace_root=str(root), health_smoke_test=False),
            runner=FakeRunner(), response_sink=lambda receipt, result: receipts.append(receipt))
        context = SimpleNamespace(
            byte_count=0, objective="Create exact smoke file",
            acceptance_criteria=("exact content",),
            allowed_paths=("docs/ascos-codex-smoke.txt",),
            forbidden_paths=(".git", ".env"), files=(),
        )
        request = SimpleNamespace(
            provider_operation_id="fixture-operation", provider_idempotency_key="fixture-key",
            external_task_id="fixture-task", project_id="fixture",
            execution_plan_id="fixture-plan", plan_version=1, managed_task_id="smoke",
            workspace_id="fixture-workspace", branch="agent/smoke",
            request_digest="request-digest", context_digest="context-digest", context=context,
            timeout_seconds=60, maximum_output_bytes=96_000,
        )
        first = provider.submit_task(request)
        duplicate = provider.submit_task(request)
        result = provider.get_task_result(first)
        print(f"provider={provider.provider_id} cli={provider.cli_version}")
        print(f"operations={len(result.file_operations)} receipt={len(receipts)}")
        print(f"duplicate_suppressed={first == duplicate}")
        print("live=false commit=false push=false pr=false merge=false deployment=false")


if __name__ == "__main__":
    main()
