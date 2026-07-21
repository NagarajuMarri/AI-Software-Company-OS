from runtime.models.artifact import Artifact
from runtime.models.lifecycle import LifecycleState


def test_artifact_holds_identity_and_version() -> None:
    artifact = Artifact(id="art-001", name="spec", type="document", version="1.0")

    assert artifact.lifecycle_state == LifecycleState.CREATED
    assert artifact.version == "1.0"

    artifact.change_state(LifecycleState.APPROVED)
    assert artifact.lifecycle_state == LifecycleState.APPROVED
