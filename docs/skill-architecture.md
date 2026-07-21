# Skill Architecture

## 1. Purpose

This document defines the authoritative architecture for reusable skills in ASCOS.

Skill Architecture defines the reusable competence units required to fulfil Business Role responsibilities through humans, Digital Twins, or combined fulfilment arrangements. It provides the stable architectural model through which ASCOS can determine what reusable skills are required for a product, assign those skills to appropriate Business Roles and Digital Twins, identify skill gaps, and prepare for later Tool and Execution Architectures.

This document is the authoritative architecture for skills. It does not define:

- Business Roles
- Digital Twins
- tools
- workflows
- runtime execution
- training programs
- courses
- certifications
- prompts
- AI models
- vendor technologies

## 2. Core Principles

The Skill Architecture is founded on the following principles:

- Reusable skills: skills are reusable architectural assets that support multiple responsibilities and products.
- Explicit skill identity: each skill has a clear architectural identity and scope.
- Composability: multiple skills may be composed into a skill set or skill profile for a responsibility or product need.
- Role independence: skills are not equivalent to Business Roles and do not define responsibility ownership.
- Fulfilment independence: skills may support humans, Digital Twins, or combined fulfilment arrangements without changing the skill architecture.
- Traceability: skill definitions, assignments, and changes must remain understandable over time.
- Governed assignment: skills are assigned through approved governance and architectural boundaries.
- Minimum necessary skill allocation: skills should be allocated only as needed to fulfil the responsibility.
- Replaceability: the mechanisms used to apply skills may evolve without changing the skill architecture.
- Project-driven selection: product and responsibility needs determine which skills are required.
- Technology neutrality: the architecture remains valid across changing implementation contexts.
- Implementation independence: the architecture does not prescribe delivery mechanisms.

Skills remain architecturally stable even when the mechanisms used to perform them change.

## 3. Skill Definition

A Skill is a reusable, bounded unit of competence that enables a responsibility or part of a responsibility to be fulfilled to an expected level.

A Skill:

- describes an ability
- has a defined purpose and boundary
- may be required by multiple Business Roles
- may be applied by humans or Digital Twins
- may be reused across multiple products
- does not itself perform work
- does not own accountability
- does not grant authority

## 4. Architectural Distinctions

The following architectural distinctions are preserved:

- Capability: a durable organizational ability owned by an Office or enterprise structure.
- Business Role: an accountable organizational responsibility pattern.
- Digital Twin: a fulfilment representation aligned to one Business Role.
- Skill: a reusable unit of competence required to fulfil part of a responsibility.
- Knowledge: information and understanding used when applying a skill.
- Tool: an approved operational resource used while applying a skill.
- Execution: the application and coordination of skills to fulfil assigned work.
- Evidence: the traceable record demonstrating what occurred and what outcome was achieved.

These distinctions establish clean architectural boundaries without defining the future architectures in detail.

## 5. Skill Classification

Skill Architecture uses a stable, non-vendor-specific classification model to improve discovery and composition.

Example categories include:

- Domain skills
- Product skills
- Architecture skills
- Engineering skills
- Data skills
- AI engineering skills
- Quality skills
- Security skills
- Platform and operations skills
- Governance and decision skills
- Documentation and knowledge skills
- Collaboration and coordination skills

These classifications improve discovery and composition but do not create permanent departments or Business Roles.

They do not name programming languages, frameworks, cloud vendors, model providers, or commercial products.

## 6. Skill Specification Model

Every reusable skill should be described through the following architectural attributes:

- Skill identity
- Name
- Purpose
- Scope
- Expected outcomes
- Required inputs
- Produced outputs
- Preconditions
- Applicable constraints
- Related capabilities
- Applicable Business Roles
- Permitted fulfilment arrangements
- Proficiency expectations
- Evidence expectations
- Dependencies
- Explicit exclusions
- Lifecycle state

These are architectural metadata only. They do not define schemas, databases, APIs, file formats, or implementation structures.

## 7. Skill Relationships

The architectural relationships between skills, roles, and fulfilment models are as follows:

- One Business Role may require zero, one, or many Skills.
- One Skill may support zero, one, or many Business Roles.
- One Digital Twin may be assigned only Skills approved for its corresponding Business Role and delegated responsibility.
- Skills remain reusable enterprise assets and are referenced by Business Roles and Digital Twins rather than owned by them.
- A Skill may relate to one or more enterprise Capabilities.
- A Skill does not own a Capability, Business Role, Digital Twin, decision, tool, or execution.
- Skill assignment does not transfer accountability or decision authority.

Business Roles own responsibilities while skills enable fulfilment.

## 8. Skill Composition

Multiple Skills may be composed into a Skill Set or Skill Profile for a particular responsibility or product need.

Key architectural rules for composition:

