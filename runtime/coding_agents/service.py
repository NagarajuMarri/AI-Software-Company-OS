class CodingAgentService:
    def __init__(self, registry):
        self.registry = registry

    def execute(self, request, capabilities):
        provider = self.registry.choose_compatible_provider(capabilities)
        provider_task_id = provider.submit_task(request)
        return (
            provider,
            provider_task_id,
            provider.get_progress(provider_task_id),
            provider.get_result(provider_task_id),
        )
