# Coding and Review Loop

Day 32 turns the approved Day 31 isolated worktree into a bounded implementation workspace and
stops before Day 33 GitHub delivery. It is exercised with a generic fixture only; no official ASCOS
pilot product is selected.

## Exact source chain

`CodingReviewService` requires the exact canonical persisted instances of:

- the Day 30 orchestration artifact and complete source-set digest;
- the Day 31 isolated workspace artifact and exact repository/base/feature identities;
- the Day 26 QA artifact referenced by orchestration; and
- the Day 27 Security artifact that retains the same QA digest.

Tenant, opportunity, artifact digests, statuses, pilot state, repository identity, workspace ID,
base branch/commit/tree, and feature branch must all match the work order. Source substitution,
unpersisted objects, cross-tenant reuse, or authority drift fails before a provider effect.

## Role-owned implementation

The work order contains Backend, Frontend, AI, and Data assignments in canonical order. Each owns a
closed path set. QA owns only the declared test path. `CONTROLLED_TEXT_PATCH` accepts bounded UTF-8
text and rejects absolute/traversing paths, `.git`, symlinks, reparse points, special destinations,
duplicates, deletions, and ownership mismatch. Patches use exclusive staging, fsync, and atomic
replacement. The source repository is never a write target.

The default provider is deterministic and limited to the generic product fixture. It creates six
reviewed files across the four Engineering roles and QA. It is not a live coding-provider grant.

## QA, Security, and feedback routing

QA runs real fixed-argument pytest inside the isolated workspace with inherited credentials removed,
plugin autoload/cache and bytecode disabled, and network proxies closed. Raw output is not persisted;
only its digest, status, and test count are retained.

After QA passes, static Security review parses changed Python and checks dependency provenance,
forbidden network/command imports, unsafe dynamic execution, hard-coded secret-like values, and
syntax. The generic verification deliberately demonstrates the loop:

1. Round 1 fails QA and returns `QA_TEST_FAILURE` to Backend.
2. Round 2 consumes that feedback and passes QA, but Security returns
   `UNSAFE_DYNAMIC_EXECUTION` to Backend.
3. Round 3 consumes the Security feedback and passes both reviews.

Every finding has one reviewer, responsible Engineering role, severity, path, and immutable return
route. A revision that does not consume the exact previous finding codes fails closed. Exhausted
rounds never produce a success artifact.

## Stop boundary and persistence

Independent Git inspection runs before and after the provider. The source branch, HEAD, tree,
status, and remote identity must remain unchanged. Workspace HEAD/tree remain at the Day 31 base;
only approved dirty paths may exist and the Git index must be empty. Final state is
`DIRTY_REVIEWED_NOT_COMMITTED` and
`CODING_AND_REVIEWS_PASSED_AWAITING_CONTROLLED_GITHUB_DELIVERY`.

The canonical mode-0600 write-once artifact retains stable IDs, exact upstream digests, role-owned
file hashes, review rounds, failure routes, final diff digest, and bounded effect counts. It retains
no local host path or raw command output. Exact retry and restart reopen the same artifact without
repeating code writes or reviews.

Day 32 grants no live provider, network, credentials, general command runner, staging, commit, push,
pull request, merge, deployment, release, billing, budget action, risk acceptance, or pilot
selection. Those delivery effects remain Day 33 and later locked modules.
