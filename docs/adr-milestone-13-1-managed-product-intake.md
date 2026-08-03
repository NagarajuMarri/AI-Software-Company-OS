# Architecture Decision: Human-Reviewed Managed Product Intake

Status: Accepted for Milestone 13.1

## Context

ASCOS PR #20 represents experimental fully autonomous Codex provider
integration. Its Windows scratch-workspace observer cannot reliably read every
file produced by the provider, so its retained V4 operation remains
`RECONCILIATION_REQUIRED`. The PR and branch preserve useful provider dispatch,
receipt, reconciliation, and scratch-isolation concepts for selective future
recovery.

## Decision

Milestone 13 human-reviewed delivery is the supported product-delivery mode.
PR #20 remains an unmerged draft and must not block human-reviewed product
progress. Its branch is preserved; no history or retained scratch evidence is
deleted.

Existing product work may enter ASCOS through an explicit
`EXISTING_PRODUCT_BRANCH` intake. Intake binds the exact base and head commits,
knowledge snapshot, changed paths and digests, historical implementation
source, required verification results, reviewer identity, and draft PR
evidence. It must state that ASCOS adopted the work for verification and
governance; it must not claim ASCOS originally implemented that work.

Failed or missing gates prevent review and PR attachment. Successful intake
stops at `WAITING_FOR_HUMAN_REVIEW`; it provides no automatic approval, merge,
deployment, branch rewrite, or branch deletion path.
