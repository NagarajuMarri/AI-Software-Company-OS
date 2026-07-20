# Role Architecture Framework

## Purpose

This document defines the reusable people-role architecture for ASCOS. It is intentionally implementation-independent and can be fulfilled by a Human, an AI Digital Twin, or a Human + AI Digital Twin arrangement.

This milestone defines role structure only. It does not define AI agents, prompts, workflows, or runtime operating behavior. It establishes an architectural principle for future milestones: every business role may be fulfilled through alternative execution models, but the role architecture itself remains stable.

## Scope and boundary

This document is the dedicated role architecture source-of-truth for people roles.

It remains separate from:

- [company-design.md](company-design.md), which defines offices, authority, and company-level organization
- [engineering-capability-model.md](engineering-capability-model.md), which defines engineering delivery capabilities and capability assembly

## Design principles

Every reusable role must have:

- Mission
- Responsibilities
- Decision authority
- Inputs
- Outputs
- Deliverables
- Success metrics (KPIs)
- Required competencies
- Required collaboration
- Escalation path
- Explicit exclusions

A role is a reusable architecture pattern. It is not automatically a permanent headcount requirement. The same role may be fulfilled by a Human, an AI Digital Twin, or a Human + AI Digital Twin arrangement depending on the organization’s scale and lifecycle needs.

## Role architecture model

### Role archetype

Each role architecture entry defines:

1. Mission
2. Accountability boundary
3. Decision scope
4. Required collaboration patterns
5. Evidence of success
6. Explicit delegation and non-responsibility boundaries

### Reuse rule

The role framework must remain reusable across:

- small startups
- medium engineering teams
- enterprise organizations

The same role family may stay stable while its staffing intensity changes.

## Role tiers

ASCOS should design roles around scalable role tiers rather than assuming a single fixed enterprise hierarchy.

### Tier 1 — Delivery Roles

These are the core execution roles that exist in almost every engineering organization.

- Associate Engineer
- Engineer
- Senior Engineer

Why this tier exists:
- it provides the reusable execution backbone of engineering delivery
- it supports the majority of implementation work across startups, teams, and enterprise organizations
- it keeps the organization stable even when leadership overhead is minimal

When it becomes necessary:
- whenever there is implementation work to perform
- even in a small startup, this tier is the baseline operating unit

### Tier 2 — Leadership Roles

These roles appear only when coordination becomes necessary.

- Technical Lead
- Engineering Manager

Why this tier exists:
- it adds coordination, sequencing, technical coherence, and delivery accountability where the work has become sufficiently complex or broad
- it provides leadership only when the organization needs it, rather than assuming that every team requires a management layer

When it becomes necessary:
- when a team needs technical direction across more than one workstream
- when delivery commitments require coordination across multiple contributors
- when communication and risk management exceed what the delivery tier alone can absorb

### Tier 3 — Strategic Roles

This tier appears only when multiple engineering teams or engineering organizations exist.

- Engineering Director

Why this tier exists:
- it provides cross-team governance, portfolio alignment, and strategic engineering coordination
- it exists to connect multiple delivery groups to company-level priorities and governance outcomes

When it becomes necessary:
- when there is more than one delivery team or engineering operating unit
- when portfolio trade-offs require centralized engineering decision-making

### Architectural rule

Role tiers should be activated only when the organization’s scale and coordination demand justify them. ASCOS should not assume that every engineering organization needs every layer of leadership simply because that model exists in traditional enterprises.

## Architecture decision evaluation

### Decision statement

ASCOS needs a reusable rule for how engineering roles are composed across different organizational scales without creating unnecessary hierarchy.

### Considered models

#### 1. Flat Engineering Organization

Advantages:
- minimal management overhead
- fast decision-making
- simple reporting structure

Disadvantages:
- weak coordination as team size and complexity increase
- responsibility drift may emerge without explicit technical leadership
- less scalable in larger portfolio environments

Scalability:
- good for small startups and very small teams
- weak for medium and enterprise scale

Suitability for ASCOS:
- suitable for early-stage or small delivery units
- not sufficient as a universal model for larger or multi-team organizations

#### 2. Capability-Based Organization

Advantages:
- strong reuse of deep technical expertise
- clear capability specialization
- well suited to shared platform and cross-project patterns

Disadvantages:
- can create artificial organizational boundaries
- may reduce product-level accountability if capability ownership becomes too detached from delivery
- can over-structure an organization if capabilities are treated as permanent departments too early

Scalability:
- strong for larger organizations with significant reuse and platform needs
- moderate for small and medium teams if over-applied

Suitability for ASCOS:
- good for capability reuse, but insufficient as the complete role architecture because it does not define the business role structure for delivery ownership

#### 3. Traditional Management Hierarchy

