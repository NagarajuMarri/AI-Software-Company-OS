# Completion Module 5 — Isolated preview and end-user acceptance

Completion Module 5 is the last ASCOS completion module before a founder selects and describes a
real pilot product. It consumes only an exact Completion Module 4 `DRAFT_PR_CREATED` receipt. It
does not call Codex, alter the reviewed patch, approve or merge the pull request, deploy production,
release, or select FamilyVault.

## Authority flow

1. The operator binds a canonical HTTPS preview origin, a `preview-*` environment identity, a
   preview-only GitHub Actions workflow, exact automated-test and security job names, and one
   declarative browser plan when starting ASCOS. None of these values is accepted from a customer
   form.
2. ASCOS reloads the exact Module 4 record and binds repository, base/head branches, commit, tree,
   open draft PR, preview configuration digest, and ordered browser plan into one durable approval
   record. Preparing the record performs no external effect.
3. The customer reviews and approves that exact digest. Starting acceptance then requires two
   separate customer confirmations: one for isolated preview deployment and one for browser use.
4. Live execution additionally requires the three launcher flags
   `--enable-preview-acceptance`, `--confirm-preview-deployment`, and
   `--confirm-browser-execution`.
5. The closed GitHub CLI gateway rechecks that the PR is still open, draft, unmerged, and points at
   the exact commit. It dispatches only the operator-bound preview workflow on the exact `agent/*`
   branch with fixed `ascos_*` inputs.
6. ASCOS waits for that single correlated run, requires the exact automated-test and security jobs
   to succeed, and performs a bounded redirect-free health check against the approved preview
   origin.
7. A fresh Playwright Chromium context executes every locked accessible browser step. Network
   requests outside the allow-list are blocked. Opaque input references are resolved only at
   invocation from the launcher environment, masked in screenshots, and cleared from memory. By
   default Chromium runs on the trusted ASCOS runner; `--browser-cdp-reference` can instead name an
   environment variable containing an approved cloud-browser CDP endpoint.
8. ASCOS publishes exact-commit automated-test, security, browser, console, network, and screenshot
   evidence to the existing Preview and Evidence Centre. The customer makes the final product
   `ACCEPT` or `REVISE` decision there.

## Preview workflow contract

The product repository must already contain the configured preview-only `workflow_dispatch`
workflow. It must accept these string inputs:

- `ascos_commit_sha`
- `ascos_tree_sha`
- `ascos_preview_environment`
- `ascos_preview_url`
- `ascos_execution_id`

The workflow is responsible for deploying only the isolated non-production environment and must
contain the two operator-declared required jobs. ASCOS records the GitHub run/job URLs and IDs but
never stores a GitHub token. GitHub authentication comes from the operator's existing `gh` login.

## Declarative browser plan

`examples/preview_acceptance_plan.json` shows the closed version-1 schema. Plans may use the
existing `ROLE`, `LABEL`, `TEST_ID`, or `TEXT` locators and the bounded `CLICK`, `FILL`,
`ASSERT_VISIBLE`, `ASSERT_TEXT`, `ASSERT_URL_PATH`, `RELOAD`, and media assertions. Secret-bearing
fills must use an opaque `secret_reference`; the referenced environment variable is never written
to the plan, state record, logs, console/network artifacts, or screenshot.

For a cloud browser, put the provider's CDP/WebSocket endpoint in an operator-managed environment
variable and pass only that variable name with `--browser-cdp-reference`. The endpoint value (which
may contain a token) is resolved only for the single Playwright connection, treated as a redaction
value, and never persisted or displayed.

## Fail-closed behavior

- Any delivery, commit, tree, branch, PR, configuration, plan, or approval digest drift stops before
  dispatch.
- A missing/failed required workflow job, redirecting/unhealthy preview, unavailable browser,
  origin escape, console/page error, network failure, missing screenshot, or incomplete evidence
  cannot produce an acceptable package.
- Preview intent is persisted before dispatch. Any later ambiguous failure becomes
  `RECONCILIATION_REQUIRED`; ASCOS never blindly dispatches a second workflow or browser run.
- Exact successful retry returns the durable receipt without another deployment or browser effect.
- A failed evidence package cannot be accepted; the existing evidence centre requires `REVISE`.

## Completion boundary

When the Module 5 pull request and CI are accepted, ASCOS is technically ready for a founder-provided
pilot product. FamilyVault is not started by this module. A later explicit founder instruction must
provide its product details and authorize its real execution. PR merge, production deployment, and
release remain separate human-controlled product delivery decisions.
