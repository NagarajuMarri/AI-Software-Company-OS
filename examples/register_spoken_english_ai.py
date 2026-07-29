"""Register ASCOS's first managed product without modifying its checkout."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.projects import FileProjectRegistry, register_spoken_english_ai


def main() -> None:
    with TemporaryDirectory() as directory:
        registry = FileProjectRegistry(Path(directory) / "projects.json")
        managed = register_spoken_english_ai(registry)
        restarted = FileProjectRegistry(registry.path)
        print(
            f"registered={managed.project_id} "
            f"repository={restarted.get(managed.project_id).repository_url}"
        )


if __name__ == "__main__":
    main()
