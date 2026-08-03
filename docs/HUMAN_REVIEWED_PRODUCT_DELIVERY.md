# Human-Reviewed Product Delivery

Milestone 13 makes human-reviewed implementation the default ASCOS product
delivery model. Provider execution remains bounded: a provider may plan or
implement, but it cannot approve or authorize the merge of its own work.
Autonomous implementation is represented explicitly and rejected at runtime.

## Lifecycle and pipeline

The lifecycle is `PLANNED` -> `IMPLEMENTING` -> `IMPLEMENTED` ->
`WAITING_FOR_HUMAN_REVIEW` -> `APPROVED` -> `MERGED`. A reviewer may instead
move work to `CHANGES_REQUESTED`; the provider can then record a revised
implementation and repeat verification and review. Unmerged work may be
`CANCELLED`.

The delivery pipeline is:

1. Select project and milestone.
2. capture a knowledge snapshot;
3. record an implementation plan;
4. dispatch a provider;
5. record implementation and verification evidence;
6. request and record human review;
7. obtain explicit merge authorization and merge; and
8. create the next milestone.

`HUMAN_REVIEWED_IMPLEMENTATION` is the default execution mode.
`PLANNING_ONLY` cannot dispatch implementation. `IMPLEMENTATION_ONLY` stops
before the review workflow. `AUTONOMOUS_IMPLEMENTATION` remains disabled.
The Codex provider is unchanged and remains an optional, experimental provider.

## State and dashboard

`ProductDeliveryState` persists the project, current milestone, branch, pull
request, provider, execution mode, review state and immutable review history,
knowledge snapshot, implementation plan, latest commit, verification status,
pending actions, progress, implementer, merge authorizer, and next milestone.
The JSON store writes atomically through a temporary file and rejects unsafe
project identifiers. The in-memory store supports deterministic tests.

`ProductDashboard` is a read model exposing the project, milestone, branch,
pull request, provider, review state and reviewer, knowledge snapshot, latest
commit, pending actions, and progress.

## Trust boundary

Successful verification is mandatory before review. Reviewer identities are
recorded with decisions, timestamps, and comments. Identity comparisons are
case-insensitive to prevent trivial self-approval bypasses. Only the approving
reviewer may authorize merge, and merge cannot occur without that explicit
authorization.

The example in `examples/human_reviewed_delivery.py` uses deterministic local
providers and requires neither Codex invocation nor GitHub credentials.
