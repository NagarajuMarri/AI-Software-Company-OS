# Governed Codex SDK execution

ASCOS Completion Module 2 connects approved managed coding tasks to the stable
Python Codex SDK. It is the first completion module that can ask a real Codex
model to generate product code. It deliberately preserves the existing ASCOS
approval, workspace, patch, test, review, and delivery gates instead of granting
the model direct repository authority.

## Execution flow

1. A human-approved managed execution plan selects one task, branch, workspace,
   path policy, bounded repository context, acceptance criteria, and quality
   gates.
2. ASCOS persists the exact provider intent before invoking Codex.
3. The operator explicitly enables the live provider and separately confirms
   usage consumption.
4. ASCOS verifies the exact Git branch and records the clean workspace digest.
5. Codex runs one identifiable thread with `ApprovalMode.deny_all` and
   `Sandbox.read_only` and returns schema-constrained file operations.
6. ASCOS rejects any workspace mutation during the model turn, validates the
   durable response receipt, and records the selected billing source.
7. The controlled patch boundary independently checks every returned path,
   operation, content limit, symlink boundary, and change policy before writing.
8. ASCOS runs the plan's fixed-argument quality gates, builds review evidence,
   and waits for human completion approval before any draft delivery action.

The model never receives approval, GitHub, merge, deployment, release, billing
selection, or pilot-selection authority.

## Authentication and billing

The adapter uses the same explicit modes established by Completion Module 1:

| Mode | Credential location | Recorded billing source |
| --- | --- | --- |
| `chatgpt-subscription` | Customer's existing local `codex login` session | `chatgpt-plan` |
| `platform-api-key` | Trusted process environment `OPENAI_API_KEY` | `openai-platform` |

ChatGPT mode clears API-key and access-token variables in the SDK child and
fails unless the active Codex account type is `chatgpt`. Platform mode clears
personal authentication, authenticates through the SDK's API-key login method,
and creates a temporary isolated `CODEX_HOME`. ASCOS never
persists the credential value, account email, authentication cache, or raw
provider response.

## Required live-use controls

The provider configuration must set `enabled=True` and
`live_operation_confirmed=True`. The actual submission must also provide both
`allow_live_provider=True` and `confirm_usage_consumption=True`. These are
independent controls; selecting an authentication mode or passing preflight
does not silently authorize a charged coding turn.

## Remaining completion work

This module supplies the real governed coding adapter, but it does not yet make
the local customer dashboard automatically compose and operate the entire
execution chain. Later completion modules must wire provider selection and
secret references into the launcher, add bounded repair turns after failed
quality gates, provide founder-safe execution progress and review controls, and
prove one generic end-to-end product build before ASCOS is declared ready for a
real customer pilot. FamilyVault is not selected or developed by this module.

Official references: [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk) and
[Codex authentication](https://learn.chatgpt.com/docs/auth).
