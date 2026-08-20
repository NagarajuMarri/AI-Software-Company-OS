# Managed Product Runtime Configuration

Day 5 introduces a declarative, revisioned contract for describing how a registered managed product
is expected to run. The contract binds repository identity, an exact source revision, bounded service
commands, public runtime settings, opaque secret references, endpoints, and an acceptance profile
before any execution is authorized.

This module is configuration only. Creating, validating, digesting, storing, or reading a
configuration performs no Git operation, subprocess execution, network access, secret resolution,
service startup, browser automation, merge, deployment, or release.

## Why this boundary exists

Runtime acceptance evidence is useful only when ASCOS can prove what was intended to run. A mutable
branch name, an operator's ad hoc shell command, or an environment copied from a terminal cannot
provide that proof. A managed runtime configuration supplies the immutable input record that later
environment and browser providers must consume.

Each configuration revision binds:

- one registered product and repository URL;
- an expected branch and a lowercase full 40-character Git commit SHA;
- ordered migration commands and named service start/stop commands represented as argument arrays,
  never shell text;
- backend, frontend, and readiness URLs;
- explicitly public environment bindings;
- opaque secret references whose values are resolved only by the separately authorized Day 6
  environment provider; and
- an acceptance-profile identity, version, and digest.

The configuration has its own canonical SHA-256 digest. Runtime-acceptance work can therefore bind
both the acceptance profile and the exact runtime configuration without trusting filenames, mutable
registry metadata, or operator recollection.

## Public API

- `CommandSpec`, `OneShotCommand`, `ReadinessProbe`, and `ManagedRuntimeService` describe bounded
  commands and service health declarations.
- `RuntimeEnvironmentVariable` and `SecretEnvironmentReference` separate persistable public values
  from unresolved secret identities.
- `ManagedProductRuntimeConfiguration` is the frozen, digestible authority record.
- `InMemoryRuntimeConfigurationStore` and `FileRuntimeConfigurationStore` preserve immutable
  revision history behind `RuntimeConfigurationStore`.
- `ManagedProductRuntimeConfigurationService` applies registry and operator policy through
  `register`/`revise`, exposes deterministic reads, and uses `bind_acceptance_run` to bind a persisted
  revision to a compatible `PLANNED` run.
- `RuntimeAcceptanceProfile` provides the versioned capability-and-journey contract and canonical
  profile digest used by that binding.

## Declarative model

### Source binding

The source binding identifies the registered product repository, expected branch, and exact commit.
The branch remains useful routing information, but the exact SHA is the execution authority. A
future checkout provider must reject a checkout whose observed commit differs from that SHA.

Repository URLs cannot embed credentials, queries, or fragments. Configuration validation does not
clone, fetch, inspect, or modify the repository. Registration checks require the configuration to
match the managed-project repository and an operator-owned repository-host allow-list.

### Commands

Every migration, service-start, and service-stop command contains an executable followed by an
immutable tuple of individual arguments. Command ordering is semantic and is preserved by canonical
serialization and digesting. Shell command strings, shell control operators, path traversal, and
shell interpreter mediation are rejected. Registration also checks every executable against an
operator-owned allow-list. A configuration may describe a command; it cannot run one.

Working directories are relative, normalized paths inside the exact-SHA workspace. The workspace
root and resolution of each configured executable belong to the Day 6 environment provider.

### Endpoints

Backend and frontend URLs identify the product surfaces. Every frontend, backend, and readiness
origin must be explicitly present in the configuration's canonical origin allow-list, preventing a
probe from reaching an undeclared host. Loopback HTTP is permitted for an isolated local acceptance
environment; non-loopback endpoints require HTTPS. URLs with embedded credentials are rejected.

Endpoint validation is structural only. Day 5 sends no request and makes no readiness claim.
Registration intersects the declared origins with a separate operator-owned origin allow-list.

### Environment and secrets

Public environment bindings contain only values deliberately classified as safe to persist and show
in evidence. Secret-like names are rejected from the public set. Secret bindings contain only an
environment key and an opaque reference such as a secret-manager identifier; the referenced value is
never part of the configuration, digest input, error text, logs, or serialized state. A key cannot be
both public and secret.

The configuration service can additionally restrict accepted opaque references to operator-owned
prefixes. A matching prefix proves only that the identifier is routable under policy; it never
retrieves or validates a secret value.

Every declared public or secret target environment name must also appear in both the configuration's
exact environment allow-list and the operator's environment-name allow-list.

Secret lookup, injection, redaction during process execution, rotation, and provider authorization
remain provider responsibilities. Day 5 deliberately has no secret resolver.

### Acceptance-profile binding

The profile binding identifies a separately defined acceptance profile by ID, version, and canonical
digest. Its digest must be verified before a runtime-acceptance run is bound. The run must agree with
the configuration's product ID and exact commit. Binding rechecks the exact persisted revision and
the current operator policy, then retains the configuration ID, revision, configuration digest, and
profile binding. A newer configuration revision never changes an older run's authority.

## Revision and persistence rules

Configurations are immutable values. Creation establishes revision 1. An update requires the
caller's expected current revision, creates revision `N + 1`, and preserves every prior revision.
Stale writers fail rather than overwrite another actor's change.

Persistent storage is schema-versioned, product-isolated, deterministic, and atomic. Loading rejects
unsupported schema versions, malformed data, digest mismatches, missing revisions, and revision
history that is not contiguous. Configuration versions are ordered numerically. Persistence failures
must not leave a partially authoritative revision.

`FileRuntimeConfigurationStore` requires POSIX advisory locking and fails closed where that primitive
is unavailable; non-POSIX deployments must supply another `RuntimeConfigurationStore` implementation
rather than silently weakening cross-process compare-and-swap guarantees.

Successful first registration and revision can publish bounded lifecycle events. Event payloads bind
the configuration digest, commit, revision, and profile identity but omit public values and opaque
secret references. Idempotent registration does not emit a duplicate event.

Canonical digests preserve semantic list ordering, including command argument order. Maps are
canonically ordered. Timestamps and generated filenames are not used as substitute identity.

## Day 5 acceptance boundary

Day 5 is complete when automated tests prove:

- strict validation of product, source, command, URL, public-environment, secret-reference, and
  acceptance-profile fields;
- deterministic configuration and profile binding digests;
- immutable revision creation, optimistic updates, history retention, restart-safe persistence, and
  corruption rejection;
- exact binding between a compatible runtime-acceptance run and one configuration revision; and
- zero repository, subprocess, network, secret-resolution, service, or browser side effects.

Day 5 does **not** prove that a product starts or works. Day 6 creates and manages an isolated
environment at the configured exact SHA. Day 7 now consumes the same configuration through the
Chrome/Playwright customer-journey provider and collects real browser evidence. Remaining capability
proof, human acceptance, merge, deployment, and release remain separate explicit controls.

See `examples/managed_product_runtime_configuration.py` for a deterministic generic product
configuration. The example constructs a declaration only and intentionally performs no runtime
action.
