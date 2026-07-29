import json
from dataclasses import replace

import pytest

from runtime.exceptions import ProjectNotFoundError, ValidationError
from runtime.project_manager import *
from runtime.project_manager.errors import *
from runtime.project_manager.cli import main as cli_main
from runtime.projects import FileProjectRegistry, InMemoryProjectRegistry, ManagedProject


@pytest.fixture
def registry():
    return InMemoryProjectRegistry((ManagedProject(
        "product", "Product", "Managed test product",
        "https://example.com/product", "main"),))


@pytest.fixture
def manager(tmp_path, registry):
    return AIProjectManager.initialize("product", registry, ManagerStateStore(tmp_path))


def setup_active(manager):
    manager.create_milestone("m1", "Foundation")
    manager.start_milestone("m1")
    return manager


@pytest.fixture
def active(manager):
    return setup_active(manager)


def test_initialization_validates_registry_and_does_not_write(tmp_path, registry):
    store = ManagerStateStore(tmp_path)
    manager = AIProjectManager.initialize("product", registry, store)
    assert manager.current_state().project_id == "product"
    assert not store.exists("product")
    with pytest.raises(ProjectNotFoundError):
        AIProjectManager.initialize("missing", registry, store)


def test_milestones_are_ordered_and_unique(manager):
    first = manager.create_milestone("a", "A")
    second = manager.create_milestone("b", "B")
    assert manager.current_state().milestones == (first, second)
    with pytest.raises(DuplicateMilestoneError):
        manager.create_milestone("a", "Again")


def test_milestone_dependencies_are_validated(manager):
    with pytest.raises(UnknownDependencyError):
        manager.create_milestone("m", "M", dependencies=("missing",))
    with pytest.raises(ValidationError):
        Milestone("m", "M", dependencies=("m",))


def test_only_one_milestone_can_be_active(manager):
    manager.create_milestone("a", "A")
    manager.create_milestone("b", "B")
    started = manager.start_milestone("a")
    assert started.started_at is not None
    with pytest.raises(InvalidMilestoneTransitionError):
        manager.start_milestone("b")


def test_milestone_dependency_must_be_complete(manager):
    manager.create_milestone("a", "A")
    manager.create_milestone("b", "B", dependencies=("a",))
    with pytest.raises(InvalidMilestoneTransitionError):
        manager.start_milestone("b")


def test_task_creation_validates_identity_and_dependencies(manager):
    manager.create_milestone("m", "M")
    task = manager.create_task("m", "a", "A")
    assert task.status == TaskStatus.TODO
    with pytest.raises(DuplicateTaskError):
        manager.create_task("m", "a", "Again")
    with pytest.raises(UnknownDependencyError):
        manager.create_task("m", "b", "B", dependencies=("missing",))
    with pytest.raises(ValidationError):
        Task("x", "X", dependencies=("x",))


def test_task_dependency_duplicates_rejected():
    with pytest.raises(ValidationError):
        Task("x", "X", dependencies=("a", "a"))


def test_blocked_task_requires_reason():
    with pytest.raises(ValidationError):
        Task("x", "X", status=TaskStatus.BLOCKED)


def test_start_and_complete_task(active):
    task = active.create_task("m1", "a", "A")
    started = active.start_task(task.task_id)
    assert started.status == TaskStatus.IN_PROGRESS
    assert started.started_at is not None
    completed = active.complete_task(task.task_id, actual_effort="1h")
    assert completed.status == TaskStatus.DONE
    assert completed.completed_at is not None
    assert completed.actual_effort == "1h"


@pytest.mark.parametrize("started,expected", [(False, TaskStatus.TODO), (True, TaskStatus.IN_PROGRESS)])
def test_block_and_unblock_policy(manager, started, expected):
    setup_active(manager)
    manager.create_task("m1", "a", "A")
    if started:
        manager.start_task("a")
    blocked = manager.block_task("a", "Waiting")
    assert blocked.blocker_reason == "Waiting"
    unblocked = manager.unblock_task("a")
    assert unblocked.status == expected
    assert unblocked.blocker_reason is None


def test_block_requires_nonblank_reason(active):
    active.create_task("m1", "a", "A")
    with pytest.raises(ValidationError):
        active.block_task("a", " ")


def test_skip_task_counts_as_complete(active):
    active.create_task("m1", "a", "A")
    skipped = active.skip_task("a")
    assert skipped.status == TaskStatus.SKIPPED
    assert skipped.completed_at is not None
    assert active.progress().percentage == 100


def test_completion_requires_dependencies(active):
    active.create_task("m1", "a", "A")
    active.create_task("m1", "b", "B", dependencies=("a",))
    with pytest.raises(UnmetTaskDependenciesError):
        active.complete_task("b")
    active.complete_task("a")
    assert active.complete_task("b").status == TaskStatus.DONE


@pytest.mark.parametrize("operation", ["start_task", "complete_task", "skip_task"])
def test_terminal_task_transitions_are_rejected(active, operation):
    active.create_task("m1", "a", "A")
    active.complete_task("a")
    with pytest.raises(InvalidTaskTransitionError):
        getattr(active, operation)("a")


def test_milestone_completion_requires_finished_tasks(active):
    active.create_task("m1", "a", "A")
    with pytest.raises(IncompleteMilestoneError):
        active.complete_milestone("m1")
    active.skip_task("a")
    completed = active.complete_milestone("m1")
    assert completed.completed_at is not None
    assert active.current_state().active_milestone_id is None


