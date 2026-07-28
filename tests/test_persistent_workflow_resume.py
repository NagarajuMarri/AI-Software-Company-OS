import subprocess
import sys
from pathlib import Path


def test_persistent_resume_example(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "examples/persistent_workflow_resume.py",
            str(tmp_path),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "stage=RELEASED" in result.stdout
    assert "SOFTWARE_WORK_RELEASED" in result.stdout
