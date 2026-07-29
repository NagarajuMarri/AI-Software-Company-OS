"""Command-line access to persisted project-manager state."""

import argparse
import json

from runtime.exceptions import RuntimeDomainError
from runtime.project_manager import AIProjectManager, ManagerStateStore
from runtime.projects import FileProjectRegistry


def build_parser():
    parser = argparse.ArgumentParser(prog="ascos")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--json", action="store_true")
    project = parser.add_subparsers(dest="group", required=True).add_parser("project")
    actions = project.add_subparsers(dest="action", required=True)
    for action in ("init-manager", "status", "progress", "next", "milestones", "tasks"):
        command = actions.add_parser(action)
        command.add_argument("project_id")
    milestone = actions.add_parser("milestone")
    milestone_actions = milestone.add_subparsers(dest="operation", required=True)
    add = milestone_actions.add_parser("add")
    add.add_argument("project_id"); add.add_argument("milestone_id"); add.add_argument("title")
    start = milestone_actions.add_parser("start")
    start.add_argument("project_id"); start.add_argument("milestone_id")
    complete = milestone_actions.add_parser("complete")
    complete.add_argument("project_id"); complete.add_argument("milestone_id")
    task = actions.add_parser("task")
    task_actions = task.add_subparsers(dest="operation", required=True)
    add = task_actions.add_parser("add")
    add.add_argument("project_id"); add.add_argument("milestone_id")
    add.add_argument("task_id"); add.add_argument("title")
    add.add_argument("--depends-on", action="append", default=[])
    for operation in ("start", "complete", "skip", "unblock"):
        command = task_actions.add_parser(operation)
        command.add_argument("project_id"); command.add_argument("task_id")
    block = task_actions.add_parser("block")
    block.add_argument("project_id"); block.add_argument("task_id")
    block.add_argument("--reason", required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    registry, store = FileProjectRegistry(args.registry), ManagerStateStore(args.state_root)
    try:
        if args.action == "init-manager":
            manager = AIProjectManager.initialize(args.project_id, registry, store)
            manager.save()
            result = {"project_id": args.project_id, "initialised": True}
        else:
            manager = AIProjectManager.load(args.project_id, registry, store)
            result = _execute(manager, args)
            if args.action in {"milestone", "task"}:
                manager.save()
        print(json.dumps(result, sort_keys=True) if args.json else _human(result))
        return 0
    except (RuntimeDomainError, ValueError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True) if args.json else f"error: {error}")
        return 2


def _execute(manager, args):
    if args.action == "status":
        state = manager.current_state()
        return {"project_id": state.project_id, "status": state.status.value,
                "active_milestone_id": state.active_milestone_id}
    if args.action == "progress":
        return manager.progress().__dict__
    if args.action == "next":
        return [{"task_id": x.task_id, "title": x.title} for x in manager.next_tasks()]
    if args.action == "milestones":
        return [{"milestone_id": x.milestone_id, "title": x.title,
                 "status": x.status.value} for x in manager.current_state().milestones]
    if args.action == "tasks":
        return [{"task_id": x.task_id, "title": x.title, "status": x.status.value}
                for x in manager.current_state().tasks]
    if args.action == "milestone":
        if args.operation == "add":
            item = manager.create_milestone(args.milestone_id, args.title)
        elif args.operation == "start":
            item = manager.start_milestone(args.milestone_id)
        else:
            item = manager.complete_milestone(args.milestone_id)
        return {"milestone_id": item.milestone_id, "status": item.status.value}
    if args.operation == "add":
        item = manager.create_task(args.milestone_id, args.task_id, args.title,
                                   dependencies=tuple(args.depends_on))
    elif args.operation == "start": item = manager.start_task(args.task_id)
    elif args.operation == "complete": item = manager.complete_task(args.task_id)
    elif args.operation == "skip": item = manager.skip_task(args.task_id)
    elif args.operation == "block": item = manager.block_task(args.task_id, args.reason)
    else: item = manager.unblock_task(args.task_id)
    return {"task_id": item.task_id, "status": item.status.value}


def _human(value):
    if isinstance(value, list):
        return "\n".join(" ".join(f"{k}={v}" for k, v in row.items()) for row in value) or "none"
    return " ".join(f"{key}={value[key]}" for key in sorted(value))


if __name__ == "__main__":
    raise SystemExit(main())
