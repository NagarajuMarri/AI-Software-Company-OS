"""Register and reload a generic managed product."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.projects import FileProjectRegistry, ManagedProject


def main() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "projects.json"
        registry = FileProjectRegistry(path)
        registry.register(
            ManagedProject(
                project_id="example-product",
                name="Example Product",
                description="Portable managed product registration example",
                repository_url="https://example.com/example-product",
                default_branch="main",
                tags=("example",),
            )
        )
        print(f"registered={FileProjectRegistry(path).get('example-product').project_id}")


if __name__ == "__main__":
    main()