def test_empty_completed_milestone_reports_100(manager):
    manager.create_milestone("m", "M")
    manager.start_milestone("m")
    manager.complete_milestone("m")
    assert manager.milestone_progress("m").percentage == 100


def test_empty_project_reports_zero(manager):
    progress = manager.progress()
    assert progress.total == 0
    assert progress.percentage == 0


def test_progress_counts_all_statuses(active):
    for task_id in "abcde":
        active.create_task("m1", task_id, task_id)
    active.complete_task("a")
    active.skip_task("b")
    active.start_task("c")
    active.block_task("d", "blocked")
    progress = active.progress()
    assert (progress.total, progress.completed, progress.skipped, progress.blocked,
            progress.in_progress, progress.remaining, progress.percentage) == (5, 1, 1, 1, 1, 3, 40)


def test_progress_rounding_is_integer_and_stable(active):
    for task_id in "abc":
        active.create_task("m1", task_id, task_id)
    active.complete_task("a")
    assert active.progress().percentage == 33


def test_planner_uses_milestone_order_and_unlocks(active):
    active.create_task("m1", "a", "A")
    active.create_task("m1", "b", "B", dependencies=("a",))
    active.create_task("m1", "c", "C")
    assert [x.task_id for x in active.next_tasks()] == ["a", "c"]
    active.complete_task("a")
    assert [x.task_id for x in active.next_tasks()] == ["b", "c"]


def test_planner_excludes_non_todo_and_does_not_mutate(active):
    for task_id in "abcd":
        active.create_task("m1", task_id, task_id)
    active.start_task("a")
    active.complete_task("b")
    active.skip_task("c")
    active.block_task("d", "blocked")
    before = active.current_state()
    assert active.next_tasks() == ()
    assert active.current_state() == before


def test_planner_without_active_milestone_is_empty(manager):
    manager.create_milestone("m", "M")
    manager.create_task("m", "a", "A")
    assert manager.next_tasks() == ()


def test_records_are_structured_and_ordered(manager):
    manager.add_decision("d", "Use JSON", "Portable")
    manager.add_note("n", "Sample")
    manager.add_risk("r", "Delay", "Schedule", RiskSeverity.MEDIUM)
    updated = manager.update_risk("r", status=RiskStatus.MITIGATED, mitigation="Buffer")
    assert updated.status == RiskStatus.MITIGATED
    assert manager.current_state().decisions[0].decision_id == "d"


def test_save_load_round_trip_and_deterministic_json(tmp_path, registry):
    store = ManagerStateStore(tmp_path)
    manager = AIProjectManager.initialize("product", registry, store)
    setup_active(manager).create_task("m1", "a", "A", metadata={"z": 1})
    manager.save()
    first = store.path_for("product").read_text(encoding="utf-8")
    loaded = AIProjectManager.load("product", registry, store)
    assert loaded.current_state() == manager.current_state()
    loaded.save()
    assert store.path_for("product").read_text(encoding="utf-8") == first
    assert json.loads(first)["schema_version"] == 1
    assert not list(store.path_for("product").parent.glob("*.tmp"))


def test_missing_corrupt_and_future_state(tmp_path, registry):
    store = ManagerStateStore(tmp_path)
    with pytest.raises(ManagerStateNotFoundError):
        AIProjectManager.load("product", registry, store)
    path = store.path_for("product")
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ManagerStateCorruptError):
        AIProjectManager.load("product", registry, store)
    path.write_text('{"schema_version": 99}', encoding="utf-8")
    with pytest.raises(UnsupportedManagerSchemaError):
        AIProjectManager.load("product", registry, store)


def test_storage_is_project_isolated(tmp_path):
    store = ManagerStateStore(tmp_path)
    assert store.path_for("a") != store.path_for("b")
    assert "projects" in store.path_for("a").parts


def test_failed_mutation_is_atomic(active):
    active.create_task("m1", "a", "A")
    active.create_task("m1", "b", "B", dependencies=("a",))
    before = active.current_state()
    with pytest.raises(UnmetTaskDependenciesError):
        active.complete_task("b")
    assert active.current_state() == before


def test_cli_initialise_read_and_mutate(tmp_path, capsys):
    registry_path = tmp_path / "registry.json"
    FileProjectRegistry(registry_path).register(ManagedProject(
        "cli", "CLI", "CLI product", "https://example.com/cli", "main"))
    prefix = ["--registry", str(registry_path), "--state-root", str(tmp_path / "state")]
    assert cli_main(prefix + ["project", "init-manager", "cli"]) == 0
    assert "initialised=True" in capsys.readouterr().out
    assert cli_main(prefix + ["project", "milestone", "add", "cli", "m", "Milestone"]) == 0
    assert cli_main(prefix + ["project", "task", "add", "cli", "m", "t", "Task"]) == 0
    assert cli_main(prefix + ["project", "milestone", "start", "cli", "m"]) == 0
    assert cli_main(prefix + ["--json", "project", "next", "cli"]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])[0]["task_id"] == "t"


def test_cli_expected_error_has_nonzero_exit_without_traceback(tmp_path, capsys):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text('{"projects": [], "schema_version": 1}', encoding="utf-8")
    result = cli_main(["--registry", str(registry_path), "--state-root", str(tmp_path),
                       "project", "status", "missing"])
    assert result == 2
    assert capsys.readouterr().out.startswith("error:")
