# Milestone 13.1 — First Human-Reviewed Managed Product Intake

Milestone 13.1 adopts existing product branches into ASCOS without rewriting
their history or making a false implementation-origin claim. The intake model
records reconciliation, historical implementation evidence, exact commit and
diff identity, one immutable result per required gate, human reviewer
assignment, and draft pull-request evidence.

The Spoken English Product Milestone 7 intake identifies its implementation
source as `EXISTING_PRODUCT_BRANCH` and its provider as historical direct
Codex-assisted implementation. ASCOS did not originally implement that branch;
ASCOS now validates and presents it for human review.

The intake dashboard derives from persisted delivery state. It contains no
credentials or provider configuration. A restart restores branch binding,
verification evidence, reviewer, lifecycle, and PR evidence. Malformed state
fails as a complete load and cannot partially replace a valid live record.

The deterministic example uses a temporary Git repository and stops at
`WAITING_FOR_HUMAN_REVIEW`.
