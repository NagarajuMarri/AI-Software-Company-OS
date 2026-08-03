"""Adopt an existing branch using only temporary deterministic Git fixtures."""

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.product_delivery import (
    BranchReconciliation,
    ExistingProductIntakeService,
    InMemoryExistingProductDeliveryStore,
)


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repository, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        repository = Path(directory)
        git(repository, "init", "-b", "main")
        git(repository, "config", "user.email", "example@example.invalid")
        git(repository, "config", "user.name", "ASCOS Example")
        (repository / "README.md").write_text("base\n", encoding="utf-8")
        git(repository, "add", "README.md")
        git(repository, "commit", "-m", "base")
        base = git(repository, "rev-parse", "HEAD")
        git(repository, "checkout", "-b", "product/milestone-7")
        (repository / "feature.py").write_text("MILESTONE = 7\n", encoding="utf-8")
        git(repository, "add", "feature.py")
        git(repository, "commit", "-m", "existing product work")
        head = git(repository, "rev-parse", "HEAD")
        paths = ("feature.py",)
        reconciliation = BranchReconciliation(
            base_sha=base,
            head_sha=head,
            merge_base_sha=base,
            base_is_ancestor=True,
            commit_count=1,
            changed_paths=paths,
            changed_path_digest=hashlib.sha256("feature.py".encode()).hexdigest(),
            diff_digest=hashlib.sha256(
                git(repository, "diff", "--binary", f"{base}...{head}").encode()
            ).hexdigest(),
            additions=1,
            deletions=0,
            working_tree_clean=True,
            remote_base_exists=True,
            remote_head_exists=True,
        )
        gates = ("tests", "migration", "compilation", "examples", "security")
        service = ExistingProductIntakeService(
            InMemoryExistingProductDeliveryStore()
        )
        service.register(
            project_id="fixture-product",
            milestone_id="milestone-7",
            milestone_title="Existing Product Milestone 7",
            repository="fixture/product",
            base_branch="main",
            current_branch="product/milestone-7",
            expected_base_sha=base,
            expected_head_sha=head,
            implementation_provider="historical implementation",
            implementation_evidence=(
                "Adopted for validation; not originally implemented by ASCOS"
            ),
            knowledge_snapshot="fixture-knowledge-v1",
            verification_requirements=gates,
            reconciliation=reconciliation,
        )
        for gate in gates:
            service.record_verification("fixture-product", gate, True, "passed")
        service.request_human_review("fixture-product", "human-reviewer")
        dashboard = service.dashboard("fixture-product")
        print(
            f"project={dashboard.project} state={dashboard.review_state.value} "
            f"reviewer={dashboard.reviewer}"
        )


if __name__ == "__main__":
    main()

