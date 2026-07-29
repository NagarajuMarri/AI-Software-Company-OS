# AI Project Manager

The AI Project Manager is a deterministic management layer over the Project
Registry. The registry remains the source of truth for project identity; manager
state references only its stable project ID and never writes to a product
repository.

## Model and lifecycle

Each project state contains ordered milestones and tasks plus lightweight
decisions, notes, and risks. Tasks move from `TODO` to `IN_PROGRESS`, `BLOCKED`,
`DONE`, or `SKIPPED`. Unblocking returns a previously started task to
`IN_PROGRESS`, otherwise to `TODO`, and clears its blocker reason. Completed
tasks are not reopened. Only one milestone is active. Empty milestones and
projects report 0% until explicitly completed.

Progress is an integer percentage: `(DONE + SKIPPED) * 100 // total`. A completed
milestone always reports 100%. The planner returns `TODO` tasks in active
milestone order when every dependency is `DONE` or `SKIPPED`; it never mutates
state.

## Persistence

`ManagerStateStore(root)` writes UTF-8, schema-versioned, sorted, indented JSON
atomically at `root/projects/<project-id>/manager.json`. Unknown versions,
malformed files, and missing state produce typed errors. Repository availability
does not affect this location.

## Python API

```python
store = ManagerStateStore(state_root)
manager = AIProjectManager.initialize("spoken-english-ai", registry, store)
manager.create_milestone("sample-foundation", "Sample foundation")
manager.create_task("sample-foundation", "inspect", "Inspect structure")
manager.start_milestone("sample-foundation")
manager.save()
```

See `examples/ai_project_manager.py` for dependency unlocking and reload.

## CLI

Commands use explicit ASCOS registry and state locations:

```text
python -m runtime.project_manager.cli --registry projects.json --state-root .ascos project init-manager spoken-english-ai
python -m runtime.project_manager.cli --registry projects.json --state-root .ascos project milestone add spoken-english-ai sample-foundation "Sample foundation"
python -m runtime.project_manager.cli --registry projects.json --state-root .ascos project task add spoken-english-ai sample-foundation inspect "Inspect structure"
python -m runtime.project_manager.cli --registry projects.json --state-root .ascos project milestone start spoken-english-ai sample-foundation
python -m runtime.project_manager.cli --registry projects.json --state-root .ascos --json project next spoken-english-ai
```

Read commands also include `status`, `progress`, `milestones`, and `tasks`;
task mutations include `start`, `complete`, `block`, `unblock`, and `skip`.
Expected domain failures return exit code 2 without a traceback.

## Limitations and extensions

This foundation has no LLM planning, autonomous execution, repository mutation,
deployment, interactive UI, or product roadmap assumptions. Future milestones
may place reviewed LLM recommendations and execution agents above this stable
API without changing its deterministic persistence and validation boundary.
