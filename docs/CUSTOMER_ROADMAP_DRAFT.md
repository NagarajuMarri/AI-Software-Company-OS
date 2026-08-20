# Traceable Customer Roadmap Draft

Day 17 lets an authenticated customer create one deterministic roadmap v0.1 from the exact Day 16
locked PRD. It makes the first planning artifact visible without estimating, scheduling, assigning,
or implementing work.

## Contract

The generation checkpoint accepts only session CSRF and the exact rendered PRD-approval digest. The
service reloads the complete customer-owned request, requirements, requirements approval, PRD, PRD
approval, and governed locked document server-side. The resulting record binds every identity and
digest in that authority chain.

ASCOS reuses `ProductRequirementsService.roadmap` and `roadmap_items`. Only `APPROVED` or `LOCKED`
requirements may enter those governed projections; Day 17 additionally requires the complete PRD to
be valid and `LOCKED`. Each stable roadmap item preserves its milestone, deterministic sequence,
ordered requirement IDs, and requirement priorities. Every locked requirement must appear exactly
once and no other requirement may appear.

## Draft boundary

The artifact and each rendered item remain `DRAFT`. The schema deliberately contains no effort or
cost estimate, target date, schedule commitment, assignee, agent, repository, branch, implementation
task, deployment, billing, release, or pilot-product field. Roadmap approval and every later planning
or delivery authority require separate founder-approved modules.

## Browser journey and evidence

The customer completes the existing signup-to-locked-PRD journey, opens the roadmap checkpoint,
generates the draft, inspects all requirement mappings, signs out, signs in again, and reopens the
same roadmap. Mandatory Chromium CI uploads `roadmap-draft-generated.png` plus a redacted digest and
claim manifest. The Community workshop planner shown there is browser test data only; no official
ASCOS pilot product has been selected.

## Persistence and security

The adapter writes one `roadmap-v0.1.json` envelope per customer/request with exclusive mode-0600
creation and a full canonical integrity digest. Reads revalidate the complete upstream authority,
regenerate the governed projection, and compare the exact milestone mapping. Exact retries return the
same record; changed content conflicts. Containment, closed directories, bounded identities, symlink
rejection, output escaping, no-store responses, CSP, framing, sniffing, and referrer controls remain
mandatory.

This file adapter is deterministic single-instance evidence. Production exposure requires
transactional uniqueness, encryption and managed keys, backup/restore, retention/deletion,
observability, rate limits, abuse controls, and privacy review.

## Explicitly deferred

Day 17 does not approve the roadmap, estimate or schedule work, assign people or agents, select an
official pilot product, connect a repository, create implementation tasks, generate or execute code,
merge, deploy, bill, or release. Day 18 is not included.
