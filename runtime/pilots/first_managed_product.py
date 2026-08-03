"""Milestone 12.5 records and policy for a real managed-product pilot.

This module deliberately performs no Git, provider, or product-repository effects.
Those remain behind the existing managed planning/execution services.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from runtime.planning import ChangePriority, ManagedProductChangeRequest


PROJECT_ID = "spoken-english-ai"
PILOT_ID = "milestone-12-5-spoken-english-web-shell"
FEATURE_BRANCH = "ascos/milestone-8-learner-web-shell"
BASE_BRANCH = "main"
MILESTONE_ID = "learner-web-experience-foundation"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


class PilotStatus(str, Enum):
    BASELINE_RECONCILED = "BASELINE_RECONCILED"
    PLANNED = "PLANNED"
    APPROVED = "APPROVED"
    MATERIALISED = "MATERIALISED"
    PROVIDER_CONFIGURATION_REQUIRED = "PROVIDER_CONFIGURATION_REQUIRED"
    CODEX_LIVE_SMOKE_TEST_REQUIRED = "CODEX_LIVE_SMOKE_TEST_REQUIRED"
    EXECUTING = "EXECUTING"
    RESULT_ACCEPTED = "RESULT_ACCEPTED"
    QUALITY_VALIDATED = "QUALITY_VALIDATED"
    REVIEWED = "REVIEWED"
    COMMITTED = "COMMITTED"
    PUSHED = "PUSHED"
    DRAFT_PR_CREATED = "DRAFT_PR_CREATED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class RepositoryBaseline:
    project_id: str
    repository_identity: str
    default_branch: str
    origin_main_sha: str
    local_main_sha: str
    current_branch: str
    local_branches: tuple[str, ...]
    remote_branches: tuple[str, ...]
    working_tree_clean: bool
    local_main_divergent: bool
    latest_merged_milestone: str
    milestone_7_local: bool
    milestone_7_remote: bool
    milestone_7_commit: str | None
    milestone_7_reachable_from: tuple[str, ...]
    milestone_7_pull_request: str | None
    unresolved_discrepancies: tuple[str, ...]
    inspected_at: datetime = field(default_factory=utc_now)
    evidence_digest: str = ""

    def __post_init__(self) -> None:
        if self.inspected_at.tzinfo is None:
            raise ValueError("inspection timestamp must be timezone-aware")
        if self.project_id != PROJECT_ID:
            raise ValueError("baseline is for an unexpected project")

    def with_digest(self) -> RepositoryBaseline:
        values = asdict(self)
        values["evidence_digest"] = ""
        return replace(self, evidence_digest=digest(values))

    @property
    def reconciliation_status(self) -> PilotStatus:
        if not self.working_tree_clean or self.local_main_divergent:
            return PilotStatus.RECONCILIATION_REQUIRED
        return PilotStatus.BASELINE_RECONCILED


@dataclass(frozen=True)
class KnowledgeSnapshotBinding:
    snapshot_id: str
    project_id: str
    repository_sha: str
    scan_digest: str
    ignored_path_policy: tuple[str, ...]
    observed_areas: tuple[tuple[str, tuple[str, ...]], ...]
    commands: tuple[tuple[str, str], ...]
    scanned_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class PilotTask:
    task_id: str
    title: str
    objective: str
    allowed_paths: tuple[str, ...]
    prohibited_paths: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    dependencies: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    quality_gates: tuple[str, ...]
    expected_evidence: tuple[str, ...]
    risk_classification: str
    maximum_output_bytes: int
    timeout_seconds: int
    maximum_attempts: int


def learner_web_shell_request(*, requested_by: str = "NagarajuMarri") -> ManagedProductChangeRequest:
    return ManagedProductChangeRequest(
        "learner-daily-speaking-practice-web-shell",
        PROJECT_ID,
        "Learner Daily Speaking Practice Web Shell",
        "Add the first authenticated learner-facing web shell around existing backend contracts.",
        "First real ASCOS-managed Spoken English product delivery pilot.",
        ("frontend implementation", "test generation", "documentation", "refactoring"),
        (
            "Authenticated learner can view the existing daily plan.",
            "Learner can submit text practice and view tutor feedback.",
            "Responsive, keyboard-accessible loading, empty, and error states are covered.",
            "No live voice, external AI, payment, merge, or deployment is introduced.",
        ),
        (
            "CONTROLLED_WRITE and explicit product-write permission are required.",
            "Execution is bound to the reconciled origin/main SHA.",
            "Tokens and secrets never enter provider context or persisted evidence.",
        ),
        ("STT", "TTS", "pronunciation scoring", "payments", "admin UI", "deployment"),
        ChangePriority.HIGH,
        requested_by,
        preferred_base_branch=BASE_BRANCH,
    )


def pilot_tasks() -> tuple[PilotTask, ...]:
    common_forbidden = (
        "backend/**", ".git/**", ".env", "**/.env", "**/node_modules/**",
        "**/dist/**", "**/__pycache__/**",
    )
    capabilities = ("CODE_GENERATION", "CODE_MODIFICATION", "TEST_GENERATION", "DOCUMENTATION")
    gates = ("frontend-test", "frontend-typecheck", "frontend-lint", "frontend-build", "diff-check")
    specs = (
        ("frontend-foundation", "Frontend Application Foundation", "Create a conservative React, TypeScript, and Vite foundation.", (), ("frontend/**", "README.md", "docs/**")),
        ("authenticated-session", "Authenticated Learner Session", "Implement login, safe token lifecycle, logout, and unauthenticated routing.", ("frontend-foundation",), ("frontend/src/auth/**", "frontend/src/api/**", "frontend/src/**/*.test.*")),
        ("daily-plan", "Daily Plan Experience", "Render the existing daily-plan contract with complete UI states.", ("authenticated-session",), ("frontend/src/features/daily-plan/**", "frontend/src/**/*.test.*")),
        ("text-practice", "Text Speaking Practice Experience", "Submit text to the supported conversation endpoint and render feedback.", ("daily-plan",), ("frontend/src/features/practice/**", "frontend/src/**/*.test.*")),
        ("accessibility", "Accessibility and Responsive Quality", "Add semantic landmarks, keyboard flow, focus visibility, and responsive styling.", ("text-practice",), ("frontend/src/**",)),
        ("frontend-docs-tests", "Frontend Test and Documentation Coverage", "Complete mocked flows, accessibility checks, and operator documentation.", ("accessibility",), ("frontend/**", "README.md", "docs/**")),
    )
    return tuple(PilotTask(
        task_id, title, objective, allowed, common_forbidden,
        ("Changes stay within allowed paths.", "Relevant automated tests pass.",
         "No credential, unsafe HTML injection, or production URL is introduced."),
        dependencies, capabilities, gates,
        ("provider receipt", "accepted result", "post-application manifest", "quality results"),
        "MEDIUM" if task_id not in {"authenticated-session", "text-practice"} else "HIGH",
        96_000, 600, 1,
    ) for task_id, title, objective, dependencies, allowed in specs)


def validate_task_graph(tasks: tuple[PilotTask, ...]) -> None:
    seen: set[str] = set()
    for task in tasks:
        if task.task_id in seen or any(item not in seen for item in task.dependencies):
            raise ValueError("tasks must be unique and dependency ordered")
        if task.maximum_output_bytes <= 0 or task.timeout_seconds <= 0:
            raise ValueError("task limits must be positive")
        seen.add(task.task_id)


@dataclass(frozen=True)
class ManagedProductPilotRecord:
    pilot_id: str
    project_id: str
    status: PilotStatus
    repository_baseline_digest: str
    knowledge_snapshot_id: str
    change_request_id: str
    proposal_id: str
    approval_actor: str
    materialised_milestone_id: str
    task_ids: tuple[str, ...]
    provider_id: str | None
    provider_operation_ids: tuple[str, ...]
    durable_receipt_ids: tuple[str, ...]
    workspace_id: str | None
    feature_branch: str
    accepted_result_ids: tuple[str, ...]
    quality_evidence_ids: tuple[str, ...]
    review_evidence_id: str | None
    commit_sha: str | None
    remote_branch_sha: str | None
    draft_pr_number: int | None
    draft_pr_url: str | None
    reconciliation_status: str
    known_limitations: tuple[str, ...]
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


class PilotRecordStore:
    """Atomic project-isolated JSON storage located in ASCOS-controlled state."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def save(self, record: ManagedProductPilotRecord) -> Path:
        if record.project_id != PROJECT_ID or record.pilot_id != PILOT_ID:
            raise ValueError("pilot record identity mismatch")
        target = self.root / record.project_id / "pilots" / f"{record.pilot_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(record), sort_keys=True, indent=2, default=str), encoding="utf-8")
        temporary.replace(target)
        return target

    def save_baseline(self, baseline: RepositoryBaseline) -> Path:
        if baseline.project_id != PROJECT_ID or not baseline.evidence_digest:
            raise ValueError("baseline must be digested for the managed project")
        return self._save_json("repository-baseline.json", asdict(baseline))

    def save_knowledge_binding(self, binding: KnowledgeSnapshotBinding) -> Path:
        if binding.project_id != PROJECT_ID:
            raise ValueError("knowledge binding identity mismatch")
        return self._save_json("knowledge-binding.json", asdict(binding))

    def _save_json(self, name: str, value: object) -> Path:
        target = self.root / PROJECT_ID / "pilots" / PILOT_ID / name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, sort_keys=True, indent=2, default=str), encoding="utf-8")
        temporary.replace(target)
        return target

    def load(self) -> dict[str, object]:
        target = self.root / PROJECT_ID / "pilots" / f"{PILOT_ID}.json"
        return json.loads(target.read_text(encoding="utf-8"))

    def update_status(self, status: PilotStatus, limitation: str) -> Path:
        """Atomically advance terminal evidence without reconstructing prior identities."""
        value = self.load()
        value["status"] = status.value
        value["updated_at"] = utc_now().isoformat()
        existing = value.get("known_limitations", ())
        limitations = list(existing) if isinstance(existing, list) else []
        if limitation not in limitations:
            limitations.append(limitation)
        value["known_limitations"] = limitations
        target = self.root / PROJECT_ID / "pilots" / f"{PILOT_ID}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")
        temporary.replace(target)
        return target
