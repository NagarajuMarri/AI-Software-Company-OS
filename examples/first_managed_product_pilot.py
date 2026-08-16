"""Complete deterministic Milestone 12.5 protocol using only temporary state."""

from datetime import datetime, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.pilots.first_managed_product import (
    FEATURE_BRANCH,
    MILESTONE_ID,
    PILOT_ID,
    PROJECT_ID,
    ManagedProductPilotRecord,
    PilotRecordStore,
    PilotStatus,
    RepositoryBaseline,
    learner_web_shell_request,
    pilot_tasks,
    validate_task_graph,
)


def main() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = RepositoryBaseline(
            PROJECT_ID, "https://github.com/NagarajuMarri/spoken-english-ai", "main",
            "fixture-main", "fixture-main", "main", ("main",), ("origin/main",),
            True, False, "Product Milestone 6", False, False, None, (), None, (),
            datetime.now(timezone.utc),
        ).with_digest()
        request = learner_web_shell_request()
        tasks = pilot_tasks()
        validate_task_graph(tasks)
        record = ManagedProductPilotRecord(
            PILOT_ID, PROJECT_ID, PilotStatus.PROVIDER_CONFIGURATION_REQUIRED,
            baseline.evidence_digest, "fixture-knowledge-main", request.request_id,
            "fixture-proposal-v1", "NagarajuMarri", MILESTONE_ID,
            tuple(task.task_id for task in tasks), "deterministic", (), (),
            "temporary-fixture-workspace", FEATURE_BRANCH, (), (), None, None, None,
            None, None, "BASELINE_RECONCILED",
            ("Deterministic provider validates protocol only; live execution is blocked.",),
        )
        persisted = PilotRecordStore(root / "ascos-state").save(record)
        print(f"pilot={record.pilot_id}")
        print(f"baseline={baseline.evidence_digest}")
        print(f"tasks={len(tasks)} approval_actor={record.approval_actor}")
        print(f"status={record.status.value} persisted={persisted.is_file()}")
        print("real_repository_modified=false live_provider=false merge=false deployment=false")


if __name__ == "__main__":
    main()
