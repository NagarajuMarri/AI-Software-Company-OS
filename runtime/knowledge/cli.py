"""Knowledge Engine CLI."""

import argparse
import json
from dataclasses import asdict

from runtime.exceptions import RuntimeDomainError
from runtime.knowledge import KnowledgeStore, ProjectKnowledgeEngine
from runtime.projects import FileProjectRegistry


def build_parser():
    parser = argparse.ArgumentParser(prog="ascos")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--json", action="store_true")
    knowledge = parser.add_subparsers(dest="group", required=True).add_parser("knowledge")
    commands = knowledge.add_subparsers(dest="action", required=True)
    for action in ("scan", "summary", "stats", "files", "symbols", "dependencies"):
        command = commands.add_parser(action); command.add_argument("project_id")
    find = commands.add_parser("find")
    find.add_argument("project_id"); find.add_argument("query")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    registry, store = FileProjectRegistry(args.registry), KnowledgeStore(args.state_root)
    try:
        if args.action == "scan":
            engine = ProjectKnowledgeEngine.create(args.project_id, registry, store)
            engine.scan(); engine.save(); result = engine.summary()
        else:
            engine = ProjectKnowledgeEngine.load(args.project_id, registry, store)
            if args.action == "summary": result = engine.summary()
            elif args.action == "stats": result = asdict(engine.statistics())
            elif args.action == "files": result = [asdict(x) for x in engine.files()]
            elif args.action == "symbols": result = [asdict(x) for x in engine.symbols()]
            elif args.action == "dependencies": result = [asdict(x) for x in engine.dependencies()]
            else:
                result = {"files": [asdict(x) for x in engine.find_file(args.query)],
                          "symbols": [asdict(x) for x in engine.find_symbol(args.query)]}
        print(json.dumps(result, sort_keys=True) if args.json else _human(result))
        return 0
    except (RuntimeDomainError, ValueError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True) if args.json else f"error: {error}")
        return 2


def _human(value):
    if isinstance(value, list):
        return "\n".join(str(x) for x in value) or "none"
    return "\n".join(f"{key}: {value[key]}" for key in sorted(value))


if __name__ == "__main__":
    raise SystemExit(main())
