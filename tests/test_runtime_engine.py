from runtime.engine.runtime_engine import RuntimeEngine
from runtime.models.lifecycle import LifecycleState


def test_runtime_engine_creates_and_retrieves_work_package() -> None:
    engine = RuntimeEngine()
    package = engine.create_work_package(
        id="wp-100",
        title="Runtime foundation",
        description="Core runtime",
        owner="platform",
    )

    item = engine.add_work_item(
        package_id="wp-100",
        id="wi-100",
        title="Initialize runtime",
        description="Initialize runtime components",
    )

    assert item.lifecycle_state == LifecycleState.CREATED
    assert engine.get_work_package("wp-100").title == "Runtime foundation"

    engine.change_work_item_state("wp-100", "wi-100", LifecycleState.READY)
    updated = engine.get_work_package("wp-100").work_items[0]
    assert updated.lifecycle_state == LifecycleState.READY
