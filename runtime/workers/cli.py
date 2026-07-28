"""Bounded, operator-started worker administration CLI."""
import argparse
import json


def build_parser():
    parser = argparse.ArgumentParser(prog="ascos-worker")
    parser.add_argument("--json", action="store_true")
    groups = parser.add_subparsers(dest="group", required=True)
    worker = groups.add_parser("worker").add_subparsers(dest="action", required=True)
    for action in ("run-once", "run", "status", "list", "scan-stale"):
        worker.add_parser(action)
    stop = worker.add_parser("request-stop")
    stop.add_argument("worker_instance_id")
    stop.add_argument("--actor", required=True)
    stop.add_argument("--reason", required=True)
    provider = groups.add_parser("provider").add_subparsers(dest="action", required=True)
    provider.add_parser("health")
    for action in ("disable", "enable", "probe", "reset-circuit"):
        command = provider.add_parser(action)
        command.add_argument("provider_id")
        command.add_argument("--actor", required=True)
        command.add_argument("--reason", required=True)
    groups.add_parser("postgres").add_subparsers(
        dest="action", required=True
    ).add_parser("verify")
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    response = {
        "ok": True, "group": arguments.group, "action": arguments.action,
        "message": "Command accepted; composition must be supplied by the host application.",
    }
    print(json.dumps(response, sort_keys=True) if arguments.json else response["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
