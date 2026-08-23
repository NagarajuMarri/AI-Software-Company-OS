# Controlled GitHub Delivery

Day 33 moves the exact Day 32 QA/Security-reviewed output to an open draft pull request and stops
before preview deployment. The runtime uses a generic fixture only; no official ASCOS pilot product
is selected.

## Exact source and authority

`GitHubDeliveryService` requires the canonical persisted Day 32 artifact in
`CODING_AND_REVIEWS_PASSED_AWAITING_CONTROLLED_GITHUB_DELIVERY`. The work order and current
human-issued authority bind its complete artifact digest, workspace digest, tenant, opportunity,
repository and workspace IDs, HTTPS GitHub identity, base branch/commit/tree, isolated feature
branch, reviewed file bindings, final diff digest, commit message, and draft-PR title/body.

Authority contains a closed action and tool profile with bounded path, Git-command, and controlled
network counts. It permits repository write, one commit, one push, and one draft PR only. Force push,
merge, deployment, and release flags are structurally rejected.

## Pre-delivery proof

Independent Git inspection proves the approved source branch, HEAD, tree, status, and remote remain
unchanged. The isolated workspace must still be on the exact Day 32 base, with precisely the sorted
reviewed dirty paths and an empty index. Every target must be a regular non-linked file whose SHA-256
matches review evidence. The registered remote must be the exact HTTPS GitHub identity.

Executable filters, hooks, filesystem monitors, credential configuration, HTTP extra headers, URL
rewrites, and configured push URLs are rejected. Unreviewed paths, staged changes, deletions,
renames, symlinks, special files, path escape, and digest drift fail before provider execution.

## Bounded delivery sequence

The provider performs the following fixed sequence:

1. prove the remote feature branch and matching pull request do not exist;
2. stage only the exact named reviewed paths;
3. create one non-GPG commit with the approved base as its only parent;
4. prove the commit path set equals the reviewed path set;
5. push one explicit feature-branch ref without force;
6. prove the remote ref equals the reviewed commit; and
7. create one open draft PR with exact base, head, commit, title, and body digest.

The adapter has no shell or general-command interface. Prompts, hooks, system/global Git config, and
credential helpers are disabled. A production gateway may use scoped opaque credential handles;
secret values are never part of a work order, observation, artifact, log, or evidence page.

## Reconciliation and stop boundary

A duplicate remote branch or PR stops before workspace mutation. If an error happens after a commit,
push, or PR effect, the provider raises reconciliation-required state. ASCOS does not reset, delete,
clean, overwrite, force-push, adopt, or blindly retry ambiguous external state.

On success the source is unchanged, the workspace is clean on the exact reviewed commit/tree, the
remote feature branch equals that commit, and the PR remains open, draft, and unmerged. The canonical
mode-0600 write-once artifact retains stable IDs, source digests, reviewed file hashes, commit/tree/
remote bindings, PR receipt, and bounded counts without a host path or credential. Exact retry and
restart reopen the artifact without another effect.

Day 33 does not approve or merge a PR, write a protected branch, force-push, deploy a preview or
production environment, release, accept risk, spend budget, or select an official pilot. Preview
deployment remains Day 34.
