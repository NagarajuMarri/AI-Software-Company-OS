# Preview Deployment

Day 34 deploys the exact human-authorized Day 33 commit to one isolated, non-production preview and
stops before complete Chrome runtime acceptance. The runtime fixture is generic verification data;
no official ASCOS pilot product is selected.

## Exact persisted sources

`PreviewDeploymentService` reloads both inputs from their canonical stores. The Day 33 artifact must
still prove one exact reviewed commit, one non-force feature-branch push, and one open draft PR bound
to the same commit/tree, with zero merge, deployment, and release effects. The Day 28 artifact must
bind the same QA and Security digests and provide exact preview, migration, deployment, monitoring,
and rollback plans whose target is `ISOLATED_NON_PRODUCTION_PREVIEW` and whose execution state is
still `NOT_EXECUTED`.

The work order and current founder-issued authority bind both artifact digests, tenant, opportunity,
repository, feature branch, draft-PR receipt, commit/tree, isolated environment ID, preview URL,
every operational plan digest, a non-secret configuration digest, sorted opaque secret-reference
IDs, exact health endpoints, and a bounded preview lifetime. Drift, expiry, missing persistence,
cross-tenant sources, changed plans, production targets, or elevated authority fail before the
provider runs.

## Closed platform effect

The provider-neutral gateway has only three operations: find an exact preview environment, create
one preview deployment, and inspect its immutable receipt. The controlled provider requires the
environment not to exist, deploys the exact approved commit/tree once, applies the preview-only
migration, enables preview monitoring, and requires every declared health endpoint to return HTTP
200. URLs are HTTPS and constrained to the approved non-production preview origin.

Only opaque credential handles may be resolved by a real platform adapter at invocation. Raw secret
values are excluded from every model, artifact, log, error, and evidence record. The gateway has no
general command, PR approval, merge, production deployment, promotion, release, billing, or pilot
operation.

## Reconciliation and persistence

A duplicate environment stops before another deployment. If an exception happens after the create
effect may have started, the provider raises reconciliation-required state. ASCOS does not adopt,
overwrite, delete, redeploy, promote, roll back, or blindly retry ambiguous external state.

On success, a canonical mode-0600 write-once artifact records stable IDs and digests, the complete
Day 26/27/28/30/31/32/33 source chain, exact commit/tree, deployment revision, health receipts,
active isolated-preview state, one migration, one monitoring configuration, bounded expiry, and
rollback readiness. It stores no host path or raw credential. Exact retry and restart reopen the
same artifact without a second platform effect; closed-directory, permission, schema, canonical,
identity, and integrity checks reject tampering.

## Evidence and stop boundary

Exact-head Chromium verification renders the exact source chain, environment identity, commit/tree,
two healthy checks, one preview deployment, one migration, one monitoring configuration, zero
production/merge/release/secret effects, restrictive headers, and empty browser console/network
failure collections.

Day 34 does not approve or merge the draft PR, deploy or promote production, execute rollback,
release, bill, spend budget, accept risk, select an official pilot, or perform the complete login and
module-specific product journeys. Those Chrome runtime-acceptance journeys remain Day 35.
