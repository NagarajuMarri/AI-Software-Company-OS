# Managed Product Voice and Media Verification

Day 9 adds the bounded Voice capability verifier on top of the exact-SHA environment and Chromium
journey runner. It covers all eight locked SpeakMate V1 Voice journeys: consent-bound capture,
speech-to-text, conversation persistence, governed response generation, text-to-speech media,
audible browser playback, avatar synchronization, and a second turn in the same session.

## Exact authority and media integrity

A write-once `VoiceVerificationPlan` binds the acceptance run, product, browser-plan digest,
runtime-configuration revision and digest, full commit SHA, acceptance-profile digest, provider,
ordered journeys, named browser assertions, exact claims, deterministic input/output fixtures,
canonical media paths, response bound, creator, and time. File storage verifies its canonical digest,
identity, path containment, and restart readback and rejects mutation or corruption.

Input and output fixtures are content-addressed WAV artifacts. The verifier reads them through their
expected digests, fetches the exact bytes delivered by the running product from the authorized origin
without proxies or redirects, and requires byte equality. It parses the WAV container itself and
checks uncompressed 16-bit PCM format, sample rate, channels, duration, peak amplitude, RMS amplitude,
and a minimum non-silent sample ratio.

## Browser and end-user evidence

Chromium performs every journey while the exact environment is ready. Playback claims require a
provider-owned media assertion, not application text alone: the media element must finish, advance
through its expected duration, be unmuted, retain an audible volume, and have decoded data. Avatar
evidence requires an observed `speaking → idle` lifecycle, and the repeat journey requires a second
persisted turn plus another completed playback.

Mandatory CI runs the chain against a migrated SQLite-backed product fixture. Deterministic local
STT, response, and TTS adapters keep the test credential-free and reproducible. The founder artifact
contains eight final screenshots, the verified learner-input and tutor-output WAV files, and a
secret-safe evidence/digest manifest.

## Deliberate boundary

Day 9 proves the provider contracts, exact media delivery, non-silent signal, browser playback path,
avatar lifecycle, and repeat-turn orchestration. Headless CI cannot prove a human heard a physical
speaker, and the deterministic fixture is not a production microphone, STT/LLM/TTS provider, or
deployed product. Production-provider and human UX acceptance remain explicit later gates. Day 10
adds PWA verification and safe complete-capability submission. No merge, deployment, or release is
performed here.
