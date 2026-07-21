from runtime.models.lifecycle import LifecycleState
from runtime.models.work_package import WorkPackage
from runtime.models.work_item import WorkItem


def test_work_package_tracks_items_and_artifacts() -> None:
    package = WorkPackage(
        id="wp-001",
        title="Platform foundation",
        description="Foundation work package",
        owner="engineering",
    )

    item = WorkItem(id="wi-001", title="Define scope", description="Define initial scope")
    package.add_work_item(item)

    assert package.work_items[0].id == "wi-001"
    assert package.lifecycle_state == LifecycleState.CREATED

    package.add_artifact("artifact-001")
    assert len(package.artifacts) == 1
    assert package.artifacts[0] == "artifact-001"
