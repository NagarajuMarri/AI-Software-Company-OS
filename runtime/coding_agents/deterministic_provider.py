from datetime import datetime, timezone

from runtime.coding_agents.exceptions import CodingAgentTaskError
from runtime.coding_agents.models import (
    CodingAgentProgress,
    CodingAgentResultStatus,
    CodingAgentTaskResult,
)


class DeterministicCodingAgentProvider:
    def __init__(
        self,
        provider_id="deterministic",
        *,
        capabilities=("python", "git"),
        priority=100,
        outcomes=(CodingAgentResultStatus.SUCCEEDED,),
        available=True,
    ):
        self.provider_id = provider_id
        self.priority = priority
        self._capabilities = tuple(capabilities)
        self._outcomes = list(outcomes)
        self._available = available
        self._tasks = {}

    def supported_capabilities(self):
        return self._capabilities

    def is_available(self):
        return self._available

    def submit_task(self, request):
        provider_task_id = f"{self.provider_id}:{request.task_id}:{len(self._tasks)+1}"
        status = (
            self._outcomes.pop(0)
            if self._outcomes else CodingAgentResultStatus.SUCCEEDED
        )
        now = datetime.now(timezone.utc)
        progress = (
            CodingAgentProgress(request.task_id, 1, "ANALYSIS", "Task accepted", now),
            CodingAgentProgress(request.task_id, 2, "TEST", "Checks recorded", now),
        )
        result = CodingAgentTaskResult(
            request.task_id, provider_task_id, status,
            "Deterministic task result", ("change.txt",) if status == CodingAgentResultStatus.SUCCEEDED else (),
            None, ("deterministic checks",), (), None if status == CodingAgentResultStatus.SUCCEEDED else status.value,
            now, now,
        )
        self._tasks[provider_task_id] = (progress, result)
        return provider_task_id

    def get_task_status(self, provider_task_id):
        return self.get_result(provider_task_id).status

    def get_progress(self, provider_task_id):
        self._require(provider_task_id)
        return self._tasks[provider_task_id][0]

    def get_result(self, provider_task_id):
        self._require(provider_task_id)
        return self._tasks[provider_task_id][1]

    def cancel_task(self, provider_task_id):
        self._require(provider_task_id)
        progress, result = self._tasks[provider_task_id]
        now = datetime.now(timezone.utc)
        self._tasks[provider_task_id] = (
            progress,
            CodingAgentTaskResult(
                result.task_id, result.provider_task_id,
                CodingAgentResultStatus.CANCELLED, "Cancelled", (), None, (), (),
                "CANCELLED", result.started_at, now,
            ),
        )

    def _require(self, identifier):
        if identifier not in self._tasks:
            raise CodingAgentTaskError("Provider task was not found")