Advantages:
- familiar operating model
- clear reporting lines
- strong control for large organizations

Disadvantages:
- assumes fixed management layers even when coordination needs do not justify them
- creates unnecessary hierarchy in small teams
- can slow decision-making and increase overhead

Scalability:
- strong in enterprise environments
- weaker in startup and lean operating contexts

Suitability for ASCOS:
- acceptable as a possible operating pattern in large organizations, but not the preferred default architecture because it is overly rigid for reusable ASCOS design

#### 4. Hybrid Organization

Advantages:
- balances product delivery with shared capability reuse
- supports multiple team sizes and organizational life cycles
- allows tier activation only when needed

Disadvantages:
- requires architectural discipline to prevent drift into duplicated leadership layers
- needs clear accountability boundaries

Scalability:
- strong across startup, medium, and enterprise scale
- best alignment with ASCOS’s need for reusable structure

Suitability for ASCOS:
- best fit because it supports both capability reuse and lean role activation

### Preferred architecture

The preferred architecture for ASCOS is the Hybrid Organization using role tiers.

Rationale:

1. It keeps delivery execution simple at the base layer.
2. It activates leadership only where coordination demand justifies it.
3. It preserves capability reuse without forcing every project into the same permanent org shape.
4. It supports future fulfillment by Human, AI Digital Twin, or Human + AI Digital Twin without changing the role architecture itself.

## Engineering roles

### Required role families

The following roles are required as reusable role families, but not necessarily as permanent full-time positions in every organization.

#### Engineering Director

- Mission: govern engineering execution outcomes for one or more delivery domains and maintain alignment to business, architecture, quality, and security expectations.
- Responsibilities: set engineering direction, approve delivery priorities, coordinate portfolio trade-offs, resolve major execution conflicts, and maintain delivery confidence.
- Decision authority: approves engineering execution priorities within governance constraints; escalates unresolved cross-office conflicts to executive governance.
- Inputs: product roadmaps, architecture policy, delivery risk, capacity, quality evidence, operational signals, and portfolio commitments.
- Outputs: engineering direction, delivery prioritization, escalation outcomes, and execution governance signals.
- Deliverables: engineering plan alignment, delivery risk summaries, resource guidance, and release readiness coordination.
- Success metrics: on-time delivery confidence, less execution drift, lower unresolved escalation rate, better portfolio-level predictability.
- Required competencies: engineering leadership, portfolio judgment, governance alignment, risk triage, cross-functional coordination.
- Required collaboration: Architecture Office, Quality Office, Security Office, DevOps Office, and product leadership.
- Escalation path: unresolved cross-office conflict escalates to Executive Office.
- Explicit exclusions: does not own product strategy, security policy, final quality certification, or detailed implementation design unless delegated.

#### Engineering Manager

- Mission: convert engineering direction into a staffed, coordinated execution model.
- Responsibilities: plan work, assign delivery ownership, maintain team health, coordinate dependencies, monitor execution quality, and support delivery accountability.
- Decision authority: manages team work allocation, delivery sequencing, and day-to-day execution decisions inside approved policy.
- Inputs: product scope, roadmap commitments, team capacity, architecture constraints, and execution risk.
- Outputs: team plans, assignments, delivery status, dependency coordination, and delivery health signals.
- Deliverables: sprint or iteration plans, resourcing coordination, team health evidence, and execution reporting.
- Success metrics: predictable delivery progress, fewer blocked dependencies, stable team execution, lower delivery rework.
- Required competencies: people coordination, delivery planning, dependency management, execution coaching, and cross-functional communication.
- Required collaboration: Technical Lead, Senior Engineers, Product leadership, and peer office interfaces.
- Escalation path: escalates major capability gaps, unresolved blockers, or policy conflicts to the Engineering Director or relevant office.
- Explicit exclusions: does not own architecture approval, quality sign-off, or executive strategy.

#### Technical Lead

- Mission: provide technical coherence for one engineering solution or product area.
- Responsibilities: guide implementation design, maintain technical quality, resolve design-level conflicts within the team, and ensure architectural intent is translated cleanly into delivery work.
- Decision authority: decides engineering implementation approach inside approved architecture boundaries and coordinates technical trade-offs within the workstream.
- Inputs: architecture direction, product requirements, implementation risk, quality constraints, and delivery sequencing.
- Outputs: technical direction, design trade-off decisions, implementation quality guidance, and workstream-level integration coherence.
- Deliverables: solution-level technical plan, design rationale, code health guidance, and implementation quality review signals.
- Success metrics: lower technical drift, fewer design rework cycles, stronger delivery consistency, better integration hygiene.
- Required competencies: system design thinking, technical judgment, implementation quality, ownership of technical trade-offs, and coaching.
- Required collaboration: Engineering Manager, Senior Engineers, Architecture Office, and relevant shared capability owners.
- Escalation path: escalates architecture-level disputes to the Architecture Office and unresolved delivery conflict to Engineering Manager or Engineering Director.
- Explicit exclusions: does not own company-wide product strategy, release approval, or security policy.

