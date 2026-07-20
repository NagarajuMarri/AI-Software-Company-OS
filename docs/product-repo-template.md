# Product Repository Template

## Purpose

This is the default template for future product repositories within ASCOS.

## Required top-level structure

```text
README.md
docs/
  architecture.md
  runbook.md
  release-notes.md
src/
  application/
tests/
  unit/
  integration/
```

## Required governance

Every product repository must include:

- architecture documentation
- security review evidence
- quality validation evidence
- release readiness evidence
- a decision record model using ADRs

## Design note

The actual implementation language and framework may vary by product domain, but the governance structure must remain consistent.
