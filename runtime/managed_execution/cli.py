"""Command-line entry point for managed-product execution records."""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum

from runtime.exceptions import RuntimeDomainError
from runtime.managed_execution.models import (
    ExecutionMode,
    ManagedProductExecutionRequest,
)
from runtime.managed_execution.service import ManagedProductExecutionService
from runtime.managed_execution.storage import ManagedExecutionStore
from runtime.planning.storage import PlanningStore
from runtime.project_manager import AIProjectManager, ManagerStateStore
from runtime.projects import FileProjectRegistry


def build_parser():
    parser = argparse.ArgumentParser(prog="ascos-execution")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--planning-state-root", required=True)
    parser.add_argument("--execution-state-root", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-product-write", action="store_true")
    execution = parser.add_subparsers(dest="group", required=True)
    request = execution.add_parser("request").add_subparsers(
        dest="action", required=True)
    create = request.add_parser("create")
    create.add_argument("project_id")
    create.add_argument("execution_request_id")
    create.add_argument("--proposal-id", required=True)
    create.add_argument("--milestone-id", required=True)
    create.add_argument("--task-id", action="append", required=True)
    create.add_argument("--requested-by", required=True)
    create.add_argument("--correlation-id", required=True)
    create.add_argument("--base-branch", required=True)
    create.add_argument("--feature-branch", required=True)
    create.add_argument("--mode", choices=[item.value for item in ExecutionMode],
                        default=ExecutionMode.PLAN_ONLY.value)
    create.add_argument("--quality-gate-profile", required=True)
    create.add_argument("--coding-capability", required=True)
    create.add_argument("--workspace-policy", required=True)
    create.add_argument("--approval-policy", required=True)
    for action in ("show", "list"):
        command = request.add_parser(action)
        command.add_argument("project_id")
        if action == "show":
            command.add_argument("execution_request_id")
    plan = execution.add_parser("plan").add_subparsers(
        dest="action", required=True)
    for action in ("generate", "show", "approve", "reject"):
        command = plan.add_parser(action)
        command.add_argument("project_id")
        command.add_argument(
            "execution_request_id" if action == "generate" else "plan_id")
        if action in {"approve", "reject"}:
            command.add_argument("--actor", required=True)
        if action == "reject":
            command.add_argument("--reason", required=True)
    status = execution.add_parser("status")
    status.add_argument("project_id")
    status.add_argument("plan_id")
    listing = execution.add_parser("list")
    listing.add_argument("project_id")
    cancel = execution.add_parser("cancel")
    cancel.add_argument("project_id")
    cancel.add_argument("plan_id")
    cancel.add_argument("--actor", required=True)
    cancel.add_argument("--reason", required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    registry = FileProjectRegistry(args.registry)
    service = ManagedProductExecutionService(
        registry,
        PlanningStore(args.planning_state_root),
        ManagedExecutionStore(args.execution_state_root),
        lambda project_id: AIProjectManager.load(
            project_id, registry, ManagerStateStore(args.planning_state_root)),
    )
    try:
        result = _execute(service, args)
        value = _encode(result)
        print(json.dumps(value, sort_keys=True) if args.json else _human(value))
        return 0
    except (RuntimeDomainError, ValueError) as error:
        value = {"error": str(error)}
        print(json.dumps(value, sort_keys=True) if args.json else f"error: {error}")
        return 2


def _execute(service, args):
    if args.group == "request":
        if args.action == "create":
            return service.create_execution_request(ManagedProductExecutionRequest(
                args.execution_request_id,
                args.project_id,
                args.proposal_id,
                args.milestone_id,
                tuple(args.task_id),
                args.requested_by,
                datetime.now(timezone.utc),
                args.correlation_id,
                args.base_branch,
                args.feature_branch,
                ExecutionMode(args.mode),
                args.quality_gate_profile,
                args.coding_capability,
                args.workspace_policy,
                args.approval_policy,
            ))
        if args.action == "show":
            return service.store.load_request(
                args.project_id, args.execution_request_id)
        return service.store.list_requests(args.project_id)
    if args.group == "plan":
        if args.action == "generate":
            return service.generate_execution_plan(
                args.project_id, args.execution_request_id)
        if args.action == "show":
            return service.get_execution_plan(args.project_id, args.plan_id)
        if args.action == "approve":
            return service.approve_execution_plan(
                args.project_id, args.plan_id, args.actor)
        return service.reject_execution_plan(
            args.project_id, args.plan_id, args.actor, args.reason)
    if args.group == "status":
        return service.get_execution_status(args.project_id, args.plan_id)
    if args.group == "list":
        return service.list_executions(args.project_id)
    return service.cancel_execution(
        args.project_id, args.plan_id, args.actor, args.reason)


def _encode(value):
    if hasattr(value, "__dataclass_fields__"):
        return _encode(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_encode(item) for item in value]
    return value


def _human(value):
    if isinstance(value, list):
        return "\n".join(str(item) for item in value) or "none"
    if isinstance(value, dict):
        return "\n".join(f"{key}: {value[key]}" for key in sorted(value))
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
