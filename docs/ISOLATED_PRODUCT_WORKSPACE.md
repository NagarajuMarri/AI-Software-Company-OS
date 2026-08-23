# Isolated Product Workspace

## Scope

Day 31 implements the locked ASCOS isolated product-workspace boundary. One current human-issued
authority binds one work order to the exact persisted Day 30 orchestration artifact, registered
repository identity, approved base branch, exact 40-character base commit, new `agent/*` feature
branch, and caller-owned workspace identity. Verification uses a generic local fixture; it does not
select or modify an official pilot product.

## Exact-base preparation

`ProductWorkspaceService` verifies the persisted orchestration source and authority before calling
the replaceable `ProductWorkspaceProvider`. `LocalGitWorktreeProvider` is the bounded operational
adapter. It uses Git argument arrays with terminal prompting, global/system configuration, hooks,
and credentials disabled. It performs no fetch, clone, push, or other network action.

Before creating anything, the adapter requires:

- a real, non-symlink repository root on the approved base branch and exact commit;
- an empty tracked/untracked status and the exact registered HTTPS repository identity;
- no existing destination or feature branch;
- no tracked symlink, submodule, or protected `.git` entry; and
- no repository-local filter, hook-path, fsmonitor, credential, or URL-rewrite configuration.

It then creates one linked worktree and one new `agent/*` feature branch at the approved commit.
After creation it proves that the source branch, HEAD, tree, and clean status did not change, and
that the new workspace is clean with the same HEAD/tree. Existing or partial state is never reset,
deleted, overwritten, cleaned, or silently adopted; it requires explicit reconciliation.

## Artifact and recovery

The immutable artifact binds the orchestration source, work order, authority, repository
registration, workspace identity, exact base/feature refs, source/workspace Git trees, bounded Git
operation count, and zero network/general-command/product-file-write/unrelated-change counts. It
stores only the workspace identity and root-relative name, never the caller's host path.

Canonical mode-0600 tenant/execution persistence is closed-schema, bounded, path-contained,
write-once, and digest checked. Exact retry or restart reopens the same artifact without invoking
Git again. Changed work, authority, source, repository, branch, base, or workspace identity
conflicts with the immutable record.

## Authority boundary

Day 31 grants one specialized `LOCAL_GIT_WORKTREE` adapter and only exact-base verification,
worktree creation, feature-branch creation, source-preservation verification, and status reporting.
It grants no general command runner, network, credentials, product-file mutation, coding provider,
test execution, Security scan, commit, push, pull request, merge, deployment, release, billing,
budget, risk acceptance, or pilot selection. Day 32 coding and review behavior requires separate
founder authorization.

## Verification

Focused tests exercise exact workspace creation, source preservation, retry/restart idempotency,
source/authority drift, dirty repositories, wrong branches/commits/identities, existing targets and
branches, symlinks, custom Git filters, provider-output drift, persistence closure, permissions,
path containment, and tamper detection. Real Chromium renders a founder-safe exact-commit report
with no local host paths and records screenshot, console, network, source, authority, base, branch,
tree, state, and artifact evidence.
