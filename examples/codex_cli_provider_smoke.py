"""Deterministic disposable-workspace Codex smoke test with a fake runner."""

from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.coding_providers import CodexScratchCodingProvider, CodexScratchConfiguration
from runtime.tools.models import CommandResult


class FakeRunner:
    def execute(self, request):
        now = datetime.now(timezone.utc)
        if request.executable == "git":
            value = subprocess.run(["git", *request.arguments], cwd=request.working_directory,
                                   capture_output=True, text=True)
            return CommandResult("git", request.arguments, value.returncode, value.stdout,
                                 value.stderr, now, now, 0.01, False)
        if request.arguments == ("--version",):
            return CommandResult("codex.cmd", request.arguments, 0, "codex-cli 0.146.0",
                                 "", now, now, 0.01, False)
        root = Path(request.working_directory)
        target = root / "docs" / "ascos-codex-smoke.txt"
        target.parent.mkdir(exist_ok=True)
        target.write_text("ASCOS_CODEX_PROVIDER_SMOKE_TEST_OK\n", encoding="utf-8")
        summary = Path(request.arguments[request.arguments.index("--output-last-message") + 1])
        summary.write_text("implemented bounded fixture", encoding="utf-8")
        return CommandResult("codex.cmd", request.arguments, 0, "", "",
                             now, now, 0.01, False)


def main() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source, scratch = root / "source", root / "scratch"
        source.mkdir(); scratch.mkdir()
        subprocess.run(["git", "init", "-b", "agent/smoke"], cwd=source, check=True,
                       capture_output=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"],
                       cwd=source, check=True)
        subprocess.run(["git", "config", "user.name", "ASCOS Fixture"],
                       cwd=source, check=True)
        (source / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=source, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=source, check=True,
                       capture_output=True)
        receipts, manifests, effects = [], [], []
        provider = CodexScratchCodingProvider(CodexScratchConfiguration(
            enabled=True, source_workspace=str(source), scratch_root=str(scratch)),
            runner=FakeRunner(),
            response_sink=lambda receipt, result: receipts.append(receipt),
            manifest_sink=manifests.append, effect_sink=effects.append)
        context = SimpleNamespace(
            objective="Create exact smoke file", acceptance_criteria=("exact content",),
            allowed_paths=("docs/ascos-codex-smoke.txt",),
            forbidden_paths=(".git", ".env"), allows_deletions=False)
        request = SimpleNamespace(
            provider_operation_id="fixture-scratch-operation",
            provider_idempotency_key="fixture-scratch-key", external_task_id="fixture-task",
            project_id="fixture", execution_plan_id="fixture-plan", plan_version=1,
            managed_task_id="smoke", workspace_id="final-workspace", branch="agent/smoke",
            request_digest="a" * 64, context_digest="b" * 64, context=context,
            timeout_seconds=60, maximum_output_bytes=96_000)
        first = provider.submit_task(request)
        duplicate = provider.submit_task(request)
        print(f"provider={provider.provider_id} mode=DISPOSABLE_WORKSPACE_MUTATION")
        print(f"paths={manifests[0].changed_paths} receipt={len(receipts)}")
        print(f"duplicate_suppressed={first == duplicate} cleanup={effects[-1].stage.value}")
        print("live=false commit=false push=false pr=false merge=false deployment=false")


if __name__ == "__main__":
    main()
