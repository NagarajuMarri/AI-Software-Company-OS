# Spoken English AI Managed Pilot

The first commercial pilot is **Personalised Daily Speaking Practice Session**.
`runtime.pilots.spoken_english.managed_change_request()` must run through Project
Registry, 12.3A planning/materialisation, separate 12.3B execution approval,
isolated workspace/branch, 12.4 provider operation, gates, evidence, and separate
completion review.

The backend change generates and persists a learner-owned daily plan with
warm-up, situation, vocabulary, grammar, pronunciation, response instructions,
completion criteria, and duration. Inputs cover proficiency, goal, mistakes,
streak, lessons, explanation language, and available duration. Learner/date
uniqueness and an authenticated endpoint are required. Generation stays behind
an interface. Voice, STT/TTS, payments, frontend/mobile, deployment, and secrets
are excluded.

## Operator sequence

1. Validate the registered project and refresh bounded Project Knowledge.
2. Create this managed change request.
3. Generate, inspect, approve, and materialise the 12.3A proposal.
4. Generate and separately approve the 12.3B execution plan.
5. Prepare its isolated workspace and controlled branch.
6. Build and inspect the provider context digest.
7. Run the deterministic provider; poll, validate/apply patches, inspect Git,
   run gates, and generate evidence.
8. Obtain separate human evidence approval.
9. Stop. Commit, push, and product PR require later explicit product-write
   authorization.

Live readiness may be validated without a call. Chargeable use additionally
requires enabled configuration, approved model, ASCOS-process credential,
`--allow-live-provider`, and explicit confirmation. Default tests use temporary
fixtures and never open the real product checkout.
