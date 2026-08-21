# ASCOS V1 — Founder-Locked 37-Module Plan

This is the durable repository source of truth for the founder-authoritative plan supplied on
20 August 2026. A day means one bounded implementation module. If a module fails testing or
acceptance, work continues on that same module; incomplete work is never marked complete. Module
numbers, names, ordering, and completion requirements must not be compressed, renumbered, or
reconstructed from chat summaries.

## Locked daily Definition of Done

Every module must pass:

1. Requirements confirmed.
2. Implemented on an `agent/*` branch.
3. Automated tests passed.
4. Actual runtime tested.
5. Evidence linked to the exact commit.
6. Security and regression checks passed.
7. Draft PR reviewed.
8. Founder acceptance obtained when required.
9. Only then proceed to the next module.

No agent may automatically approve, merge, deploy, or release its own work.

## Phase 1 — Repair and stabilize ASCOS

| Day | Module | Completion requirement |
| ---: | --- | --- |
| 1 | CI and Python packaging repair | `pyproject.toml` corrected; clean GitHub CI passes |
| 2 | Legacy PR #20 reconciliation | Python 3.11 cleanup fixed; retained work preserved; PR updated or safely superseded |
| 3 | Milestone 15 completion | Runtime-acceptance PR #26 passes CI and becomes review-ready; merge only after approval |
| 4 | PostgreSQL production validation | Real PostgreSQL concurrency, migration and recovery CI passes |

## Phase 2 — Real end-user testing engine

| Day | Module | Completion requirement |
| ---: | --- | --- |
| 5 | Managed-product runtime configuration | Product repo, branch, SHA, commands, URLs, environment and secret references defined |
| 6 | Environment lifecycle provider | ASCOS checks out exact SHA, runs migrations, starts services, waits for readiness and stops safely |
| 7 | Chrome/Playwright provider | Real browser opens; screenshots, console and network evidence collected |
| 8 | Authentication journeys | Registration, login, logout, session restoration and password recovery tested |
| 9 | Failure-to-repair loop | Failed journeys reopen development tasks and require correction plus complete retesting |
| 10 | Acceptance and release binding | Releases blocked unless exact-commit runtime and required human evidence are complete |

## Phase 3 — ASCOS customer application

| Day | Module | Completion requirement |
| ---: | --- | --- |
| 11 | ASCOS service API | Secure API exposes products, requirements, plans, agents, runs and evidence |
| 12 | Customer accounts and tenancy | Signup, login, logout, recovery and isolated customer workspaces work |
| 13 | Control Center frontend | Responsive dashboard shell, navigation and protected routes work |
| 14 | New Product intake | Customer can describe product, users, platforms, features, priorities and constraints |
| 15 | Product Manager clarification | PM agent asks structured follow-up questions and records confirmed answers |
| 16 | PRD generation | Approved intake becomes a traceable versioned PRD |
| 17 | PRD review and locking | Customer can revise, approve and lock the exact PRD version |
| 18 | Architecture and work-package proposal | ASCOS produces architecture, milestones, dependencies and work packages |
| 19 | Plan approval controls | Customer can approve, reject or request changes; execution cannot start without approval |
| 20 | Project progress dashboard | Milestones, tasks, agents, progress, blockers and decisions are visible |
| 21 | Preview and evidence centre | Customer can open product previews, inspect test evidence and submit ACCEPT/REVISE |

## Phase 4 — Operational multi-agent workforce

| Day | Module | Completion requirement |
| ---: | --- | --- |
| 22 | Digital Twin execution runtime | Real provider-neutral agents can receive bounded roles, tools and authority |
| 23 | CEO and Product Manager agents | Opportunity intake, scope clarification, product planning and status reporting work |
| 24 | Software Architect agent | Architecture proposal, technology selection, ADRs and risk identification work |
| 25 | Engineering agent family | Backend, frontend, AI and data assignments execute through one governed engineering runtime |
| 26 | QA Engineer agent | Test plans, automated tests, integration tests and defect reports work |
| 27 | Security Engineer agent | Threat model, dependency checks, secret checks and security findings work |
| 28 | DevOps Engineer agent | CI, preview environment, migrations, deployment plan, monitoring and rollback preparation work |
| 29 | Documentation Engineer agent | Technical, user, API, operations and release documentation generated and validated |
| 30 | Multi-agent orchestration | Dependencies, parallel work, context sharing, handoffs, conflicts and escalations work |

## Phase 5 — Automatic product implementation

| Day | Module | Completion requirement |
| ---: | --- | --- |
| 31 | Isolated product workspace | ASCOS creates safe worktrees/branches without altering approved or unrelated work |
| 32 | Coding and review loop | Developers implement; QA/security review; failures return to the responsible agent |
| 33 | Controlled GitHub delivery | Exact reviewed files can be committed, pushed and opened as a draft PR after authorization |
| 34 | Preview deployment | Approved commit deploys to an isolated preview environment after human authorization |
| 35 | Complete runtime acceptance | ASCOS logs in and performs module-specific end-user journeys in Chrome |
| 36 | First end-to-end product pilot | One customer idea proceeds from intake through PRD, agents, code, testing and draft PR |
| 37 | ASCOS V1 hardening and acceptance | Security, backups, recovery, audit, monitoring, documentation and founder UAT complete |

## Mandatory human approvals

Founder approval remains required for final PRD, major architecture, material scope changes, paid
services or budget, product repository writes, merge, preview or production deployment, release,
and subjective UX, audio, voice, and visual acceptance.

## After ASCOS V1

Later modules may add Android emulator or physical-device testing, iOS testing, customer
subscriptions and billing, usage limits and development budgets, team/customer organization
accounts, notifications, multi-product portfolio management, agent performance and cost analytics,
and production deployment of ASCOS itself.

## Current bounded status

Days 1–31 have founder acceptance for continuation. Day 32 is the active module. Approval to start a
later module never implies authority to merge, deploy, release, or select an official pilot product.
Browser and workspace fixture products are test data only; no official ASCOS implementation pilot
is selected.
