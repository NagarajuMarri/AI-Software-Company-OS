# Milestone 12.5 managed-product pilot

The first real product pilot targets `NagarajuMarri/spoken-english-ai` and the
**Learner Daily Speaking Practice Web Shell**. ASCOS owns reconciliation,
knowledge binding, approval, provider routing, controlled patch application,
quality evidence, review, Git effects, and the draft-PR boundary. A provider may
generate bounded text changes but cannot approve, run commands, commit, push,
open a PR, merge, release, or deploy.

## Observed product baseline

Read-only reconciliation on 2026-08-03 found:

- repository: `https://github.com/NagarajuMarri/spoken-english-ai`
- default branch: `main`
- local and `origin/main`: `4c88b7edcb306ba736237e0cbcc289b5ca479543`
- working tree: clean; local main: not divergent
- latest merged milestone: Product Milestone 6, PR 5
- Milestone 7 exists locally and remotely at
  `cdeb27ab9eea2325a2b76c4580b2b1668dc07422`
- Milestone 7 is one commit based directly on current main, changes 59 paths,
  and has no open or recently closed pull request
- no `ascos/milestone-8-learner-web-shell` branch was observed

Milestone 7 remains unresolved product work. ASCOS must not merge it or duplicate
its AI/voice backend changes. The web-shell pilot remains bound to the observed
main SHA.

## Knowledge and plan

The main tree contains a FastAPI/SQLAlchemy backend with API routes under
`backend/app/api/routes`, JWT access and rotating opaque refresh-token flows,
conversation, curriculum/progress, and simulated voice modules. It has backend
tests, five Alembic migrations, and Markdown documentation. No frontend is
present. Snapshots exclude VCS metadata, `.env` files, credentials, virtual
environments, caches, dependency trees, build outputs, binaries, and secrets.

`learner_web_shell_request()` produces the approved change request. The epic is
**Learner Web Experience Foundation**, with six dependency-ordered bounded tasks
from `pilot_tasks()`. Each declares allowed and prohibited paths, acceptance
criteria, capabilities, gates, evidence, risk, output limit, timeout, and retry
policy. The human approval actor is `NagarajuMarri`; providers cannot approve or
review their own work.

## Current result

Final status is `PROVIDER_CONFIGURATION_REQUIRED`. `OPENAI_API_KEY` was not
present, and no enabled, authorized live provider with a durable response sink
was configured. The deterministic provider is used only by the temporary fixture.

ASCOS therefore did not create a product workspace or feature branch, invoke a
live provider, apply product changes, run product gates, commit, push, open a
product PR, merge, or deploy. To resume, an operator must configure an approved
model and credential through the secret boundary, explicitly authorize the live
operation, configure a durable response sink, and retain request/output limits.
The credential must never be printed, persisted, logged, or put in context.

## Codex CLI activation follow-up

The `codex-cli` adapter validates CLI `0.146.x`, uses the existing no-shell
argument-array runner, a read-only ephemeral sandbox, strict schema output,
workspace and environment allow-lists, bounded context/result/patch sizes,
request and wall-clock limits, and a durable receipt before returning success.
Authentication remains owned by the installed CLI; ASCOS does not inspect or
persist its credential files or tokens.

The first live fixture reached Codex CLI `0.146.0` with model `gpt-5.6-sol` and
persisted a complete receipt. The provider returned `SUCCEEDED` with no proposed
file operations. Independent verification rejected the result because
`docs/ascos-codex-smoke.txt` was absent. The adapter now rejects any successful
implementation result with zero operations and clarifies that Codex must propose,
but not directly apply, operations. In accordance with the live-smoke failure
policy, the request was not resubmitted and Spoken English Milestone 7 was not
opened or modified. Current state is `CODEX_LIVE_SMOKE_TEST_REQUIRED`.

A single operator-authorized V2 attempt then used the strict
`CodexCliResultEnvelopeV1` protocol in a fresh Git fixture. The CLI produced one
raw JSON envelope and a durable matching receipt, but returned terminal
`FAILED_PERMANENT`, zero operations, and claimed no implementation requirements
were provided despite the bounded task objective and acceptance criteria. ASCOS
did not parse the result as success, did not apply a patch, and did not retry.
The fixture therefore remains blocked at `CODEX_LIVE_SMOKE_TEST_REQUIRED`, and
Milestone 7 verification remains unstarted.

## Disposable observed-workspace mode

`DISPOSABLE_WORKSPACE_MUTATION` is now the primary Codex CLI mode. ASCOS copies
an exact clean Git baseline into a unique scratch workspace, removes remotes,
invokes Codex with workspace-write and approval policy `never`, and treats the
resulting Git status, diff, filesystem contents, and hashes as authoritative.
Codex summaries never determine success. Only an observed manifest is converted
to file operations for later ASCOS-controlled application to the final workspace.
Uncertain scratch state is retained for reconciliation and is never rerun
automatically.

The single V3 live attempt exited but produced no Git-observable file. It left a
`docs` directory and Git metadata inaccessible to the observing process under
Windows permissions, preventing trustworthy filesystem inspection and cleanup.
No manifest, converted result, or accepted receipt was created. The scratch
identity and baseline evidence were retained at `OBSERVATION_STARTED` and then
classified `RECONCILIATION_REQUIRED`. Per policy, Milestone 7 did not start and
the pilot remains `CODEX_LIVE_SMOKE_TEST_REQUIRED`.
