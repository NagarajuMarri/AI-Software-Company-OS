# Completion Module 4 — Customer-governed review and draft delivery

Completion Module 4 advances one exact Completion Module 3 result from
`REVIEW_REQUIRED` to `DRAFT_PR_CREATED`. It makes no LLM call. It cannot run the
next task, approve or merge a pull request, deploy preview or production,
release, or select FamilyVault.

## Authority flow

1. The operator starts the local launcher with the same trusted product
   workspace used for Module 3 plus a GitHub `owner/name`, integration base
   branch, and remote name. These fields are never browser inputs.
2. ASCOS reloads the exact Module 3 customer execution plan and accepted provider
   patch effect. It rechecks the customer/product/plan/workspace identities,
   `agent/*` branch, unchanged pre-turn commit, dirty path set, tracked Git diff,
   patch manifest, and content SHA-256 for every changed file.
3. The dashboard displays the repository identity, base/head branches, escaped
   canonical patch, file hashes, change counts, and locked review digest. It
   never displays the local workspace path, credential, token, or remote URL.
4. The customer approves that exact review digest. This performs no Git or
   GitHub mutation.
5. Live delivery requires both launcher flags
   `--enable-product-delivery` and
   `--confirm-product-repository-write`, plus a separate fixed customer
   confirmation on the approved review.
6. Preflight verifies the local review again, requires the exact HTTPS GitHub
   push identity, and proves the feature branch and matching PR do not already
   exist remotely.
7. The closed adapter stages only reviewed paths, creates one non-GPG
   single-parent commit, verifies its path set and parent, pushes only the
   `agent/*` head without force, and verifies the remote SHA.
8. The GitHub gateway opens one PR in open draft state with the locked
   base/head/title/body. ASCOS records commit, tree, PR number, and URL, then
   stops.

## Authentication

Git push uses the operator's existing credential-safe Git configuration.
Draft-PR creation uses an existing GitHub CLI login or its operator-managed
environment. ASCOS does not accept a GitHub token in a browser form, include a
token in Git arguments, or persist a credential. Provider keys and Codex tokens
are removed from Git subprocesses.

## Fail-closed and reconciliation rules

- Any Module 3 status other than `REVIEW_REQUIRED`, more or fewer than one
  completed task, missing accepted patch evidence, branch/commit/path drift,
  digest mismatch, unsafe file, binary/non-UTF-8 review content, or oversized
  patch prevents approval or delivery.
- A stale review digest, malformed form, cross-customer request, or absent fixed
  confirmation performs no effect.
- A pre-existing remote branch or matching PR stops before staging or commit.
- Delivery intent is persisted before the first repository mutation. Any later
  exception becomes `RECONCILIATION_REQUIRED`; ASCOS does not reset the commit,
  delete the branch/PR, overwrite, force-push, or retry automatically.
- Exact successful retry returns the existing receipt without a second commit,
  push, or PR.

## Remaining completion boundary

An open draft PR is review evidence, not a release. Preview deployment, cloud
browser end-user testing against the deployed product, PR approval/merge,
production deployment, and release remain later separately authorized
completion modules.
