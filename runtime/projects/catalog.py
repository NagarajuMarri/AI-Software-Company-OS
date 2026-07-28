"""Approved managed-product registrations."""

from runtime.projects.models import ManagedProject, ProjectLifecycle

SPOKEN_ENGLISH_AI = ManagedProject(
    project_id="spoken-english-ai",
    name="Spoken English AI",
    description="AI-assisted spoken English learning product",
    repository_url="https://github.com/NagarajuMarri/spoken-english-ai",
    default_branch="main",
    lifecycle=ProjectLifecycle.ACTIVE,
    tags=("ai", "education", "managed-product"),
)


def register_spoken_english_ai(registry):
    """Register the first managed product without repository I/O."""

    return registry.register(SPOKEN_ENGLISH_AI)