- Skill composition is project- and responsibility-driven.
- A Skill Set is not a Business Role.
- A Skill Profile describes required competence, not a permanent person or Digital Twin.
- Composition must avoid unnecessary duplication.
- Shared skills should be reused rather than redefined.
- Dependencies and incompatibilities must remain explicit.
- Composition does not define execution sequencing.

Composition does not introduce workflows.

## 9. Skill Proficiency

Proficiency expresses the expected depth and autonomy of competence.

A concise implementation-independent proficiency model may use the following levels:

- Foundational
- Working
- Advanced
- Authoritative

Each level is defined by the expected degree of competence and independence appropriate to the delegated responsibility.

Proficiency:

- expresses the expected depth and autonomy of competence
- does not grant governance authority
- does not replace Role Architecture
- must be appropriate to the delegated responsibility
- is evaluated through future implementation and Evidence Architecture mechanisms

## 10. Skill Lifecycle

Skills progress through a conceptual lifecycle:

- Proposed
- Defined
- Approved
- Available
- Assigned
- Observed
- Revised
- Deprecated
- Retired

This is not a runtime workflow.

Deprecated or retired skills must remain traceable where previous decisions, products, or evidence depend on them.

## 11. Skill Governance

Skill governance establishes the architectural responsibilities for maintaining skill integrity and reuse.

Governance responsibilities include:

- approving reusable skills
- maintaining boundaries
- preventing duplicate skills
- verifying relationship to capabilities and roles
- approving proficiency expectations
- reviewing skill relevance
- deprecating and retiring skills
- preserving traceability
- controlling skill assignment to Digital Twins

Architectural responsibilities remain clear:

- Business Roles retain accountability.
- Decision Architecture governs relevant decisions.
- Skill Architecture governs skill definitions and relationships.
- Digital Twins may use only approved and assigned skills.
- Skill governance does not define runtime enforcement mechanisms.

## 12. Contribution to ASCOS Product Generation

Skill Architecture directly supports the ASCOS objective of enabling product generation through architecture rather than implementation.

The conceptual chain is:

Product Intent
    ↓
Required Product Outcomes
    ↓
Required Enterprise Capabilities
    ↓
Required Business Roles
    ↓
Required Skill Profiles
    ↓
Approved Digital Twin Skill Assignments
    ↓
Future Tool Selection and Execution Planning

When ASCOS receives a request such as:

“Create a Spoken English App”

Skill Architecture allows the operating system to determine the kinds of reusable competence required without prematurely selecting tools, technologies, workflows, or implementations.

Examples may remain at the level of abstract competence areas such as:

- language-learning domain understanding
- product requirements analysis
- conversational experience design
- speech-system architecture
- backend system design
- quality validation
- security assessment
- deployment readiness

This section explains architectural contribution, not runtime behaviour.

## 13. Architectural Boundaries

Skill Architecture owns:

- skill definitions
- skill classifications
- skill metadata
- skill relationships
- skill composition principles
- proficiency concepts
- skill lifecycle
- skill governance

Skill Architecture does not own:

- organizational capabilities
- Business Role accountability
- Digital Twin identity
- decision authority
- tools
- workflows
- execution sequencing
- runtime orchestration
- evidence storage
- knowledge storage
- training delivery
- certification systems
- implementation technology

## 14. Relationship to Other Architectures

Skill Architecture relates to other architecture domains as follows:

- Engineering Capability Model: Capabilities express durable organizational abilities; Skills express reusable units of competence contributing to those abilities.
- Role Architecture: Business Roles require skills but retain responsibility, authority, and accountability.
- Digital Twin Architecture: Digital Twins receive approved skill assignments only within the scope of their corresponding Business Role and delegated responsibility.
- Decision Architecture: Decisions concerning skill creation, approval, assignment, revision, deprecation, and retirement are governed by Decision Architecture.
- Future Tool Architecture: Tools support the application of skills but are not skills.
- Future Execution Architecture: Execution coordinates the application of skills but is not defined here.
- Future Evidence Architecture: Evidence demonstrates skill application and outcomes but is not defined here.
- Future Knowledge Architecture: Knowledge supports skill application but is not itself a skill.

## 15. Extension Principles

This architecture remains valid when:

- products change
- organizational structures change
- Business Roles evolve
- Digital Twins are replaced
- tools change
- technologies change
- implementation mechanisms change
- new domains are introduced
- proficiency evaluation methods change

Skills may evolve while architectural ownership boundaries remain stable.

## 16. Design Principles Summary

The following concise principles summarize the architecture for future reference:

- One skill has one explicit architectural identity.
- Skills are reusable competence units.
- Skills enable responsibilities but do not own accountability.
- Business Roles define responsibility; Skills enable fulfilment.
- Digital Twins use only approved and assigned skills.
- Skill assignment does not grant decision authority.
- Skills may be composed without defining workflows.
- Product needs determine skill selection.
- Skill Architecture remains independent of tools and technologies.
- Skill Architecture directly supports ASCOS product-generation assembly.
