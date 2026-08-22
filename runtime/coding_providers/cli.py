"""Secret-safe operator CLI for persisted coding-provider operations."""

import argparse
import json

from runtime.coding_providers.errors import CodingProviderError


def build_parser():
    parser = argparse.ArgumentParser(prog="ascos-provider")
    parser.add_argument("--project-id", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("provider-list")
    validate = sub.add_parser("provider-validate")
    validate.add_argument("provider_id")
    for name in ("provider-status", "provider-poll", "provider-progress",
                 "provider-result", "provider-reconcile"):
        command = sub.add_parser(name)
        command.add_argument("operation_id")
    submit = sub.add_parser("provider-submit")
    submit.add_argument("operation_id")
    submit.add_argument("--allow-live-provider", action="store_true")
    submit.add_argument("--confirm-usage-consumption", action="store_true")
    cancel = sub.add_parser("provider-cancel")
    cancel.add_argument("operation_id")
    cancel.add_argument("--actor", required=True)
    cancel.add_argument("--reason", required=True)
    return parser


def run_provider_command(service, registry, store, argv, *, prepared_requests=None):
    args = build_parser().parse_args(argv)
    prepared_requests = prepared_requests or {}
    if args.command == "provider-list":
        return {"providers": [
            {"provider_id": identifier, "enabled": enabled,
             "capabilities": [item.value for item in capabilities]}
            for identifier, enabled, capabilities in registry.list()]}
    if args.command == "provider-validate":
        provider = registry.get(args.provider_id)
        provider.validate_configuration()
        return {"provider_id": args.provider_id, "healthy": True}
    if args.command == "provider-status":
        operation = store.load_operation(args.project_id, args.operation_id)
        return {"operation_id": args.operation_id, "state": operation.state.value}
    if args.command == "provider-progress":
        return {"events": [
            {"sequence": item.sequence, "type": item.event_type,
             "message": item.message}
            for item in store.load_progress(args.project_id, args.operation_id)]}
    if args.command == "provider-poll":
        operation = service.poll(args.project_id, args.operation_id)
        return {"operation_id": args.operation_id, "state": operation.state.value}
    if args.command == "provider-result":
        result = service.result(args.project_id, args.operation_id)
        return {"provider_task_id": result.provider_task_id,
                "status": result.status.value, "summary": result.summary}
    if args.command == "provider-submit":
        try:
            request = prepared_requests[args.operation_id]
        except KeyError as error:
            raise CodingProviderError(
                "Prepared bounded request is unavailable in this process") from error
        operation = service.submit(
            args.project_id, args.operation_id, request,
            allow_live_provider=args.allow_live_provider,
            confirm_usage_consumption=args.confirm_usage_consumption)
        return {"operation_id": args.operation_id, "state": operation.state.value}
    if args.command == "provider-cancel":
        operation = service.cancel(
            args.project_id, args.operation_id, actor=args.actor, reason=args.reason)
        return {"operation_id": args.operation_id, "state": operation.state.value}
    operation = service.reconcile(args.project_id, args.operation_id)
    return {"operation_id": args.operation_id, "state": operation.state.value}


def print_result(value):
    print(json.dumps(value, sort_keys=True))
