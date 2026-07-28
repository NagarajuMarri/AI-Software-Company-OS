import sys
import threading
import time

import pytest

from runtime.tools import CommandRequest, LocalCommandRunner
from runtime.tools.exceptions import (
    CommandCancelledError, CommandTimeoutError, InvalidCommandError,
)


def runner(tmp_path, limit=64000):
    return LocalCommandRunner(
        tmp_path, allowed_executables={"python"},
        allowed_environment={"SAFE"}, max_output_bytes=limit,
    )


def test_command_success_and_nonzero_exit(tmp_path):
    ok = runner(tmp_path).execute(CommandRequest(
        "python", ("-c", "print('ok')"), tmp_path
    ))
    failed = runner(tmp_path).execute(CommandRequest(
        "python", ("-c", "raise SystemExit(7)"), tmp_path
    ))
    assert ok.exit_code == 0 and ok.stdout.strip() == "ok"
    assert failed.exit_code == 7


def test_timeout_kills_process(tmp_path):
    with pytest.raises(CommandTimeoutError):
        runner(tmp_path).execute(CommandRequest(
            "python", ("-c", "import time;time.sleep(5)"), tmp_path,
            timeout_seconds=.05,
        ))


def test_cancellation_and_executable_allowlist(tmp_path):
    cancellation = threading.Event()
    cancellation.set()
    with pytest.raises(CommandCancelledError):
        runner(tmp_path).execute(
            CommandRequest("python", (), tmp_path), cancellation=cancellation
        )
    with pytest.raises(InvalidCommandError):
        runner(tmp_path).execute(CommandRequest("powershell", (), tmp_path))


def test_output_is_bounded_and_shell_metacharacter_is_literal(tmp_path):
    result = runner(tmp_path, 10).execute(CommandRequest(
        "python", ("-c", "print('x'*100)"), tmp_path
    ))
    literal = runner(tmp_path).execute(CommandRequest(
        "python", ("-c", "import sys;print(sys.argv[1])", ";echo injected"), tmp_path
    ))
    assert result.output_truncated and len(result.stdout.encode()) <= 10
    assert literal.stdout.strip() == ";echo injected"


def test_secret_environment_and_nul_are_rejected(tmp_path):
    with pytest.raises(InvalidCommandError):
        runner(tmp_path).execute(CommandRequest(
            "python", (), tmp_path, {"API_TOKEN": "secret"}
        ))
    with pytest.raises(InvalidCommandError):
        runner(tmp_path).execute(CommandRequest(
            "python", ("bad\0argument",), tmp_path
        ))


def test_allowed_environment_value_is_redacted_from_output(tmp_path):
    result = runner(tmp_path).execute(CommandRequest(
        "python",
        ("-c", "import os;print(os.environ['SAFE'])"),
        tmp_path,
        {"SAFE": "credential-like-value"},
    ))
    assert result.stdout.strip() == "[REDACTED]"
    assert "credential-like-value" not in repr(result)


def test_live_cancellation_terminates_child(tmp_path):
    cancellation = threading.Event()
    timer = threading.Timer(.05, cancellation.set)
    timer.start()
    try:
        with pytest.raises(CommandCancelledError):
            runner(tmp_path).execute(
                CommandRequest(
                    "python", ("-c", "import time;time.sleep(5)"),
                    tmp_path, timeout_seconds=10,
                ),
                cancellation=cancellation,
            )
    finally:
        timer.cancel()


def test_working_directory_outside_workspace_is_rejected(tmp_path):
    outside = tmp_path.parent / "outside-command-test"
    outside.mkdir(exist_ok=True)
    from runtime.tools.exceptions import WorkspaceSecurityError
    with pytest.raises(WorkspaceSecurityError):
        runner(tmp_path).execute(CommandRequest("python", (), outside))


def test_unavailable_allowlisted_executable_is_structured(tmp_path):
    local = LocalCommandRunner(
        tmp_path, allowed_executables={"definitely_missing_executable"}
    )
    with pytest.raises(InvalidCommandError, match="unavailable"):
        local.execute(CommandRequest(
            "definitely_missing_executable", (), tmp_path
        ))