#### Senior Engineer

- Mission: provide deep technical execution and judgment for complex implementation responsibilities.
- Responsibilities: design and implement high-quality solutions, mentor less experienced engineers, guide technical quality, and support design decisions across shared capabilities.
- Decision authority: approves implementation choices within approved architecture constraints and can act as a technical owner for one or more engineering areas.
- Inputs: product guidance, team delivery commitments, architecture constraints, quality expectations, and integration needs.
- Outputs: solution implementation, design guidance, technical review evidence, and reusable engineering patterns.
- Deliverables: production-ready implementation, code review quality, technical documentation evidence, and reusable design patterns when appropriate.
- Success metrics: fewer defects, better implementation quality, stronger mentoring outcomes, reduced rework.
- Required competencies: advanced engineering execution, system thinking, debugging, mentoring, and technical communication.
- Required collaboration: Technical Lead, Engineering Manager, peer engineers, and Architecture Office on major design questions.
- Escalation path: escalates major architecture, security, or release-readiness concerns to the relevant authority function.
- Explicit exclusions: does not own organization-level policy or final external release approval.

#### Engineer

- Mission: deliver implementation work in one or more engineering capability areas with strong execution discipline.
- Responsibilities: implement features, maintain code quality, contribute to technical understanding, and participate in reviews and delivery commitments.
- Decision authority: makes implementation-level decisions within assigned scope and approved standards.
- Inputs: product and technical requirements, architecture direction, team plans, review feedback, and quality expectations.
- Outputs: implemented work, test evidence, defect corrections, and review-ready contributions.
- Deliverables: working code, validated changes, and clear implementation artifacts.
- Success metrics: delivery throughput, defect escape reduction, stable feature completion, and reliable review outcomes.
- Required competencies: core engineering competence, review discipline, debugging, testing awareness, and communication.
- Required collaboration: Senior Engineer, Technical Lead, and engineering team peers.
- Escalation path: escalates unresolved design or risk concerns to the Technical Lead or Engineering Manager.
- Explicit exclusions: does not own cross-team architecture decisions or quality certification.

#### Associate Engineer

- Mission: grow into a reliable execution contributor through guided implementation, review, and mentorship.
- Responsibilities: complete well-scoped implementation tasks, follow standards, learn delivery practices, and participate in routine engineering collaboration.
- Decision authority: limited to approved small-scope tasks and implementation under supervision.
- Inputs: backlog items, mentor direction, coding standards, and review feedback.
- Outputs: assigned work product, test evidence, learning outcomes, and review-ready changes.
- Deliverables: completed tasks, documented learning progress, and steadily improving engineering consistency.
- Success metrics: successful completion of junior-level work, increasing ownership quality, reduced review friction, and readiness for broader responsibility.
- Required competencies: fundamentals, disciplined execution, attention to standards, and growth readiness.
- Required collaboration: assigned mentor, team peers, and relevant technical lead.
- Escalation path: escalates blockers or uncertain design choices to Senior Engineer or Technical Lead.
- Explicit exclusions: does not own independent product decisions, major design authority, or release sign-off.

### Are all roles required?

No.

These are reusable role families, not mandatory permanent roles for every organization.

The minimal viable structure depends on scale:

- Small startup: Engineering Director or implementation lead, Senior Engineer, Engineer, and Associate Engineer when needed
- Medium team: Engineering Manager plus Technical Lead, Senior Engineer, Engineer, and Associate Engineer
- Enterprise: full role layering with explicit governance and team-scale specialization

The architecture therefore supports role presence by need, rather than forcing a full hierarchy everywhere.

## Separate roles from capability assignments

The role framework must separate business role from capability assignment.

### Role

A role is the reusable business accountability pattern.

Example:

Person
↓
Role
Senior Engineer
↓
Assignment
AI Engineering Capability

Later, the same person remains the same role while the assignment changes.

Example:

Person
↓
Role
Senior Engineer
↓
Assignment
Backend Engineering Capability

### Why this is more reusable

This separation is more reusable because it allows the same business role to be fulfilled by different execution models while preserving stable accountability.

It supports:

- Human
- AI Digital Twin
- Human + AI Digital Twin

The same role can remain stable even if the performance mode changes. This prevents role architecture from becoming tied to one implementation method, one platform, or one type of delivery model.

### Capability assignments

Specialist roles should not be treated as a new permanent hierarchy by default. They are best modeled as capability-specific assignments or project assignments under the existing engineering capability model.

