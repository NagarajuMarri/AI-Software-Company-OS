"""Day 5 acceptance tests for declarative managed-product runtime configuration.

These tests intentionally exercise configuration, policy, persistence, and binding
only.  They must never start a process, contact a network service, resolve a
secret, open a browser, or mutate a repository.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import json

import pytest

from runtime.managed_product_runtime import (
    CommandSpec,
    FileRuntimeConfigurationStore,
    InMemoryRuntimeConfigurationStore,
    ManagedProductRuntimeConfiguration,
    ManagedProductRuntimeConfigurationService,
    ManagedRuntimeService,
    OneShotCommand,
    ReadinessProbe,
    RuntimeConfigurationConflictError,
    RuntimeConfigurationCorruptError,
    RuntimeConfigurationNotFoundError,
    RuntimeConfigurationPolicyError,
    RuntimeEnvironmentVariable,
    SecretEnvironmentReference,
    configuration_digest,
)
from runtime.projects import InMemoryProjectRegistry, ManagedProject
from runtime.projects import ProjectLifecycle
from runtime.runtime_acceptance import (
    AcceptanceStage,
    RuntimeAcceptanceProfile,
    RuntimeAcceptanceRun,
    RuntimeAcceptanceStore,
    acceptance_profile_digest,
    evidence_digest,
    speakmate_v1_contracts,
    speakmate_v1_journeys,
    speakmate_v1_profile,
)


NOW = datetime(2026, 8, 16, 9, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
SHA = "a" * 40
OTHER_SHA = "b" * 40
PROFILE_ID = "speakmate-v1"
PROFILE_VERSION = "1.0"
PROFILE = speakmate_v1_profile()
PROFILE_DIGEST = PROFILE.digest


def project() -> ManagedProject:
    return ManagedProject(
        project_id="spoken-english-ai",
        name="SpeakMate",
        description="Spoken English managed product",
        repository_url="https://github.com/example/spoken-english-ai.git",
        default_branch="main",
    )


def command(
    executable: str = "python",
    arguments: tuple[str, ...] = ("-m", "backend.app"),
    working_directory: str = "backend",
) -> CommandSpec:
    return CommandSpec(executable, arguments, working_directory)


def oneshot(
    command_id: str = "database-migrate",
    spec: CommandSpec | None = None,
    timeout_seconds: int = 300,
) -> OneShotCommand:
    return OneShotCommand(
        command_id,
        spec
        or command(
            arguments=("-m", "alembic", "upgrade", "head"),
            working_directory="backend",
        ),
        timeout_seconds,
    )


def backend_service() -> ManagedRuntimeService:
    return ManagedRuntimeService(
        "backend",
        command(arguments=("-m", "backend.app"), working_directory="backend"),
        ReadinessProbe("backend-ready", "http://127.0.0.1:8000/health"),
        oneshot(
            "backend-stop",
            command(arguments=("-m", "backend.stop"), working_directory="backend"),
            30,
        ),
    )


def frontend_service() -> ManagedRuntimeService:
    return ManagedRuntimeService(
        "frontend",
        command("npm", ("run", "preview"), "frontend"),
        ReadinessProbe("frontend-ready", "http://localhost:4173/health"),
        oneshot("frontend-stop", command("npm", ("run", "stop"), "frontend"), 30),
    )


def configuration(**changes) -> ManagedProductRuntimeConfiguration:
    values = {
        "configuration_id": "spoken-english-ai-runtime",
        "project_id": "spoken-english-ai",
        "revision": 1,
        "repository_url": "https://github.com/example/spoken-english-ai.git",
        "branch": "main",
        "commit_sha": SHA,
        "frontend_url": "http://localhost:4173",
        "backend_url": "http://127.0.0.1:8000",
        "allowed_origins": (
            "http://127.0.0.1:8000",
            "http://localhost:4173",
        ),
        "migration_commands": (oneshot(),),
        "services": (backend_service(), frontend_service()),
        "environment_allow_list": ("APP_ENV", "DATABASE_URL"),
        "environment": (RuntimeEnvironmentVariable("APP_ENV", "acceptance"),),
        "secret_references": (
            SecretEnvironmentReference(
                "DATABASE_URL", "ascos.spoken-english-ai.database"
            ),
        ),
        "acceptance_profile_id": PROFILE_ID,
        "acceptance_profile_version": PROFILE_VERSION,
        "acceptance_profile_digest": PROFILE_DIGEST,
        "created_by": "founder",
        "created_at": NOW,
    }
    values.update(changes)
    return ManagedProductRuntimeConfiguration(**values)


def acceptance_run(**changes) -> RuntimeAcceptanceRun:
    values = {
        "run_id": "run-day5",
        "product_id": "spoken-english-ai",
        "version": "1.0",
        "commit_sha": SHA,
        "stage": AcceptanceStage.PLANNED,
        "capabilities": speakmate_v1_contracts(),
        "journeys": speakmate_v1_journeys(),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return RuntimeAcceptanceRun(**values)


def service(store=None, *, registry=None, profiles=None, **policy):
    registry = registry or InMemoryProjectRegistry((project(),))
    profiles = profiles or {PROFILE.profile_id: PROFILE}
    defaults = {
        "allowed_executables": frozenset({"python", "npm"}),
        "allowed_repository_hosts": frozenset({"github.com"}),
        "allowed_origins": frozenset(
            {"http://127.0.0.1:8000", "http://localhost:4173"}
        ),
        "allowed_environment_names": frozenset({"APP_ENV", "DATABASE_URL"}),
        "allowed_secret_references": frozenset(
            {"ascos.spoken-english-ai.database"}
        ),
    }
    defaults.update(policy)
    return ManagedProductRuntimeConfigurationService(
        registry,
        store or InMemoryRuntimeConfigurationStore(),
        profiles,
        **defaults,
    )


def test_valid_configuration_is_immutable_and_has_canonical_digest():
    value = configuration()
    assert len(value.digest) == 64
    assert value.digest == configuration_digest(value)
    assert value.digest == value.digest.lower()
    assert set(value.digest) <= set("0123456789abcdef")
    with pytest.raises(FrozenInstanceError):
        value.branch = "develop"


def test_configuration_digest_is_deterministic_and_preserves_command_semantics():
    first = configuration()
    second = configuration()
    reordered_arguments = replace(
        first.services[1].start_command,
        arguments=("preview", "run"),
    )
    changed = replace(
        first,
        services=(
            first.services[0],
            replace(first.services[1], start_command=reordered_arguments),
        ),
    )
    assert configuration_digest(first) == configuration_digest(second)
    assert configuration_digest(first) != configuration_digest(changed)
    assert changed.services[1].start_command.arguments == ("preview", "run")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: replace(value, repository_url="https://github.com/example/other.git"),
        lambda value: replace(value, branch="release/v1"),
        lambda value: replace(value, commit_sha=OTHER_SHA),
        lambda value: replace(
            value,
            frontend_url="http://localhost:4174",
            allowed_origins=("http://127.0.0.1:8000", "http://localhost:4174"),
            services=(
                value.services[0],
                replace(
                    value.services[1],
                    readiness_probe=replace(
                        value.services[1].readiness_probe,
                        url="http://localhost:4174/health",
                    ),
                ),
            ),
        ),
        lambda value: replace(value, environment=(RuntimeEnvironmentVariable("APP_ENV", "test"),)),
        lambda value: replace(value, secret_references=(SecretEnvironmentReference("DATABASE_URL", "ascos.spoken-english-ai.database-v2"),)),
        lambda value: replace(value, acceptance_profile_version="1.1"),
        lambda value: replace(value, acceptance_profile_digest="c" * 64),
        lambda value: replace(value, created_by="operator"),
        lambda value: replace(value, created_at=LATER),
    ],
)
def test_digest_changes_for_each_authority_bearing_field(mutation):
    value = configuration()
    assert configuration_digest(value) != configuration_digest(mutation(value))


@pytest.mark.parametrize(
    "identifier",
    ("", ".", "..", "../runtime", "..\\runtime", "/runtime", "C:\\runtime", "bad/id", "bad\x00id"),
)
def test_configuration_identifiers_are_filesystem_safe(identifier):
    with pytest.raises(ValueError, match="identifier"):
        configuration(configuration_id=identifier)


@pytest.mark.parametrize(
    "repository_url",
    (
        "file:///tmp/product",
        "../product",
        "https://user:password@github.com/example/product.git",
        "https://github.com/example/product.git?token=x",
        "https://github.com/example/product.git#main",
        "https://github.com:99999/example/product.git",
        "https://github.com:0/example/product.git",
        "https://github.com/example/%2e%2e/product.git",
        "https://github.com/example/../product.git",
        "https://github.com/example/./product.git",
        "https://github.com/example//product.git",
        "http://example.com/product.git",
        "https:\\github.com\\example\\product.git",
    ),
)
def test_repository_url_rejects_credentials_ambiguity_and_insecure_external_http(
    repository_url,
):
    with pytest.raises(ValueError, match="repository|port"):
        configuration(repository_url=repository_url)


@pytest.mark.parametrize(
    "branch",
    (
        "",
        ".hidden",
        "/main",
        "main/",
        "main..next",
        "main@{1}",
        "main branch",
        "main~1",
        "main^",
        "main:next",
        "main?",
        "main*",
        "main[0]",
        "main\\next",
        "topic/value.lock",
    ),
)
def test_branch_must_be_a_safe_git_reference(branch):
    with pytest.raises(ValueError, match="branch"):
        configuration(branch=branch)


@pytest.mark.parametrize("commit_sha", ("a" * 39, "a" * 41, "g" * 40, "A" * 40))
def test_commit_sha_is_exact_lowercase_full_sha(commit_sha):
    with pytest.raises(ValueError, match="lowercase|SHA"):
        configuration(commit_sha=commit_sha)


@pytest.mark.parametrize(
    "executable",
    ("", "/bin/python", "../python", "sh", "bash", "cmd.exe", "powershell", "pwsh"),
)
def test_commands_reject_shells_and_unsafe_executables(executable):
    with pytest.raises(ValueError, match="executable"):
        command(executable=executable)


@pytest.mark.parametrize(
    "arguments",
    (
        ("-c", "print('unsafe')"),
        ("&&", "next"),
        ("--token=raw-secret-value",),
        ("password=not-persistable",),
        ("contains\x00nul",),
    ),
)
def test_command_arguments_reject_inline_code_shell_tokens_and_secrets(arguments):
    with pytest.raises(ValueError, match="argument|Inline"):
        command(arguments=arguments)


@pytest.mark.parametrize(
    "arguments",
    (
        ("--password", "hunter2"),
        ("--api-key", "abc123"),
        ("--client-secret", "ordinarysecret"),
        ("--authorization", "ordinary-value"),
        ("--access-key", "ordinary-value"),
        ("--password=hunter2",),
        ("--header", "Basic dXNlcjpwYXNz"),
        ("--identity", "AKIAIOSFODNN7EXAMPLE"),
    ),
)
def test_command_arguments_reject_secret_bearing_option_forms(arguments):
    with pytest.raises(ValueError, match="secret|argument|unsafe"):
        command(arguments=arguments)


@pytest.mark.parametrize(
    "executable,arguments",
    (
        ("python", ("/tmp/evil.py",)),
        ("python", ("../../evil.py",)),
        ("python", ("C:\\evil.py",)),
        ("npm", ("--prefix", "../../outside", "run", "start")),
    ),
)
def test_command_arguments_cannot_escape_the_future_workspace(executable, arguments):
    with pytest.raises(ValueError, match="path|workspace|argument|unsafe"):
        command(executable, arguments)


def test_non_shell_metacharacters_remain_literal_arguments():
    value = command("npm", ("run", "preview", "--", "--label=a$b"), "frontend")
    assert value.arguments[-1] == "--label=a$b"


@pytest.mark.parametrize(
    "working_directory",
    ("", "../backend", "backend/../secrets", "/backend", "C:\\backend", ".git/hooks", "./backend", "bad\x00path"),
)
def test_working_directories_must_stay_inside_future_workspace(working_directory):
    with pytest.raises(ValueError, match="working directory"):
        command(working_directory=working_directory)


@pytest.mark.parametrize("working_directory", ("backend/", "backend/.", "backend/./app"))
def test_working_directories_must_already_be_canonical(working_directory):
    with pytest.raises(ValueError, match="working directory"):
        command(working_directory=working_directory)


@pytest.mark.parametrize("timeout", (0, -1, 1801, True, 1.5))
def test_one_shot_command_timeout_is_bounded(timeout):
    with pytest.raises(ValueError, match="timeout"):
        oneshot(timeout_seconds=timeout)


@pytest.mark.parametrize(
    "url",
    (
        "http://example.com/health",
        "ftp://localhost/health",
        "http://0.0.0.0:8000/health",
        "http://[::]:8000/health",
        "http://user:password@localhost/health",
        "http://localhost:99999/health",
        "http://localhost/health?token=x",
        "http://localhost/health#fragment",
        "http:\\localhost\\health",
    ),
)
def test_runtime_endpoints_fail_closed(url):
    with pytest.raises(ValueError, match="unsafe|requires HTTPS|unspecified|port"):
        ReadinessProbe("ready", url)


@pytest.mark.parametrize(
    "url",
    (
        "http://localhost:0/health",
        "https://product.example/%2e%2e/admin",
        "https://product.example/a/%2E%2E/admin",
    ),
)
def test_endpoint_ports_and_encoded_traversal_fail_closed(url):
    with pytest.raises(ValueError, match="port|traversal|unsafe"):
        ReadinessProbe("ready", url)


@pytest.mark.parametrize(
    "url",
    (
        "http://localhost:8000/a/../health",
        "http://localhost:8000/a/./health",
        "http://localhost:8000/a//health",
    ),
)
def test_readiness_urls_must_have_canonical_paths(url):
    with pytest.raises(ValueError, match="canonical|path|unsafe"):
        ReadinessProbe("ready", url)


@pytest.mark.parametrize(
    "field,url",
    (
        ("frontend_url", "http://localhost:4173/app/../admin"),
        ("frontend_url", "http://localhost:4173/app/./home"),
        ("frontend_url", "http://localhost:4173/app//home"),
        ("backend_url", "http://127.0.0.1:8000/api/../admin"),
        ("backend_url", "http://127.0.0.1:8000/api/./health"),
        ("backend_url", "http://127.0.0.1:8000/api//health"),
    ),
)
def test_declared_frontend_and_backend_urls_must_have_canonical_paths(field, url):
    with pytest.raises(ValueError, match="canonical|path|unsafe"):
        configuration(**{field: url})


def test_external_https_and_loopback_http_endpoints_are_allowed():
    assert ReadinessProbe("local", "http://127.0.0.1:8000/health").url.startswith(
        "http://"
    )
    assert ReadinessProbe("public", "https://product.example/health").url.startswith(
        "https://"
    )


def test_readiness_probe_must_use_an_allowed_runtime_origin():
    foreign = replace(
        backend_service(),
        readiness_probe=ReadinessProbe("backend-ready", "http://localhost:9999/health"),
    )
    with pytest.raises(ValueError, match="allowed origin"):
        configuration(services=(foreign, frontend_service()))


@pytest.mark.parametrize(
    "name,value",
    (
        ("lowercase", "safe"),
        ("9INVALID", "safe"),
        ("API_KEY", "safe"),
        ("PASSWORD", "safe"),
        ("APP_TOKEN", "safe"),
        ("AUTHORIZATION", "safe"),
        ("AWS_ACCESS_KEY_ID", "safe"),
        ("APP_ENV", "ghp_abcdefghijklmnopqrstuvwxyz123456"),
        ("APP_ENV", "token=raw-secret"),
        ("APP_ENV", "Basic dXNlcjpwYXNz"),
        ("APP_ENV", "AKIAIOSFODNN7EXAMPLE"),
    ),
)
def test_public_environment_rejects_invalid_names_and_secret_material(name, value):
    with pytest.raises(ValueError, match="Environment|Sensitive|unsafe"):
        RuntimeEnvironmentVariable(name, value)


@pytest.mark.parametrize(
    "reference",
    (
        "",
        "postgresql://user:password@database/app",
        "DATABASE_URL=value",
        "ascos/product/database",
        "ascos.product.database?version=1",
        "raw secret value",
    ),
)
def test_secret_values_are_replaced_by_opaque_references(reference):
    with pytest.raises(ValueError, match="opaque safe reference"):
        SecretEnvironmentReference("DATABASE_URL", reference)


def test_token_shaped_string_cannot_masquerade_as_a_secret_reference():
    with pytest.raises(ValueError, match="opaque safe reference"):
        SecretEnvironmentReference("DATABASE_URL", "ghp_" + "a" * 24)


def test_environment_declarations_must_be_unique_sorted_exact_and_disjoint():
    public = RuntimeEnvironmentVariable("APP_ENV", "acceptance")
    secret = SecretEnvironmentReference("DATABASE_URL", "ascos.database")
    with pytest.raises(ValueError, match="sorted"):
        configuration(environment_allow_list=("DATABASE_URL", "APP_ENV"))
    with pytest.raises(ValueError, match="exactly cover"):
        configuration(environment_allow_list=("APP_ENV", "DATABASE_URL", "EXTRA"))
    with pytest.raises(ValueError, match="overlap"):
        configuration(
            environment_allow_list=("APP_ENV",),
            environment=(public,),
            secret_references=(SecretEnvironmentReference("APP_ENV", "ascos.app"),),
        )
    with pytest.raises(ValueError, match="unique"):
        configuration(
            environment_allow_list=("APP_ENV", "DATABASE_URL"),
            environment=(public, public),
            secret_references=(secret,),
        )


def test_duplicate_command_service_and_probe_identities_are_rejected():
    backend = backend_service()
    duplicate_service = replace(frontend_service(), service_id="backend")
    with pytest.raises(ValueError, match="service IDs"):
        configuration(services=(backend, duplicate_service))
    duplicate_probe = replace(
        frontend_service(),
        readiness_probe=replace(
            frontend_service().readiness_probe,
            probe_id=backend.readiness_probe.probe_id,
        ),
    )
    with pytest.raises(ValueError, match="probe IDs"):
        configuration(services=(backend, duplicate_probe))
    with pytest.raises(ValueError, match="command IDs"):
        configuration(migration_commands=(backend.stop_command,))


def successor(
    current: ManagedProductRuntimeConfiguration,
    *,
    commit_sha: str = OTHER_SHA,
    branch: str = "agent/runtime-v2",
    created_by: str = "operator",
    created_at: datetime = LATER,
) -> ManagedProductRuntimeConfiguration:
    return replace(
        current,
        revision=current.revision + 1,
        branch=branch,
        commit_sha=commit_sha,
        created_by=created_by,
        created_at=created_at,
        supersedes_digest=current.digest,
    )


@pytest.mark.parametrize(
    "store_factory",
    (
        lambda _tmp_path: InMemoryRuntimeConfigurationStore(),
        lambda tmp_path: FileRuntimeConfigurationStore(tmp_path),
    ),
)
def test_store_preserves_immutable_revisions_and_optimistic_updates(
    store_factory, tmp_path
):
    store = store_factory(tmp_path)
    first = configuration()
    assert store.save(first) == first
    assert store.save(first) == first
    second = successor(first)
    assert store.save(second, expected_revision=1) == second
    assert store.get(first.project_id, first.configuration_id) == second
    assert store.get_revision(first.project_id, first.configuration_id, 1) == first
    assert store.get_revision(first.project_id, first.configuration_id, 2) == second
    assert store.list_revisions(first.project_id, first.configuration_id) == (
        first,
        second,
    )
    assert store.list_for_project(first.project_id) == (second,)


@pytest.mark.parametrize(
    "store_factory",
    (
        lambda _tmp_path: InMemoryRuntimeConfigurationStore(),
        lambda tmp_path: FileRuntimeConfigurationStore(tmp_path),
    ),
)
def test_store_rejects_conflicting_create_stale_writer_and_broken_history(
    store_factory, tmp_path
):
    store = store_factory(tmp_path)
    first = store.save(configuration())
    with pytest.raises(RuntimeConfigurationConflictError):
        store.save(replace(first, branch="other"), expected_revision=1)
    second = store.save(successor(first), expected_revision=1)
    with pytest.raises(RuntimeConfigurationConflictError, match="another writer"):
        store.save(
            successor(first, commit_sha="c" * 40, branch="agent/stale"),
            expected_revision=1,
        )
    with pytest.raises(RuntimeConfigurationConflictError, match="predecessor"):
        store.save(
            replace(
                second,
                revision=3,
                commit_sha="d" * 40,
                supersedes_digest="e" * 64,
            ),
            expected_revision=2,
        )


def test_file_store_survives_restart_and_orders_revisions_numerically(tmp_path):
    store = FileRuntimeConfigurationStore(tmp_path)
    current = store.save(configuration())
    for revision in range(2, 11):
        current = store.save(
            successor(
                current,
                commit_sha=f"{revision:040x}",
                branch=f"agent/runtime-v{revision}",
                created_at=NOW,
            ),
            expected_revision=revision - 1,
        )
    restarted = FileRuntimeConfigurationStore(tmp_path)
    assert restarted.get(current.project_id, current.configuration_id) == current
    assert tuple(
        item.revision
        for item in restarted.list_revisions(
            current.project_id, current.configuration_id
        )
    ) == tuple(range(1, 11))


def test_two_file_store_instances_enforce_cross_instance_compare_and_swap(tmp_path):
    first_store = FileRuntimeConfigurationStore(tmp_path)
    second_store = FileRuntimeConfigurationStore(tmp_path)
    first = first_store.save(configuration())
    first_candidate = successor(first)
    stale_candidate = successor(first, commit_sha="c" * 40, branch="agent/stale")
    first_store.save(first_candidate, expected_revision=1)
    with pytest.raises(RuntimeConfigurationConflictError, match="another writer"):
        second_store.save(stale_candidate, expected_revision=1)
    assert second_store.get(first.project_id, first.configuration_id) == first_candidate


@pytest.mark.parametrize(
    "project_id,configuration_id",
    (
        ("../project", "runtime"),
        ("..\\project", "runtime"),
        ("/project", "runtime"),
        ("project", "../runtime"),
        ("project", "C:\\runtime"),
        ("project", "."),
    ),
)
def test_store_rejects_unsafe_identity_at_every_read_boundary(
    tmp_path, project_id, configuration_id
):
    store = FileRuntimeConfigurationStore(tmp_path)
    with pytest.raises(ValueError, match="Unsafe"):
        store.get(project_id, configuration_id)
    with pytest.raises(ValueError, match="Unsafe"):
        store.get_revision(project_id, configuration_id, 1)
    with pytest.raises(ValueError, match="Unsafe"):
        store.list_revisions(project_id, configuration_id)


def test_missing_configuration_and_revision_raise_typed_errors(tmp_path):
    store = FileRuntimeConfigurationStore(tmp_path)
    with pytest.raises(RuntimeConfigurationNotFoundError):
        store.get("spoken-english-ai", "missing")
    first = store.save(configuration())
    with pytest.raises(RuntimeConfigurationNotFoundError):
        store.get_revision(first.project_id, first.configuration_id, 2)


def _configuration_directory(tmp_path):
    return tmp_path / "spoken-english-ai" / "spoken-english-ai-runtime"


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: {**payload, "schema_version": 999},
        lambda payload: {**payload, "digest": "0" * 64},
        lambda payload: {**payload, "unexpected": True},
        lambda _payload: ["not", "an", "envelope"],
    ),
)
def test_file_store_rejects_unknown_schema_digest_tamper_and_malformed_envelope(
    tmp_path, mutate
):
    store = FileRuntimeConfigurationStore(tmp_path)
    first = store.save(configuration())
    path = _configuration_directory(tmp_path) / "current.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(mutate(payload)), encoding="utf-8")
    with pytest.raises(RuntimeConfigurationCorruptError, match="cannot be trusted"):
        FileRuntimeConfigurationStore(tmp_path).get(
            first.project_id, first.configuration_id
        )


def test_file_store_rejects_missing_revision_even_when_current_is_well_formed(tmp_path):
    store = FileRuntimeConfigurationStore(tmp_path)
    first = store.save(configuration())
    second = store.save(successor(first), expected_revision=1)
    directory = _configuration_directory(tmp_path)
    (directory / "revisions" / "00000001.json").unlink()
    with pytest.raises(RuntimeConfigurationCorruptError, match="contiguous|history"):
        FileRuntimeConfigurationStore(tmp_path).get(
            second.project_id, second.configuration_id
        )


def test_file_store_rejects_current_pointer_to_an_older_valid_revision(tmp_path):
    store = FileRuntimeConfigurationStore(tmp_path)
    first = store.save(configuration())
    second = store.save(successor(first), expected_revision=1)
    directory = _configuration_directory(tmp_path)
    current_path = directory / "current.json"
    current_path.write_bytes((directory / "revisions" / "00000001.json").read_bytes())
    with pytest.raises(RuntimeConfigurationCorruptError, match="current|history"):
        FileRuntimeConfigurationStore(tmp_path).get(
            second.project_id, second.configuration_id
        )


def test_corrupt_history_blocks_later_revision_without_any_new_authority(tmp_path):
    store = FileRuntimeConfigurationStore(tmp_path)
    first = store.save(configuration())
    second = store.save(successor(first), expected_revision=1)
    directory = _configuration_directory(tmp_path)
    current_path = directory / "current.json"
    current_before = current_path.read_bytes()
    (directory / "revisions" / "00000001.json").unlink()
    third = successor(
        second,
        commit_sha="c" * 40,
        branch="agent/runtime-v3",
    )
    with pytest.raises(RuntimeConfigurationCorruptError, match="history|contiguous"):
        store.save(third, expected_revision=2)
    assert current_path.read_bytes() == current_before
    assert not (directory / "revisions" / "00000003.json").exists()


def test_file_store_rejects_snapshot_copied_under_another_identity(tmp_path):
    store = FileRuntimeConfigurationStore(tmp_path)
    first = store.save(configuration())
    source = _configuration_directory(tmp_path) / "current.json"
    foreign = tmp_path / "other-project" / "other-runtime"
    (foreign / "revisions").mkdir(parents=True)
    (foreign / "current.json").write_bytes(source.read_bytes())
    (foreign / "revisions" / "00000001.json").write_bytes(source.read_bytes())
    with pytest.raises(RuntimeConfigurationCorruptError, match="identity"):
        FileRuntimeConfigurationStore(tmp_path).get("other-project", "other-runtime")
    assert store.get(first.project_id, first.configuration_id) == first


def test_file_store_leaves_no_fixed_temporary_or_lock_files_after_success(tmp_path):
    FileRuntimeConfigurationStore(tmp_path).save(configuration())
    names = {
        path.name
        for path in _configuration_directory(tmp_path).rglob("*")
        if path.is_file()
    }
    assert ".write.lock" not in names
    assert not any(name.endswith(".tmp") for name in names)


def test_file_store_recovers_an_exact_orphan_revision_after_current_write_failure(
    tmp_path, monkeypatch
):
    import runtime.managed_product_runtime.persistence as persistence

    store = FileRuntimeConfigurationStore(tmp_path)
    first = store.save(configuration())
    second = successor(first)
    real_replace = persistence.os.replace
    failed = False

    def fail_current_once(source, target):
        nonlocal failed
        if not failed and target.name == "current.json":
            failed = True
            raise OSError("injected current-pointer write failure")
        return real_replace(source, target)

    monkeypatch.setattr(persistence.os, "replace", fail_current_once)
    with pytest.raises(OSError, match="injected"):
        store.save(second, expected_revision=1)
    monkeypatch.setattr(persistence.os, "replace", real_replace)

    restarted = FileRuntimeConfigurationStore(tmp_path)
    with pytest.raises(RuntimeConfigurationCorruptError, match="history|current"):
        restarted.get(first.project_id, first.configuration_id)
    assert restarted.save(second, expected_revision=1) == second
    assert restarted.get(first.project_id, first.configuration_id) == second
    assert restarted.list_revisions(first.project_id, first.configuration_id) == (
        first,
        second,
    )
    assert not any(
        path.name.endswith(".tmp")
        for path in _configuration_directory(tmp_path).rglob("*")
    )


def bound_acceptance_run(
    runtime_configuration: ManagedProductRuntimeConfiguration | None = None,
    **changes,
) -> RuntimeAcceptanceRun:
    runtime_configuration = runtime_configuration or configuration()
    values = {
        "runtime_configuration_id": runtime_configuration.configuration_id,
        "runtime_configuration_revision": runtime_configuration.revision,
        "runtime_configuration_digest": runtime_configuration.digest,
        "acceptance_profile_id": PROFILE.profile_id,
        "acceptance_profile_version": PROFILE.version,
        "acceptance_profile_digest": PROFILE.digest,
    }
    values.update(changes)
    return acceptance_run(**values)


def test_speakmate_profile_digest_is_canonical_and_binds_contract_semantics():
    assert PROFILE.profile_id == PROFILE_ID
    assert PROFILE.version == PROFILE_VERSION
    assert PROFILE.digest == acceptance_profile_digest(
        PROFILE.profile_id,
        PROFILE.version,
        PROFILE.capabilities,
        PROFILE.journeys,
    )
    reordered = RuntimeAcceptanceProfile(
        PROFILE.profile_id,
        PROFILE.version,
        tuple(reversed(PROFILE.capabilities)),
        tuple(reversed(PROFILE.journeys)),
    )
    changed_title = RuntimeAcceptanceProfile(
        PROFILE.profile_id,
        PROFILE.version,
        (replace(PROFILE.capabilities[0], title="Changed title"),)
        + PROFILE.capabilities[1:],
        PROFILE.journeys,
    )
    changed_requirement = RuntimeAcceptanceProfile(
        PROFILE.profile_id,
        PROFILE.version,
        (
            replace(
                PROFILE.capabilities[0],
                requirement_ids=PROFILE.capabilities[0].requirement_ids
                + ("NEW-REQUIREMENT",),
            ),
        )
        + PROFILE.capabilities[1:],
        PROFILE.journeys,
    )
    assert reordered.digest == PROFILE.digest
    assert changed_title.digest != PROFILE.digest
    assert changed_requirement.digest != PROFILE.digest
    assert replace(PROFILE, version="1.1").digest != PROFILE.digest


@pytest.mark.parametrize(
    "mutation",
    (
        lambda: RuntimeAcceptanceProfile(
            PROFILE.profile_id,
            PROFILE.version,
            list(PROFILE.capabilities),
            PROFILE.journeys,
        ),
        lambda: RuntimeAcceptanceProfile(
            PROFILE.profile_id,
            PROFILE.version,
            PROFILE.capabilities,
            list(PROFILE.journeys),
        ),
        lambda: replace(
            PROFILE.capabilities[0],
            required_journey_ids=list(
                PROFILE.capabilities[0].required_journey_ids
            ),
        ),
        lambda: replace(
            PROFILE.capabilities[0],
            requirement_ids=list(PROFILE.capabilities[0].requirement_ids),
        ),
        lambda: replace(
            PROFILE.journeys[0],
            required_evidence=list(PROFILE.journeys[0].required_evidence),
        ),
    ),
)
def test_acceptance_profiles_and_nested_contracts_require_immutable_tuples(mutation):
    with pytest.raises(
        ValueError,
        match="tuple|capabilities and journeys|evidence kinds",
    ):
        mutation()


def test_runtime_acceptance_configuration_binding_is_complete_and_profile_verified():
    value = bound_acceptance_run()
    assert value.runtime_configuration_digest == configuration().digest
    with pytest.raises(ValueError, match="binding must be complete"):
        acceptance_run(runtime_configuration_id="spoken-english-ai-runtime")
    with pytest.raises(ValueError, match="profile digest"):
        bound_acceptance_run(acceptance_profile_digest="f" * 64)


def test_runtime_evidence_digest_binds_configuration_revision_and_digest():
    first = bound_acceptance_run()
    changed_revision = replace(first, runtime_configuration_revision=2)
    changed_digest = replace(first, runtime_configuration_digest="f" * 64)
    assert evidence_digest(first) != evidence_digest(changed_revision)
    assert evidence_digest(first) != evidence_digest(changed_digest)


@pytest.mark.parametrize(
    "field,replacement",
    (
        ("runtime_configuration_id", "other-runtime"),
        ("runtime_configuration_revision", 2),
        ("runtime_configuration_digest", "f" * 64),
        ("acceptance_profile_id", "other-profile"),
        ("acceptance_profile_version", "2.0"),
    ),
)
def test_persisted_acceptance_run_cannot_change_runtime_authority(
    tmp_path, field, replacement
):
    store = RuntimeAcceptanceStore(tmp_path)
    value = bound_acceptance_run()
    store.save(value)
    changes = {field: replacement}
    if field in {"acceptance_profile_id", "acceptance_profile_version"}:
        changes["acceptance_profile_digest"] = acceptance_profile_digest(
            changes.get("acceptance_profile_id", value.acceptance_profile_id),
            changes.get("acceptance_profile_version", value.acceptance_profile_version),
            value.capabilities,
            value.journeys,
        )
    with pytest.raises(ValueError, match="immutable"):
        store.save(replace(value, **changes))


class EventRecorder:
    def __init__(self):
        self.events = []

    def publish(self, event_type, aggregate_type, aggregate_id, payload):
        self.events.append((event_type.value, aggregate_type, aggregate_id, payload))


def test_service_registers_revises_reads_and_emits_exactly_once_events():
    recorder = EventRecorder()
    store = InMemoryRuntimeConfigurationStore()
    manager = service(store, event_publisher=recorder)
    first = configuration()
    second = successor(first)
    assert manager.register(first) == first
    assert manager.register(first) == first
    assert manager.revise(second, expected_revision=1) == second
    assert manager.get(first.project_id, first.configuration_id) == second
    assert manager.get_revision(first.project_id, first.configuration_id, 1) == first
    assert manager.list_for_project(first.project_id) == (second,)
    assert [item[0] for item in recorder.events] == [
        "MANAGED_PRODUCT_RUNTIME_CONFIGURATION_CREATED",
        "MANAGED_PRODUCT_RUNTIME_CONFIGURATION_REVISED",
    ]
    for _name, aggregate_type, aggregate_id, payload in recorder.events:
        assert aggregate_type == "MANAGED_PRODUCT_RUNTIME_CONFIGURATION"
        assert aggregate_id == first.configuration_id
        assert payload["configuration_digest"] in {first.digest, second.digest}
        assert "ascos.spoken-english-ai.database" not in json.dumps(payload)


@pytest.mark.parametrize(
    "policy,match",
    (
        ({"allowed_executables": frozenset({"python"})}, "executable"),
        ({"allowed_repository_hosts": frozenset({"example.com"})}, "host"),
        (
            {"allowed_origins": frozenset({"http://127.0.0.1:8000"})},
            "origin",
        ),
        ({"allowed_environment_names": frozenset({"APP_ENV"})}, "environment"),
        ({"allowed_secret_references": frozenset()}, "secret reference"),
    ),
)
def test_operator_allow_lists_are_authoritative_and_failure_has_no_side_effects(
    policy, match
):
    store = InMemoryRuntimeConfigurationStore()
    recorder = EventRecorder()
    manager = service(store, event_publisher=recorder, **policy)
    with pytest.raises(RuntimeConfigurationPolicyError, match=match):
        manager.register(configuration())
    assert store.list_for_project("spoken-english-ai") == ()
    assert recorder.events == []


def test_project_registry_identity_and_lifecycle_are_authoritative():
    mismatched = ManagedProject(
        "spoken-english-ai",
        "SpeakMate",
        "Mismatched project",
        "https://github.com/example/other.git",
        "main",
    )
    paused = replace(project(), lifecycle=ProjectLifecycle.PAUSED)
    for registered, match in ((mismatched, "repository"), (paused, "Paused|archived")):
        manager = service(
            registry=InMemoryProjectRegistry((registered,)),
        )
        with pytest.raises(RuntimeConfigurationPolicyError, match=match):
            manager.register(configuration())


def test_service_rejects_unknown_version_and_stale_profile_digest():
    with pytest.raises(RuntimeConfigurationPolicyError, match="ID/version"):
        service().register(
            configuration(
                acceptance_profile_id="unknown-profile",
                acceptance_profile_digest="c" * 64,
            )
        )
    with pytest.raises(RuntimeConfigurationPolicyError, match="stale|untrusted"):
        service().register(configuration(acceptance_profile_digest="c" * 64))
    with pytest.raises(RuntimeConfigurationPolicyError, match="ID/version"):
        service().register(
            configuration(
                acceptance_profile_version="2.0",
                acceptance_profile_digest="c" * 64,
            )
        )


def test_bind_acceptance_run_records_exact_persisted_configuration_and_profile():
    manager = service()
    config = manager.register(configuration())
    run = acceptance_run()
    bound = manager.bind_acceptance_run(config, run)
    assert bound.runtime_configuration_id == config.configuration_id
    assert bound.runtime_configuration_revision == config.revision
    assert bound.runtime_configuration_digest == config.digest
    assert bound.acceptance_profile_id == PROFILE.profile_id
    assert bound.acceptance_profile_version == PROFILE.version
    assert bound.acceptance_profile_digest == PROFILE.digest
    assert bound.stage is AcceptanceStage.PLANNED
    assert manager.bind_acceptance_run(config, bound) == bound


def test_binding_requires_exact_persisted_revision_and_current_operator_policy():
    store = InMemoryRuntimeConfigurationStore()
    permissive = service(store)
    config = permissive.register(configuration())
    tampered = replace(config, branch="agent/unpersisted")
    with pytest.raises(RuntimeConfigurationPolicyError, match="exact persisted"):
        permissive.bind_acceptance_run(tampered, acceptance_run())

    tightened = service(store, allowed_executables=frozenset({"python"}))
    with pytest.raises(RuntimeConfigurationPolicyError, match="executable"):
        tightened.bind_acceptance_run(config, acceptance_run())

    paused_registry = InMemoryProjectRegistry(
        (replace(project(), lifecycle=ProjectLifecycle.PAUSED),)
    )
    paused = service(store, registry=paused_registry)
    with pytest.raises(RuntimeConfigurationPolicyError, match="Paused|archived"):
        paused.bind_acceptance_run(config, acceptance_run())


@pytest.mark.parametrize(
    "run,match",
    (
        (acceptance_run(product_id="other-product"), "product"),
        (acceptance_run(commit_sha=OTHER_SHA), "commit"),
        (replace(acceptance_run(), stage=AcceptanceStage.IMPLEMENTED), "PLANNED"),
        (
            acceptance_run(
                capabilities=(
                    replace(
                        speakmate_v1_contracts()[0],
                        title="Unregistered contract mutation",
                    ),
                )
                + speakmate_v1_contracts()[1:]
            ),
            "contract",
        ),
    ),
)
def test_binding_rejects_incompatible_acceptance_runs(run, match):
    manager = service()
    config = manager.register(configuration())
    with pytest.raises(RuntimeConfigurationPolicyError, match=match):
        manager.bind_acceptance_run(config, run)


def test_new_configuration_revision_cannot_rebind_an_existing_acceptance_run():
    manager = service()
    first = manager.register(configuration())
    old_bound_run = manager.bind_acceptance_run(first, acceptance_run())
    second = manager.revise(
        successor(first, commit_sha=SHA), expected_revision=1
    )
    with pytest.raises(RuntimeConfigurationPolicyError, match="immutable"):
        manager.bind_acceptance_run(second, old_bound_run)
    assert old_bound_run.runtime_configuration_revision == 1
    assert old_bound_run.runtime_configuration_digest == first.digest


def test_declarative_configuration_lifecycle_has_zero_runtime_side_effects(
    tmp_path, monkeypatch
):
    import socket
    import subprocess
    import urllib.request

    def prohibited(*_args, **_kwargs):
        raise AssertionError("Day 5 configuration attempted a runtime side effect")

    monkeypatch.setattr(subprocess, "run", prohibited)
    monkeypatch.setattr(subprocess, "Popen", prohibited)
    monkeypatch.setattr(socket, "create_connection", prohibited)
    monkeypatch.setattr(urllib.request, "urlopen", prohibited)

    store = FileRuntimeConfigurationStore(tmp_path)
    manager = service(store)
    first = manager.register(configuration())
    assert configuration_digest(first) == first.digest
    assert manager.get(first.project_id, first.configuration_id) == first
    bound = manager.bind_acceptance_run(first, acceptance_run())
    assert bound.stage is AcceptanceStage.PLANNED
    assert bound.evidence == ()
    assert bound.journey_results == ()
