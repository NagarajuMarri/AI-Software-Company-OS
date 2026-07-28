import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.workers import WorkerConfiguration
from runtime.workers.lifecycle import start_process


def main():
    configuration = WorkerConfiguration(
        "demo-runtime", "demo-worker", "sqlite-demo-reference",
        ("DEMO_DISPATCH",), ("deterministic-provider",),
        polling_interval_seconds=0, maximum_operations=2, maximum_idle_cycles=1,
    )
    process, results = start_process(
        configuration, "runtime.workers.demo_composition:create_demo_worker"
    )
    process.join(timeout=10)
    if process.is_alive():
        raise RuntimeError("Worker process exceeded bounded runtime")
    if process.exitcode:
        raise RuntimeError("Worker process failed")
    outcome = results.get(timeout=2)
    print(f"processed={outcome['processed']} child_exit={process.exitcode}")


if __name__ == "__main__": main()
