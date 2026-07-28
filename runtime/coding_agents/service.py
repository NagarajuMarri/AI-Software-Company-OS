class CodingAgentService:
    def __init__(self, registry):
        self.registry = registry

    def execute(self, request, capabilities):
        provider = self.registry.choose_compatible_provider(capabilities)
        provider_task_id = provider.submit_task(request)
        progress = provider.get_progress(provider_task_id)
        for expected, item in enumerate(progress, start=1):
            if item.task_id != request.task_id or item.sequence != expected:
                raise ValueError("Provider progress sequence is invalid")
        result = provider.get_result(provider_task_id)
        if result.task_id != request.task_id:
            raise ValueError("Provider result belongs to another task")
        return (
            provider,
            provider_task_id,
            progress,
            result,
        )
