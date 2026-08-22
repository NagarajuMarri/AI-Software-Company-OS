# ASCOS V1 unified local UAT launcher

The unified launcher runs the real ASCOS customer application in one local browser experience. It
is intended for founder/user-acceptance testing on one computer. It is deliberately not a
production web server and does not grant the governed workforce or delivery modules live external
authority.

## What you can test

The interactive path uses the persisted Days 11–21 application services:

1. Create a local customer account or sign in again.
2. Submit a product idea.
3. Refine, review, approve, and lock requirements.
4. Generate, review, approve, and lock the PRD.
5. Generate, review, approve, and lock the roadmap.
6. Generate the non-binding delivery-effort estimate.
7. Inspect the read-only project-progress projection.
8. Open the governed execution centre. With optional operator configuration, create and approve an
   exact task plan and authorize one Codex coding turn.
9. Inspect the Preview and Evidence Centre's truthful waiting state.
10. Stop and restart the launcher and verify that the account and product remain available.

The `/uat` page also explains the Days 22–37 runtime boundary. The default launcher does not start a
live provider. If the operator explicitly binds a trusted product workspace and enables Completion
Module 3, the customer may authorize one usage-bearing Codex turn. The launcher never creates the
repository, commits, pushes, opens a PR, creates a preview, deploys, releases, or silently bills.

## Run on Windows PowerShell or the VS Code PowerShell terminal

Playwright and WSL are **not required** to use the launcher. From the repository directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
ascos-local-uat
```

If the virtual environment is already active, run only the last two commands. The default browser
opens automatically at `http://127.0.0.1:8765`.

If PowerShell cannot find the installed command, use the equivalent module command:

```powershell
python -m runtime.local_uat
```

## Run on macOS, Linux, or WSL

```console
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
ascos-local-uat
```

The launcher does not need Playwright, so an unsupported Playwright/Ubuntu combination does not
block manual local UAT.

## Useful options

Use a different loopback port:

```console
ascos-local-uat --port 8877
```

Choose a different persistent data directory:

```console
ascos-local-uat --data-dir local-founder-uat
```

Do not open the browser automatically:

```console
ascos-local-uat --no-browser
```

To opt into Completion Module 3, first prepare a separate clean product repository on an existing
`agent/*` branch. Then declare only the product paths and existing context files Codex may use:

```powershell
ascos-local-uat `
  --execution-workspace C:\Projects\customer-product `
  --execution-model gpt-5.6-terra `
  --execution-auth-mode chatgpt-subscription `
  --execution-allowed-path src `
  --execution-candidate-file src\app.py `
  --enable-live-execution `
  --confirm-live-operation
```

The customer must still approve the exact generated plan and then check two separate boxes for the
first coding task and usage consumption. For company API billing, set `OPENAI_API_KEY` in the
launcher environment and select `--execution-auth-mode platform-api-key`. Never paste a key into
the dashboard. See `CUSTOMER_GOVERNED_EXECUTION.md` for the full flow and stop conditions.

To opt into Completion Module 4 review only, add the trusted GitHub repository
and integration target. This prepares and displays evidence but still performs
no repository write:

```powershell
ascos-local-uat `
  --execution-workspace C:\Projects\customer-product `
  --execution-allowed-path src `
  --execution-candidate-file src\app.py `
  --delivery-repository company/customer-product `
  --delivery-base-branch main
```

After local review UAT succeeds, intentionally enable one commit, non-force
feature-branch push, and open draft PR by adding both repository-write flags:

```powershell
  --enable-product-delivery `
  --confirm-product-repository-write
```

The product workspace must already use the approved `agent/*` branch. Git push
authentication and an authenticated GitHub CLI (`gh auth status`) are
operator-managed; no token is entered in the ASCOS dashboard. The customer must
still approve the exact displayed patch and separately confirm draft delivery.
Success stops at an open draft PR. See `CUSTOMER_GOVERNED_DELIVERY.md`.

Press `Ctrl+C` in the terminal to stop the server. The health endpoint is
`http://127.0.0.1:8765/healthz`.

## Local data and reset

By default, accounts, sessions, product artifacts, approvals, and the local pre-authentication
secret are stored under `.ascos-uat-data/`. Keep that directory to test returning access.

To intentionally start a new blank UAT environment, stop the launcher and rename the directory,
for example:

```powershell
Rename-Item .ascos-uat-data .ascos-uat-data-backup
```

Renaming keeps the prior test data recoverable. Do not commit either directory.

## Does successful local UAT mean ASCOS can be deployed directly?

No. Successful local UAT makes the exact revision a stronger **deployment candidate**. The local
launcher uses Python's development WSGI server, loopback HTTP, and file-backed single-machine data;
these are intentionally not the production topology.

Before production deployment, the following separate gates remain:

| Gate | Why it is still required |
| --- | --- |
| Merge the reviewed integration PR | Establishes one approved source revision on `main`. |
| Select a production hosting target | Defines compute, network, domain, region, and operational ownership. |
| Configure production persistence | Replaces local files with the approved durable database and migration plan. |
| Configure secrets and HTTPS | Protects sessions, credentials, provider keys, and customer traffic. |
| Authorize live integrations | Selects and limits AI provider, GitHub, preview, and deployment credentials. |
| Run security and operational gates | Verifies backups, recovery, monitoring, rate limits, logs, and incident handling. |
| Deploy an isolated preview first | Produces real preview/test/security evidence without production promotion. |
| Perform post-deployment UAT | Confirms the deployed URL, browser journeys, health, persistence, and rollback. |
| Explicitly approve production release | Keeps merge, deployment, and release human-governed. |

The safe sequence is: **local UAT → review fixes → merge approved integration → configure a
production-grade environment → deploy preview → run exact deployed acceptance → explicit
production release approval**.
