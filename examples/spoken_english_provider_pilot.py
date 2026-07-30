"""Offline provider-readiness demonstration; never opens the real product checkout."""

import tempfile
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.coding_providers import (
    CodingContextBuilder,
    CodingProviderRegistry,
    CodingProviderService,
    ControlledPatchApplier,
    DeterministicCodingProvider,
    FileOperation,
    FileOperationKind,
    ProviderOperationStore,
)
from runtime.pilots.spoken_english import managed_change_request


def main():
    change = managed_change_request()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        workspace = root / "managed-workspace"
        workspace.mkdir()
        (workspace / "backend.py").write_text("API = 'learner-owned'\n", encoding="utf-8")
        plan = SimpleNamespace(
            project_id="spoken-english-ai", execution_plan_id="pilot-plan-v1",
            version=1, workspace_identity="pilot-workspace",
            feature_branch="ascos/personalised-daily-practice")
        task = SimpleNamespace(
            project_task_id="daily-practice-backend",
            objective=change.objective,
            acceptance_criteria=change.acceptance_criteria,
            allowed_paths=("",), forbidden_paths=(".env", ".git/", "deploy/"),
            allowed_commands=(("python", "-m", "pytest", "-q"),),
            candidate_files=("backend.py",))
        request = SimpleNamespace(
            external_task_id="pilot-plan-v1-daily-practice-backend-attempt-1",
            timeout_seconds=120)
        provider = DeterministicCodingProvider(file_operations=(
            FileOperation(
                FileOperationKind.CREATE, "daily_practice_plan.txt",
                "warm-up, situation, vocabulary, grammar, pronunciation, completion\n"),))
        service = CodingProviderService(
            CodingProviderRegistry((provider,)), ProviderOperationStore(root / "state"),
            CodingContextBuilder(), ControlledPatchApplier())
        operation, provider_request = service.prepare(
            plan=plan, task=task, coding_request=request, workspace_path=workspace,
            provider_id="deterministic")
        submitted = service.submit(
            "spoken-english-ai", operation.provider_operation_id, provider_request)
        print(f"pilot={change.request_id}")
        print(f"provider_state={submitted.state.value}")
        print(f"context_digest={provider_request.context_digest}")
        print("live_provider=false product_repository_modified=false")


if __name__ == "__main__":
    main()
