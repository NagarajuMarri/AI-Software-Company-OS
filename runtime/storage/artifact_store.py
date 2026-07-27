from __future__ import annotations

from typing import Dict, List

from runtime.exceptions import ArtifactNotFoundError, DuplicateArtifactError
from runtime.models.artifact import Artifact


class ArtifactStore:
    """In-memory store for managing artifacts."""

    def __init__(self) -> None:
        self._artifacts: Dict[str, Artifact] = {}

    def add_artifact(self, artifact: Artifact) -> Artifact:
        """Store an artifact by its identifier.

        Args:
            artifact: The artifact to store.

        Returns:
            The stored artifact.
        """
        if artifact.id in self._artifacts:
            raise DuplicateArtifactError(f"Artifact {artifact.id!r} already exists")
        self._artifacts[artifact.id] = artifact
        return artifact

    def get_artifact(self, artifact_id: str) -> Artifact:
        """Retrieve an artifact by identifier.

        Args:
            artifact_id: The artifact identifier.

        Returns:
            The stored artifact.

        Raises:
            ArtifactNotFoundError: If the artifact does not exist.
        """
        if artifact_id not in self._artifacts:
            raise ArtifactNotFoundError(f"Artifact {artifact_id!r} not found")
        return self._artifacts[artifact_id]

    def list_artifacts(self) -> List[Artifact]:
        """Return all stored artifacts.

        Returns:
            A list of artifacts in insertion order.
        """
        return list(self._artifacts.values())
