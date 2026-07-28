"""Real GitHub adapter boundary around an injected operation callable."""

from runtime.integrations.github.exceptions import ExternalProviderUnavailableError


class CallableGitHubProvider:
    def __init__(self, operation_client):
        if not callable(operation_client):
            raise TypeError("operation_client must be callable")
        self._client = operation_client

    def invoke(self, operation: str, request: dict):
        try:
            result = self._client(operation, dict(request))
        except Exception as error:
            raise ExternalProviderUnavailableError(
                f"GitHub operation {operation!r} failed"
            ) from error
        if not isinstance(result, dict):
            raise ExternalProviderUnavailableError(
                "GitHub adapter returned an invalid response"
            )
        return dict(result)
