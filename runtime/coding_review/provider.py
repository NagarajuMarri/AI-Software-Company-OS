"""Bounded local text implementation, pytest, and static Security review for Day 32."""

from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Protocol

from runtime.coding_review.errors import (
    CodingReviewFailed,
    CodingReviewPolicyError,
    CodingReviewReconciliationRequired,
)
from runtime.coding_review.models import (
    QA_ROLE,
    SECURITY_ROLE,
    CodingReviewAuthority,
    CodingReviewObservation,
    CodingReviewWorkOrder,
    CodingRoundPlan,
    CodingRoundRecord,
    FailureRoute,
    ObservedProductFile,
    ReviewFinding,
    TextPatch,
)


class CodingReviewProvider(Protocol):
    """Apply bounded text plans and return closed review evidence."""

    provider_id: str

    def execute(
        self,
        workspace: Path,
        work_order: CodingReviewWorkOrder,
        authority: CodingReviewAuthority,
    ) -> CodingReviewObservation: ...


class LocalDeterministicCodingReviewProvider:
    """Exercise a real local review loop without network, credentials, or Git delivery."""

    provider_id = "local-deterministic-coding-review-v1"

    def __init__(self, plans: tuple[CodingRoundPlan, ...] | None = None) -> None:
        self._plans = plans
        self.execution_count = 0

    def execute(
        self,
        workspace: Path,
        work_order: CodingReviewWorkOrder,
        authority: CodingReviewAuthority,
    ) -> CodingReviewObservation:
        if not isinstance(workspace, Path):
            raise CodingReviewPolicyError("Coding-review workspace must be a Path")
        self.execution_count += 1
        root = workspace.absolute()
        _real_directory(root, "coding-review workspace")
        if root.resolve() != root:
            raise CodingReviewPolicyError("Coding-review workspace path contains a link")
        plans = self._plans
        if plans is None:
            if work_order.repository_id != "generic-product-fixture":
                raise CodingReviewPolicyError(
                    "Default deterministic implementation is only for the generic fixture"
                )
            plans = default_generic_fixture_plans()
        if not 1 <= len(plans) <= authority.max_review_rounds:
            raise CodingReviewPolicyError("Coding-review plan exceeds the round budget")
        if tuple(item.round_number for item in plans) != tuple(range(1, len(plans) + 1)):
            raise CodingReviewPolicyError("Coding-review plans are out of order")

        records: list[CodingRoundRecord] = []
        routes: list[FailureRoute] = []
        changed: set[str] = set()
        writes = 0
        commands = 0
        previous_codes: tuple[str, ...] = ()
        passed = False

        for index, plan in enumerate(plans):
            if plan.resolves_feedback_codes != previous_codes:
                raise CodingReviewPolicyError(
                    "Coding round does not consume the exact returned review feedback"
                )
            self._validate_patches(root, work_order, plan)
            for patch in plan.patches:
                self._write(root, patch)
                changed.add(patch.path)
                writes += 1
            if writes > authority.max_file_writes:
                raise CodingReviewPolicyError("Coding-review file-write budget was exceeded")

            qa_passed, qa_count, qa_digest = self._qa(root, work_order.qa_test_paths)
            commands += 1
            findings: tuple[ReviewFinding, ...]
            if not qa_passed:
                findings = (
                    ReviewFinding(
                        code="QA_TEST_FAILURE",
                        reviewer_role=QA_ROLE,
                        responsible_role=plan.failure_owner_role,
                        path=work_order.qa_test_paths[0],
                        severity="HIGH",
                        summary="The isolated product test suite did not pass",
                    ),
                )
                security_status = "NOT_RUN_QA_FAILED"
            else:
                findings = self._security(root, work_order, plan.failure_owner_role)
                commands += 1
                security_status = "FAIL" if findings else "PASS"
            record = CodingRoundRecord(
                round_number=plan.round_number,
                resolved_feedback_codes=plan.resolves_feedback_codes,
                changed_paths=tuple(sorted(item.path for item in plan.patches)),
                qa_status="PASS" if qa_passed else "FAIL",
                qa_test_count=qa_count,
                qa_result_digest=qa_digest,
                security_status=security_status,
                findings=findings,
                diff_digest=self._content_state_digest(root, tuple(sorted(changed))),
                file_write_count=len(plan.patches),
                specialized_command_count=1 if not qa_passed else 2,
            )
            records.append(record)
            for finding in findings:
                routes.append(
                    FailureRoute(
                        route_id=f"route-round-{plan.round_number}-{finding.code.lower()}",
                        round_number=plan.round_number,
                        finding_code=finding.code,
                        reviewer_role=finding.reviewer_role,
                        responsible_role=finding.responsible_role,
                    )
                )
            previous_codes = record.failure_codes
            if qa_passed and security_status == "PASS":
                if index != len(plans) - 1:
                    raise CodingReviewPolicyError(
                        "Coding-review plan contains work after both reviews passed"
                    )
                passed = True
                break

        if not passed:
            raise CodingReviewFailed(
                "Coding-review rounds ended without QA and Security pass"
            )
        if commands + writes > authority.max_tool_calls:
            raise CodingReviewPolicyError("Coding-review tool-call budget was exceeded")
        final_paths = tuple(sorted(changed))
        final_files = tuple(
            ObservedProductFile(
                path=path,
                owner_role=work_order.owner_for(path),
                content_digest=hashlib.sha256((root / path).read_bytes()).hexdigest(),
            )
            for path in final_paths
        )
        return CodingReviewObservation(
            provider_id=self.provider_id,
            rounds=tuple(records),
            failure_routes=tuple(routes),
            final_changed_paths=final_paths,
            final_files=final_files,
            final_diff_digest="0" * 64,
            qa_execution_count=len(records),
            security_execution_count=sum(
                item.security_status != "NOT_RUN_QA_FAILED" for item in records
            ),
            product_file_write_count=writes,
            specialized_command_count=commands,
        )

    @staticmethod
    def _validate_patches(
        root: Path,
        work_order: CodingReviewWorkOrder,
        plan: CodingRoundPlan,
    ) -> None:
        for patch in plan.patches:
            try:
                owner = work_order.owner_for(patch.path)
            except ValueError as error:
                raise CodingReviewPolicyError("Patch path is outside the work order") from error
            if owner != patch.owner_role:
                raise CodingReviewPolicyError("Patch role does not own its target path")
            destination = _destination(root, patch.path)
            if destination.exists() and not destination.is_file():
                raise CodingReviewPolicyError("Patch destination is not a regular file")

    @staticmethod
    def _write(root: Path, patch: TextPatch) -> None:
        destination = _destination(root, patch.path)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _destination(root, patch.path)
        stage = destination.with_name(f".{destination.name}.ascos-stage")
        if os.path.lexists(stage):
            raise CodingReviewReconciliationRequired("Patch staging path already exists")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(stage, flags, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(patch.content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(stage, destination)
            os.chmod(destination, 0o644)
        except Exception as error:
            try:
                stage.unlink(missing_ok=True)
            except OSError:
                pass
            if isinstance(error, CodingReviewReconciliationRequired):
                raise
            raise CodingReviewReconciliationRequired(
                "Text patch effect is partial or uncertain"
            ) from error

    @staticmethod
    def _qa(workspace: Path, test_paths: tuple[str, ...]) -> tuple[bool, int, str]:
        if any(not (workspace / path).is_file() for path in test_paths):
            raise CodingReviewPolicyError("QA test materialization is incomplete")
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
        }
        if os.name == "nt":
            environment["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "C:\\Windows")
        result = subprocess.run(
            (
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                *test_paths,
            ),
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            shell=False,
            timeout=60,
            check=False,
        )
        output = (result.stdout + result.stderr).encode("utf-8", errors="replace")
        digest = hashlib.sha256(output).hexdigest()
        counts = tuple(
            int(value)
            for value in re.findall(r"(\d+) (?:passed|failed|error|errors)", output.decode(errors="replace"))
        )
        return result.returncode == 0, max(sum(counts), 1), digest

    @staticmethod
    def _security(
        workspace: Path,
        work_order: CodingReviewWorkOrder,
        failure_owner_role: str,
    ) -> tuple[ReviewFinding, ...]:
        findings: list[ReviewFinding] = []
        local_modules = {Path(path).stem for path in work_order.allowed_paths if path.endswith(".py")}
        forbidden_imports = {
            "ftplib",
            "http",
            "requests",
            "socket",
            "subprocess",
            "urllib",
        }
        forbidden_calls = {"compile", "eval", "exec", "__import__"}
        secret_names = re.compile(r"(?i)(api[_-]?key|password|secret|token)")
        for path in work_order.allowed_paths:
            target = workspace / path
            if not target.is_file() or target.suffix != ".py":
                continue
            try:
                tree = ast.parse(target.read_text(encoding="utf-8"), filename=path)
            except (OSError, SyntaxError) as error:
                findings.append(
                    ReviewFinding(
                        "INVALID_PYTHON_SOURCE",
                        SECURITY_ROLE,
                        failure_owner_role,
                        path,
                        "HIGH",
                        "Static Security review could not parse the changed Python source",
                    )
                )
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = (
                        tuple(item.name.split(".")[0] for item in node.names)
                        if isinstance(node, ast.Import)
                        else ((node.module or "").split(".")[0],)
                    )
                    for name in names:
                        if name in forbidden_imports:
                            findings.append(
                                ReviewFinding(
                                    "FORBIDDEN_RUNTIME_CAPABILITY",
                                    SECURITY_ROLE,
                                    failure_owner_role,
                                    path,
                                    "CRITICAL",
                                    "Changed source imports a forbidden command or network capability",
                                )
                            )
                        elif (
                            name
                            and name not in local_modules
                            and name != "pytest"
                            and name not in sys.stdlib_module_names
                        ):
                            findings.append(
                                ReviewFinding(
                                    "UNAPPROVED_DEPENDENCY",
                                    SECURITY_ROLE,
                                    failure_owner_role,
                                    path,
                                    "HIGH",
                                    "Changed source imports a dependency outside the approved environment",
                                )
                            )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in forbidden_calls
                ):
                    findings.append(
                        ReviewFinding(
                            "UNSAFE_DYNAMIC_EXECUTION",
                            SECURITY_ROLE,
                            failure_owner_role,
                            path,
                            "CRITICAL",
                            "Changed source contains forbidden dynamic execution",
                        )
                    )
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
                    value = node.value
                    if (
                        isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and value.value
                        and any(
                            isinstance(target_name, ast.Name)
                            and secret_names.search(target_name.id)
                            for target_name in targets
                        )
                    ):
                        findings.append(
                            ReviewFinding(
                                "HARDCODED_SECRET",
                                SECURITY_ROLE,
                                failure_owner_role,
                                path,
                                "CRITICAL",
                                "Changed source contains a hard-coded secret-like value",
                            )
                        )
        unique: dict[tuple[str, str], ReviewFinding] = {}
        for finding in findings:
            unique[(finding.code, finding.path)] = finding
        return tuple(unique[key] for key in sorted(unique))

    @staticmethod
    def _content_state_digest(workspace: Path, paths: tuple[str, ...]) -> str:
        digest = hashlib.sha256()
        for path in paths:
            digest.update(path.encode())
            digest.update(b"\0")
            digest.update((workspace / path).read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()


def default_generic_fixture_plans() -> tuple[CodingRoundPlan, ...]:
    """Return a three-round fixture proving QA and Security feedback routing."""

    return (
        CodingRoundPlan(
            round_number=1,
            resolves_feedback_codes=(),
            failure_owner_role="BACKEND_ENGINEER",
            patches=(
                TextPatch(
                    "BACKEND_ENGINEER",
                    "app.py",
                    "from ai import summarize\nfrom backend import release_value\nfrom data import persist\nfrom frontend import render_status\n\n\ndef value():\n    return release_value()\n\n\ndef product_snapshot():\n    current = value()\n    return {\n        'status': render_status(current),\n        'summary': summarize('reviewed'),\n        'record': persist(current),\n    }\n",
                ),
                TextPatch(
                    "BACKEND_ENGINEER",
                    "backend.py",
                    "def release_value():\n    return 31\n",
                ),
                TextPatch(
                    "FRONTEND_ENGINEER",
                    "frontend.py",
                    "def render_status(value):\n    return f'ASCOS {value}'\n",
                ),
                TextPatch(
                    "AI_ENGINEER",
                    "ai.py",
                    "def summarize(value):\n    return value.strip().upper()\n",
                ),
                TextPatch(
                    "DATA_ENGINEER",
                    "data.py",
                    "def persist(value):\n    return {'value': value}\n",
                ),
                TextPatch(
                    QA_ROLE,
                    "test_product.py",
                    "from app import product_snapshot, value\n\n\ndef test_release_value():\n    assert value() == 32\n\n\ndef test_integrated_snapshot():\n    assert product_snapshot() == {\n        'status': 'ASCOS 32',\n        'summary': 'REVIEWED',\n        'record': {'value': 32},\n    }\n",
                ),
            ),
        ),
        CodingRoundPlan(
            round_number=2,
            resolves_feedback_codes=("QA_TEST_FAILURE",),
            failure_owner_role="BACKEND_ENGINEER",
            patches=(
                TextPatch(
                    "BACKEND_ENGINEER",
                    "backend.py",
                    "def release_value():\n    return 32\n\n\ndef evaluate_expression(value):\n    return eval(value)\n",
                ),
            ),
        ),
        CodingRoundPlan(
            round_number=3,
            resolves_feedback_codes=("UNSAFE_DYNAMIC_EXECUTION",),
            failure_owner_role="BACKEND_ENGINEER",
            patches=(
                TextPatch(
                    "BACKEND_ENGINEER",
                    "backend.py",
                    "def release_value():\n    return 32\n",
                ),
            ),
        ),
    )


def _destination(root: Path, relative: str) -> Path:
    candidate = root
    parts = Path(relative.replace("\\", "/")).parts
    for index, part in enumerate(parts):
        candidate = candidate / part
        if not os.path.lexists(candidate):
            continue
        details = candidate.lstat()
        attributes = getattr(details, "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(details.st_mode) or attributes & reparse:
            raise CodingReviewPolicyError("Patch path contains a link or reparse point")
        if index < len(parts) - 1 and not stat.S_ISDIR(details.st_mode):
            raise CodingReviewPolicyError("Patch parent is not a directory")
    absolute = candidate.absolute()
    if os.path.commonpath((str(root), str(absolute))) != str(root):
        raise CodingReviewPolicyError("Patch path escapes the workspace")
    return candidate


def _real_directory(path: Path, label: str) -> None:
    try:
        details = path.lstat()
    except FileNotFoundError as error:
        raise CodingReviewPolicyError(f"{label} does not exist") from error
    if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
        raise CodingReviewPolicyError(f"{label} is unsafe")
