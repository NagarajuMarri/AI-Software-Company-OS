"""Managed Product Planning CLI."""

import argparse
import json
from dataclasses import asdict

from runtime.exceptions import RuntimeDomainError
from runtime.knowledge import KnowledgeStore, ProjectKnowledgeEngine
from runtime.planning import *
from runtime.project_manager import AIProjectManager, ManagerStateStore
from runtime.projects import FileProjectRegistry


def build_parser():
    parser = argparse.ArgumentParser(prog="ascos")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--json", action="store_true")
    planning = parser.add_subparsers(dest="group", required=True).add_parser("planning")
    groups = planning.add_subparsers(dest="entity", required=True)
    request = groups.add_parser("request").add_subparsers(dest="action", required=True)
    create = request.add_parser("create")
    create.add_argument("project_id"); create.add_argument("request_id")
    create.add_argument("--title", required=True); create.add_argument("--objective", required=True)
    create.add_argument("--business-context", required=True); create.add_argument("--requested-by", required=True)
    create.add_argument("--acceptance", action="append", required=True)
    create.add_argument("--capability", action="append", default=[])
    create.add_argument("--constraint", action="append", default=[])
    create.add_argument("--out-of-scope", action="append", default=[])
    create.add_argument("--priority", choices=[x.value for x in ChangePriority], default="NORMAL")
    create.add_argument("--correlation-id", default="")
    for action in ("show", "list"):
        command = request.add_parser(action); command.add_argument("project_id")
        if action == "show": command.add_argument("request_id")
    context = groups.add_parser("context").add_subparsers(dest="action", required=True)
    build = context.add_parser("build"); build.add_argument("project_id"); build.add_argument("request_id")
    proposal = groups.add_parser("proposal").add_subparsers(dest="action", required=True)
    for action in ("generate", "show", "approve", "reject", "materialise"):
        command = proposal.add_parser(action); command.add_argument("project_id")
        command.add_argument("proposal_id" if action != "generate" else "request_id")
        if action in {"approve", "reject"}: command.add_argument("--actor", required=True)
        if action == "reject": command.add_argument("--reason", required=True)
    listing = proposal.add_parser("list"); listing.add_argument("project_id")
    status = groups.add_parser("status"); status.add_argument("project_id")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    registry = FileProjectRegistry(args.registry)
    root = args.state_root
    service = ManagedProductPlanningService(
        registry, PlanningStore(root),
        lambda project_id: ProjectKnowledgeEngine.load(project_id, registry, KnowledgeStore(root)),
        lambda project_id: AIProjectManager.load(project_id, registry, ManagerStateStore(root)),
        DeterministicPlanningProvider())
    try:
        result = _execute(service, args)
        value = _encode(result)
        print(json.dumps(value, sort_keys=True) if args.json else _human(value))
        return 0
    except (RuntimeDomainError, ValueError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True) if args.json else f"error: {error}")
        return 2


def _execute(service, args):
    if args.entity == "request":
        if args.action == "create":
            return service.create_request(ManagedProductChangeRequest(
                args.request_id, args.project_id, args.title, args.objective,
                args.business_context, tuple(args.capability), tuple(args.acceptance),
                tuple(args.constraint), tuple(args.out_of_scope), ChangePriority(args.priority),
                args.requested_by, correlation_id=args.correlation_id))
        if args.action == "show": return service.get_request(args.project_id, args.request_id)
        return service.list_requests(args.project_id)
    if args.entity == "context":
        context = service.build_context(args.project_id, args.request_id)
        return {"project_id": context.project_id, "request_id": context.request.request_id,
                "files": len(context.relevant_files), "symbols": len(context.relevant_symbols)}
    if args.entity == "status": return service.get_planning_status(args.project_id)
    if args.action == "generate": return service.generate_proposal(args.project_id, args.request_id)
    if args.action == "show": return service.get_proposal(args.project_id, args.proposal_id)
    if args.action == "list": return service.list_proposals(args.project_id)
    if args.action == "approve":
        return service.approve_proposal(args.project_id, args.proposal_id, args.actor)
    if args.action == "reject":
        return service.reject_proposal(args.project_id, args.proposal_id, args.actor, args.reason)
    return service.materialise_approved_proposal(args.project_id, args.proposal_id)


def _encode(value):
    from datetime import datetime
    from enum import Enum
    if hasattr(value, "__dataclass_fields__"): return _encode(asdict(value))
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, Enum): return value.value
    if isinstance(value, dict): return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [_encode(v) for v in value]
    return value


def _human(value):
    if isinstance(value, list): return "\n".join(str(x) for x in value) or "none"
    if isinstance(value, dict): return "\n".join(f"{key}: {value[key]}" for key in sorted(value))
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
