# Managed Product Environment Lifecycle

Day 6 consumes one exact persisted Managed Product Runtime Configuration and verifies that its source,
migrations, services, readiness declarations, shutdown, and disposable-workspace cleanup operate as
declared. This is the first runtime side-effect boundary in the acceptance engine.

It is deliberately not itself a browser, deployment, merge, release, or production-hosting
capability. Day 7 composes it through `verify_with_ready_probe`, so Playwright runs only after
readiness and still passes through reverse shutdown and cleanup.

## Authority and policy

An `EnvironmentExecutionRequest` binds a safe run ID to the configuration's project ID,
configuration ID, positive revision, and canonical digest. `ManagedProductEnvironmentService` loads
that exact immutable revision from `RuntimeConfigurationStore`; caller-supplied configuration objects
are not execution authority. A mismatched digest fails before secret lookup, Git, process, or network
activity.

Execution rechecks current operator policy for:

- repository host;
- every migration, start, and stop executable;
- every declared runtime origin;
- every public or secret environment target name; and
- every opaque secret reference or approved reference prefix.

A declaration accepted under older policy therefore cannot run after policy is tightened.

## Exact-SHA workspace

`LocalManagedProductEnvironmentProvider` creates a run-specific disposable clone below one
operator-owned workspace root. Git runs with terminal prompting disabled, system/global Git config
disabled, and a private temporary home. The configured branch is cloned without tags, the configured
full commit is checked out detached, and the observed `HEAD` must match exactly. All remotes are then
removed before product commands run.

The provider rejects pre-existing run directories, an unsafe root, a missing Git layout, working
directory escape, and any workspace symlink whose resolved target escapes the clone. It never writes
to the registered source repository and exposes no commit, push, pull-request, merge, or deployment
operation.

## Secrets and commands

Public environment values come from the persisted configuration. Secret values are obtained only at
the execution boundary through an injected `RuntimeSecretResolver`. Resolution must produce a
bounded, non-empty, NUL-free string. Values are passed only to declared product processes, cleared
from the in-memory environment mapping after the run, and never placed in results, observations,
errors, digests, workspace identifiers, or event metadata.

Migration and service commands remain immutable argument arrays and run with `shell=False`. The
process environment starts from only the executable search path (and Windows system root when
required), plus the configuration's exact allow-listed values. Migration output is bounded, values
resolved as secrets are replaced before hashing, and raw output is not retained.

## Lifecycle

One verification run performs this order:

1. load and re-authorize the exact configuration revision;
2. resolve approved opaque secret references;
3. clone and verify the exact detached commit;
4. remove every Git remote;
5. run migrations in declared order;
6. start services in declared order;
7. probe each declared readiness endpoint without proxy inheritance or HTTP redirects;
8. execute declared stop commands and stop processes in reverse order; and
9. remove the disposable workspace.

Shutdown runs after migration/startup/readiness failure for every process that was started. A failed
declared stop is recorded even if forced termination succeeds. If a process or workspace cannot be
proven safely stopped or removed, the terminal state is `RECONCILIATION_REQUIRED` and the workspace
is retained. Otherwise a failed verification is `FAILED`; a complete verified lifecycle is
`STOPPED`.

A retained workspace is not evidence-safe storage: product code may have written runtime data while
it held injected values. Operators must isolate access, treat the directory as potentially sensitive,
stop any remaining process, reconcile the failure, and remove it through an approved cleanup path.

## Evidence boundary

`ManagedProductEnvironmentResult` is a terminal, immutable, digestible summary. Observations cover
source, migrations, service startup, readiness, service stop, and cleanup with UTC timing, outcome,
exit/status code, and a digest of bounded redacted output. The result contains no raw command output,
secret reference, secret value, process handle, or local workspace path.

These observations prove the environment portion of runtime acceptance. Day 7 now binds them to
browser, console, network, screenshot, and journey results for the same configuration and commit.
The complete runtime acceptance lifecycle still awaits Days 8–10 capability evidence.

## Day 6 acceptance boundary

Day 6 is complete when deterministic tests prove:

- a real loopback-served Git fixture is cloned, pinned to the exact configured SHA, and stripped of
  remotes;
- a real migration, service process, readiness HTTP request, declared stop, and cleanup succeed;
- stale/tampered authority and tightened operator policy fail before runtime effects;
- missing secrets, wrong commits, migration failures, readiness failures, stop failures, symlink
  escape, and cleanup failures fail closed with bounded terminal results;
- services are stopped and workspaces cleaned after failure whenever safe; and
- secrets and provider output never enter the returned authority record.

Production repository credentials, distributed environment workers, durable in-flight recovery,
host/container isolation and production deployment remain later work. The
included local provider is POSIX-only because it uses a new process group to stop the complete
declared service tree; Windows must supply a future Job Object or equivalent provider and fails
closed rather than silently weakening shutdown guarantees.
