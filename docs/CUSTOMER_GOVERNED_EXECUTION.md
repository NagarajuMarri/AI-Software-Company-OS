# Completion Module 3 — Customer-governed product execution

Completion Module 3 is the first ASCOS completion module that joins the real authenticated customer
journey to governed product coding. It consumes only the exact locked customer request, approved
requirements, approved PRD, approved roadmap, delivery estimate, and deterministic progress
projection. It then uses the accepted Completion Module 2 Codex SDK adapter for one bounded task.

It is deliberately not a delivery or deployment module. A successful turn leaves a reviewed local
candidate patch with the original Git commit unchanged.

## Authority flow

1. An operator prepares a separate product Git repository on a clean existing `agent/*` branch.
2. The operator starts `ascos-local-uat` with the workspace, model, authentication mode, allowed
   product paths, and existing candidate context files. These values cannot come from the browser.
3. The signed-in customer completes and locks the normal ASCOS planning journey through the
   delivery estimate and project-progress page.
4. The customer opens **Governed product execution** and creates a plan. This operation is local and
   non-chargeable; it does not invoke Codex.
5. The dashboard displays the exact branch, commit, provider, model, authentication/billing source,
   ordered requirements, acceptance criteria, and write allow-list. The customer approves that
   exact scope digest.
6. ASCOS re-verifies the complete planning chain and clean workspace. The customer separately
   confirms the first task and one usage-bearing Codex turn.
7. Codex receives bounded text context in a read-only, deny-all SDK thread. It returns structured
   file operations; it cannot write the repository itself.
8. ASCOS verifies identity, billing metadata, text/path policy, unchanged read-only workspace, and
   the durable provider receipt. ASCOS then applies the validated local patch.
9. The dashboard records provider task ID, input/output units, request count, changed paths, and the
   patch-manifest digest, and stops at `REVIEW_REQUIRED`.

## Launcher example

ChatGPT subscription authentication on Windows PowerShell:

```powershell
ascos-local-uat `
  --data-dir .ascos-customer-uat `
  --execution-workspace C:\Projects\customer-product `
  --execution-model gpt-5.6-terra `
  --execution-auth-mode chatgpt-subscription `
  --execution-allowed-path src `
  --execution-allowed-path tests `
  --execution-candidate-file src\app.py `
  --execution-candidate-file tests\test_app.py `
  --enable-live-execution `
  --confirm-live-operation
```

Company OpenAI Platform billing uses the same workflow, but the operator supplies the key only in
the launcher environment:

```powershell
$env:OPENAI_API_KEY = "<company-managed-secret>"
ascos-local-uat `
  --execution-workspace C:\Projects\customer-product `
  --execution-auth-mode platform-api-key `
  --execution-allowed-path src `
  --execution-candidate-file src\app.py `
  --enable-live-execution `
  --confirm-live-operation
```

ASCOS never persists or displays the key. In ChatGPT-subscription mode it clears API-key and access
token variables in the Codex child and verifies the active local Codex account type. In Platform
mode it isolates the configured key from personal ChatGPT authentication. The dashboard always
names the selected billing source before the chargeable confirmation.

## Fail-closed rules

- The product workspace must exist, be a Git repository, be clean, and be on an `agent/*` branch.
- Its branch and exact pre-turn commit must still match at plan approval and execution.
- Allowed paths and candidate files are relative, bounded, unique, and operator-supplied. Git
  internals, credentials, environment files, CI workflows, deployment, infrastructure, migration,
  payment, private-key, and binary changes are blocked.
- Browser forms accept only CSRF, exact scope digest, and fixed confirmation fields. They accept no
  workspace path, key, model, file path, shell command, remote, or deployment target.
- Only the first pending task can run. A successful patch stops all remaining tasks.
- Any ambiguous live-provider or patch state becomes `RECONCILIATION_REQUIRED`; ASCOS never retries
  it automatically.

## Explicitly unavailable

Completion Module 3 cannot stage or commit the product patch, push a branch, open or update a pull
request, merge, create preview evidence, deploy, release, select a production target, or start
FamilyVault. Those require later completion modules and new founder authority after their own tests
and evidence.