### Recommended classification

#### AI Engineer

- Classification: capability-specific assignment under the permanent AI Engineering core capability
- Rationale: AI capability is durable, but AI specialism is not the same as a separate company-wide department in every project.
- Use model: project-activated specialist sub-practices are added when a product requires them.

#### Frontend Engineer

- Classification: capability-specific assignment under Frontend Engineering
- Rationale: this is a durable capability family, but it does not require a separate permanent leadership layer in every project.

#### Backend Engineer

- Classification: capability-specific assignment under Backend Engineering
- Rationale: this is a core reusable capability and should stay visible as a capability family rather than as an always-separate reporting line.

#### Data Engineer

- Classification: capability-specific assignment under Data and Database Engineering
- Rationale: data engineering is a necessary specialization within a capability area and should be activated when the delivery model needs it.

#### Platform Engineer

- Classification: permanent capability anchor for shared platform enablement, but not necessarily a standalone permanent people role in every team
- Rationale: platform concerns are reusable and cross-project, so the role family should be visible and durable, but its staffing must scale with portfolio demand.

#### Integration Engineer

- Classification: project assignment or capability-specific assignment under Platform and Integration Engineering
- Rationale: integration complexity varies by product; therefore it should not be treated as a universal permanent role in every team.

### Summary rule

The specialist role family is reusable, but the staffing model should remain:

- permanent role: only for durable shared capability anchors, such as AI Engineering as a core capability
- capability-specific assignment: used when a role family must exist inside a delivery team for a defined capability area
- project assignment: used when expertise is needed for a single initiative and is not a permanent organizational feature

## Updated role-tier model

The role framework should be expressed as tiers rather than a fixed hierarchy.

### Tier 1 — Delivery Roles

- Associate Engineer
- Engineer
- Senior Engineer

These roles exist in almost every engineering organization and form the implementation backbone.

### Tier 2 — Leadership Roles

- Technical Lead
- Engineering Manager

These roles appear only when coordination becomes necessary for the engineering organization or a delivery team.

### Tier 3 — Strategic Roles

- Engineering Director

This role exists only when multiple engineering teams or engineering organizations require strategic coordination.

### Activation rule

ASCOS should activate a higher tier only when organizational scale and coordination demand make that tier necessary.

This design keeps the role framework lean and prevents unnecessary hierarchy.

## Updated capability assignment model

The role architecture distinguishes between:

- business role: the reusable accountability pattern
- capability assignment: the technical responsibility that the role is currently carrying

Example:

- Role: Senior Engineer
- Assignment: AI Engineering Capability

Later:

- Role: Senior Engineer
- Assignment: Backend Engineering Capability

This architecture is more reusable because it allows one business role to be reused across different capability contexts while remaining implementation-independent.

## Role lifecycle

### Role creation

A role is created when a reusable demand is persistent enough to justify an enduring architecture pattern, or when a project requires a temporary delivery-specific assignment.

### Role retirement

A role is retired when the capability need ceases to exist, or when the same work can be absorbed into an existing capability without unnecessary hierarchy.

### Temporary assignments

Temporary assignments are used for:

- a focused product initiative
- integration-intensive work
- temporary AI specialist work
- urgent portfolio support

Temporary assignments should not become permanent structure unless the need repeats and justifies the architecture change.

### Acting responsibilities

Acting responsibilities may be assigned when a role is vacant or when delivery demand requires a temporary leadership handoff. Acting assignments should remain time-bound and should always preserve the preexisting accountability path.

## Source-of-truth decision

### Option A: place role architecture inside engineering-capability-model.md

Pros:

- keeps all engineering architecture in one place
- reduces file count

Cons:

- mixes capability design with people-role design
- obscures the difference between capability assembly and role structure
- makes the engineering capability document harder to maintain for governance reviewers

### Option B: create one dedicated role-architecture document

Pros:

- preserves [company-design.md](company-design.md) as the organization source-of-truth
- preserves [engineering-capability-model.md](engineering-capability-model.md) as the capability source-of-truth
- keeps people-role structure separate, readable, and scalable
- supports future reuse across human, AI, and hybrid fulfillment models

Cons:

- adds one additional document to the docs layer

### Preferred option

Option B is preferred.

Reason:

- [company-design.md](company-design.md) already owns office-level company organization.
- [engineering-capability-model.md](engineering-capability-model.md) already owns engineering capability assembly.
- This document should own the reusable people-role architecture that links those two foundations without duplicating either.

## Validation

This milestone has been scoped to role architecture only.

Validation checks:

- no duplication with [company-design.md](company-design.md)
- no duplication with [engineering-capability-model.md](engineering-capability-model.md)
- no AI agents defined
- no prompts defined
- no workflows defined

This document remains a pure role architecture artifact.
