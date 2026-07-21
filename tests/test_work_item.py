from runtime.models.lifecycle import LifecycleState
from runtime.models.work_item import WorkItem


def test_work_item_defaults_and_state_change() -> None:
    item = WorkItem(id="wi-002", title="Assess readiness", description="Check readiness")
    assert item.lifecycle_state == LifecycleState.CREATED

    item.change_state(LifecycleState.READY)
    assert item.lifecycle_state == LifecycleState.READY
