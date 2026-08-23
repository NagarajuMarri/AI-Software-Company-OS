# Digital Twin Execution Runtime

Day 22 turns the technology-independent Digital Twin architecture into one bounded operational
runtime. It supplies the provider-neutral execution foundation required by later workforce modules;
it does not implement any specialized workforce role.

## Contract

`DigitalTwinDefinition` aligns one fulfilment identity to exactly one existing `AgentRole`. It names
one provider, declared capabilities, and the maximum set of tools approved for that Twin. A
`DigitalTwinAssignment` narrows that definition to one tenant, objective, bounded non-secret context,
required capabilities, requested tools, and exact `DelegatedAuthority` digest.

The delegation grant independently binds:

- issuer, tenant, assignment, Twin, and Business Role;
- the SHA-256 digest of the exact objective;
- explicit allowed actions and tool IDs;
- issue/expiry times with a maximum 24-hour lifetime;
- maximum tool calls and total output bytes; and
- whether a live provider may be considered.

The model rejects grants that omit assigned-work authority or attempt to include governance change,
approval, product-repository write, commit, merge, deployment, release, billing, or pilot selection.
The runtime then compares every identity and digest again immediately before provider selection.

## Provider and tool boundaries

`DigitalTwinProvider` is a replaceable protocol. A provider declares supported roles, capabilities,
and tools. It receives only `ProviderExecutionRequest` plus `DigitalTwinToolGateway`; it is not given
the persistence store or any ambient filesystem, process, repository, network, secret, or deployment
adapter.

`DigitalTwinToolRegistry` accepts only tools declaring `read_only=True` in Day 22. The gateway checks
the exact requested-tool allowlist and call/output budget at each invocation. Inputs and outputs are
closed bounded string maps whose keys cannot be secret-bearing. Returned values remain in memory;
the durable receipt stores only request/response digests and a sanitized outcome. The included
`ReadOnlyRecordTool` and `DeterministicDigitalTwinProvider` form the offline runtime-verification
composition. They are neither a product implementation nor a specialized QA agent.

Live providers are supported as a contract boundary, not shipped or invoked by this module. A
provider marked live can run only when the delegation and the runtime operator independently allow
it. If a process restarts after a live intent was persisted but before its receipt exists, ASCOS
requires reconciliation and does not resubmit blindly.

## Durable execution

Before provider activity, `FileDigitalTwinExecutionStore` exclusively writes a canonical execution
intent. After the bounded call, the runtime writes one canonical terminal receipt containing:

- exact Twin, assignment, delegation, provider-request, and intent digests;
- terminal `SUCCEEDED` or sanitized `FAILED` status;
- a digest of structured provider output, not its values;
- ordered digest-only tool-call evidence; and
- UTC start/completion times.

The store uses per-execution file locking, tenant/execution path containment, closed directories,
mode-0600 files, bounded reads, canonical schema envelopes, and symlink, permission, identity,
schema, and digest validation. Exact retry or restart returns the same receipt without invoking the
provider again.

## Verification and evidence

Unit and security tests cover successful execution, exact retry/restart, role/tenant/objective and
authority mismatches, expiration, prohibited actions, capability incompatibility, unapproved tools,
tool-call budgets, malformed or secret-bearing provider data, provider exceptions, live-provider
dual authorization, mode-0600 persistence, tampering, symlinks, and unknown entries.

Mandatory Chromium CI opens a restrictive-header runtime-evidence report for a generic fixture,
verifies the exact authority/assignment/provider/tool/receipt facts, and uploads
`day22-founder-digital-twin-runtime`. Its manifest binds the exact PR head and approved Day 21 base
to all runtime digests and the screenshot hash.

## Explicit exclusions

Day 22 does not implement the CEO, Product Manager, Software Architect, engineering, QA, Security,
DevOps, Documentation, or multi-agent orchestration behaviors assigned to Days 23–30. It creates no
product task or workspace and exposes no product repository, command, network, coding, approval,
merge, deployment, release, billing, or pilot-selection authority. No official pilot product has
been selected.
