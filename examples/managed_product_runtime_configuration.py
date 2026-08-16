"""Build a deterministic managed-product runtime declaration without executing it."""

from datetime import datetime, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.managed_product_runtime import (  # noqa: E402
    CommandSpec,
    FileRuntimeConfigurationStore,
    ManagedProductRuntimeConfiguration,
    ManagedProductRuntimeConfigurationService,
    ManagedRuntimeService,
    OneShotCommand,
    ReadinessProbe,
    RuntimeEnvironmentVariable,
    SecretEnvironmentReference,
)
from runtime.projects import InMemoryProjectRegistry, ManagedProject  # noqa: E402
from runtime.runtime_acceptance import (  # noqa: E402
    AcceptanceJourney,
    AcceptanceStage,
    CapabilityAcceptanceContract,
    EvidenceKind,
    RuntimeAcceptanceProfile,
    RuntimeAcceptanceRun,
)

NOW = datetime(2026, 8, 16, tzinfo=timezone.utc)
COMMIT_SHA = "1" * 40
REPOSITORY_URL = "https://example.com/products/generic-demo.git"


def build_profile() -> RuntimeAcceptanceProfile:
    """Return a small generic profile; this is not a real product acceptance claim."""

    journey = AcceptanceJourney(
        "demo.smoke",
        "DEMO",
        "Customer opens the generic demo",
        (EvidenceKind.BROWSER, EvidenceKind.SCREENSHOT),
    )
    capability = CapabilityAcceptanceContract(
        "DEMO",
        "1.0",
        "Generic demo surface",
        (journey.journey_id,),
    )
    return RuntimeAcceptanceProfile(
        "generic-demo-profile", "1.0", (capability,), (journey,)
    )


def build_configuration(
    profile: RuntimeAcceptanceProfile,
) -> ManagedProductRuntimeConfiguration:
    """Return an immutable declaration for a fictional, framework-neutral demo product."""

    return ManagedProductRuntimeConfiguration(
        configuration_id="generic-demo-runtime",
        project_id="generic-demo-product",
        revision=1,
        repository_url=REPOSITORY_URL,
        branch="main",
        commit_sha=COMMIT_SHA,
        frontend_url="http://127.0.0.1:4173",
        backend_url="http://127.0.0.1:8000",
        allowed_origins=("http://127.0.0.1:4173", "http://127.0.0.1:8000"),
        migration_commands=(
            OneShotCommand(
                "database-migrate",
                CommandSpec("python", ("-m", "demo_product.migrate")),
                timeout_seconds=180,
            ),
        ),
        services=(
            ManagedRuntimeService(
                "backend",
                CommandSpec("python", ("-m", "demo_product.backend")),
                ReadinessProbe("backend-ready", "http://127.0.0.1:8000/health"),
                OneShotCommand(
                    "backend-stop",
                    CommandSpec(
                        "python", ("-m", "demo_product.control", "stop", "backend")
                    ),
                ),
            ),
            ManagedRuntimeService(
                "frontend",
                CommandSpec("python", ("-m", "demo_product.frontend")),
                ReadinessProbe("frontend-ready", "http://127.0.0.1:4173/ready"),
                OneShotCommand(
                    "frontend-stop",
                    CommandSpec(
                        "python", ("-m", "demo_product.control", "stop", "frontend")
                    ),
                ),
            ),
        ),
        environment_allow_list=("APP_MODE", "DATABASE_URL", "PUBLIC_API_URL"),
        environment=(
            RuntimeEnvironmentVariable("APP_MODE", "acceptance"),
            RuntimeEnvironmentVariable("PUBLIC_API_URL", "http://127.0.0.1:8000"),
        ),
        secret_references=(
            SecretEnvironmentReference("DATABASE_URL", "demo-acceptance-database"),
        ),
        acceptance_profile_id=profile.profile_id,
        acceptance_profile_version=profile.version,
        acceptance_profile_digest=profile.digest,
        created_by="example-operator",
        created_at=NOW,
    )


def main() -> None:
    profile = build_profile()
    configuration = build_configuration(profile)
    project = ManagedProject(
        "generic-demo-product",
        "Generic Demo Product",
        "Fictional product used only to demonstrate a runtime declaration",
        REPOSITORY_URL,
        "main",
    )
    with TemporaryDirectory() as directory:
        store = FileRuntimeConfigurationStore(directory)
        service = ManagedProductRuntimeConfigurationService(
            InMemoryProjectRegistry((project,)),
            store,
            (profile,),
            allowed_executables=frozenset({"python"}),
            allowed_repository_hosts=frozenset({"example.com"}),
            allowed_origins=frozenset(configuration.allowed_origins),
            allowed_environment_names=frozenset(
                configuration.environment_allow_list
            ),
            allowed_secret_references=frozenset({"demo-acceptance-database"}),
        )
        registered = service.register(configuration)
        planned_run = RuntimeAcceptanceRun(
            "generic-demo-run",
            project.project_id,
            "1.0",
            COMMIT_SHA,
            AcceptanceStage.PLANNED,
            profile.capabilities,
            profile.journeys,
            NOW,
            NOW,
        )
        bound_run = service.bind_acceptance_run(registered, planned_run)
        restored = FileRuntimeConfigurationStore(directory).get(
            configuration.project_id, configuration.configuration_id
        )
        print(f"configuration={restored.configuration_id}")
        print(f"revision={restored.revision}")
        print(f"commit={restored.commit_sha}")
        print(f"digest={restored.digest}")
        print(f"restart_verified={restored == configuration}")
        print(
            "acceptance_binding="
            f"{bound_run.runtime_configuration_id}@"
            f"{bound_run.runtime_configuration_revision}"
        )
        print("execution_performed=false")


if __name__ == "__main__":
    main()
