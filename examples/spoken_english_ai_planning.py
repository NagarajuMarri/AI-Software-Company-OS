"""Offline, isolated planning pilot for Spoken English AI."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.knowledge import KnowledgeStore, ProjectKnowledgeEngine
from runtime.planning import *
from runtime.project_manager import AIProjectManager, ManagerStateStore
from runtime.projects import InMemoryProjectRegistry, register_spoken_english_ai


def main():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = root / "reviewed-fixture"; fixture.mkdir()
        (fixture / "voice_boundaries.py").write_text(
            "class SpeechToTextBoundary:\n    pass\n\n"
            "class TextToSpeechBoundary:\n    pass\n", encoding="utf-8")
        registry = InMemoryProjectRegistry()
        register_spoken_english_ai(registry)
        knowledge_store = KnowledgeStore(root / "state")
        knowledge = ProjectKnowledgeEngine.create(
            "spoken-english-ai", registry, knowledge_store)
        knowledge.scan((("spoken-english-ai-reviewed-fixture", fixture),))
        knowledge.save()
        manager_store = ManagerStateStore(root / "state")
        manager = AIProjectManager.initialize(
            "spoken-english-ai", registry, manager_store)
        manager.save()
        service = ManagedProductPlanningService(
            registry, PlanningStore(root / "state"),
            lambda project_id: ProjectKnowledgeEngine.load(
                project_id, registry, knowledge_store),
            lambda project_id: AIProjectManager.load(
                project_id, registry, manager_store),
            DeterministicPlanningProvider())
        change = ManagedProductChangeRequest(
            "real-voice-ai-provider", "spoken-english-ai",
            "Spoken English AI — Real Voice and AI Provider Integration",
            "Plan provider-neutral real voice and AI tutor boundaries",
            "Reviewed pilot planning request using isolated structural knowledge",
            ("audio-input", "speech-to-text", "ai-tutor", "text-to-speech",
             "pronunciation-assessment", "consent-aware-audio"),
            ("Audio input is supported", "Speech-to-text uses a provider boundary",
             "AI tutor uses a provider boundary",
             "Grammar and Telugu feedback are preserved",
             "Text-to-speech uses a provider boundary",
             "Pronunciation assessment is classified",
             "Audio lifecycle is consent-aware", "Tests are offline and deterministic",
             "No direct provider secrets", "No frontend or payment work"),
            ("No live provider calls", "No product repository writes"),
            ("Frontend work", "Payment work"), ChangePriority.HIGH,
            "product-owner", correlation_id="spoken-english-ai-planning-pilot")
        service.create_request(change)
        context = service.build_context("spoken-english-ai", change.request_id)
        proposal = service.generate_proposal("spoken-english-ai", change.request_id)
        approved = service.approve_proposal(
            "spoken-english-ai", proposal.proposal_id, "human-reviewer",
            "Pilot proposal explicitly reviewed")
        service.materialise_approved_proposal(
            "spoken-english-ai", proposal.proposal_id)
        state = service.manager_loader("spoken-english-ai").current_state()
        print("milestone:", state.milestones[0].milestone_id)
        for task in proposal.tasks:
            print("task:", task.task_id, "depends_on:", task.dependencies,
                  "quality_gates:", task.quality_gates)
        print("approval:", approved.decisions[-1].actor,
              approved.decisions[-1].timestamp.isoformat())
        print("bounded_context_files:", len(context.relevant_files))


if __name__ == "__main__":
    main()
