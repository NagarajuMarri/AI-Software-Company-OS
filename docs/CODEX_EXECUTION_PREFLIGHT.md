# Codex execution preflight

ASCOS uses **Codex**, not an interactive ChatGPT Work conversation, as its programmatic coding
specialist. ChatGPT Work remains the founder supervision and approval surface. The local ASCOS
runtime connects to Codex through the stable Python Codex SDK; later completion modules will place
that specialist behind the existing governed task, workspace, review, and evidence boundaries.

This module deliberately proves one explicitly selected authentication/billing mode and one
optional read-only live invocation only. It does not create a product repository, generate or
apply code, run product commands, commit, push, create a pull request, deploy, release, or consume
plan/API usage beyond the separately confirmed preflight call.

## Authentication and billing modes

ASCOS never silently chooses or changes the Codex billing source. The operator must select exactly
one mode:

| Mode | Where it runs | Authentication | Usage source |
| --- | --- | --- | --- |
| `chatgpt-subscription` | Customer's trusted local runner | Existing `codex login` session | Customer's eligible ChatGPT plan/credits |
| `platform-api-key` | Trusted local or company runner | `OPENAI_API_KEY` from the process environment | Company's OpenAI Platform account |

Personal ChatGPT authentication is local-only. ASCOS does not request a ChatGPT password, copy an
authentication cache, upload the cache to a hosted service, or share one customer's session with
another customer. The Codex SDK reads the active local account and ASCOS verifies that its type is
`chatgpt` before any model turn.

Platform mode reads only `OPENAI_API_KEY`, gives its value to an isolated Codex process, clears
conflicting ChatGPT/access-token variables in that process, and uses a temporary isolated
`CODEX_HOME` so a personal cached session cannot take precedence. The API key is never included in
a result or error message. Its validity is checked only by the separately confirmed live call.

## Install the optional SDK

From the ASCOS virtual environment:

```powershell
python -m pip install -e ".[codex]"
```

## Personal ChatGPT plan setup

On the customer's trusted computer, install the Codex CLI, then run:

```powershell
codex login
codex login status
```

The browser sign-in belongs to the customer and remains in the local Codex/OS credential store.
After login, run the non-billable static readiness check:

```powershell
ascos-codex-preflight `
  --workspace C:\Projects\pilot-product `
  --model gpt-5.6-terra `
  --auth-mode chatgpt-subscription `
  --enable-live-provider
```

## Company Platform API setup

Keep the API key only in the trusted process environment or production secret manager. Never paste
it into ASCOS forms, prompts, source files, Git configuration, screenshots, logs, or chat messages.

```powershell
$env:OPENAI_API_KEY="<set-locally-never-paste-in-chat>"

ascos-codex-preflight `
  --workspace C:\Projects\pilot-product `
  --model gpt-5.6-terra `
  --auth-mode platform-api-key `
  --enable-live-provider
```

## Static readiness check

The static check loads the SDK and verifies a non-root, non-symlink Git workspace. In ChatGPT mode,
it also reads the active local Codex account type and fails closed unless it is `chatgpt`. In
Platform mode, it checks the approved environment variable locally and does not test the key. It
starts no model turn and consumes no model tokens.

## Explicit read-only live check

The live check requires all three live-operation flags. It starts one Codex thread in the SDK's
read-only sandbox, requests one fixed sentinel response, and rejects the result if Git state changes.
It consumes either ChatGPT plan usage or Platform API tokens according to `--auth-mode`.

```powershell
ascos-codex-preflight `
  --workspace C:\Projects\pilot-product `
  --model gpt-5.6-terra `
  --auth-mode chatgpt-subscription `
  --enable-live-provider `
  --confirm-live-operation `
  --live-check `
  --confirm-usage-consumption
```

For company API billing, change only `--auth-mode` to `platform-api-key` after setting the local
environment variable. The JSON result contains the provider ID, model, authentication mode,
billing source, safe credential-environment name when applicable, safe ChatGPT plan label when
applicable, sandbox, workspace digest, timestamp, and readiness state. It never contains a
credential value, email address, authentication token, cache path, or raw provider response.

Passing this preflight means `CONFIGURATION_READY` or `LIVE_VERIFIED`; it does **not** by itself
mean ASCOS can develop a product. Completion Module 2 adds the governed Codex SDK execution adapter
described in `CODEX_SDK_EXECUTION.md`. Later modules must still compose that adapter into the local
customer application, bounded repair loop, founder review surface, and generic end-to-end readiness
pilot.

The execution integration persists only the selected authentication mode and an opaque
company-secret reference. It never persists a raw API key, personal ChatGPT credential, Codex
authentication cache, or email address. Every execution receipt identifies `chatgpt-plan` or
`openai-platform` as the billing source, and changing that source requires a new explicit customer
authorization.

Official references: [Codex authentication](https://learn.chatgpt.com/docs/auth) and
[Codex SDK](https://learn.chatgpt.com/docs/codex-sdk).
