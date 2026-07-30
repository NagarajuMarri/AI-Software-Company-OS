"""Fully offline controlled managed-product execution pilot."""

from datetime import datetime, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.integrations.git.models import GitCommit, GitStatus
from runtime.integrations.github import InMemoryGitHubProvider
from runtime.integrations.github.models import GitHubRepository
from runtime.knowledge import KnowledgeStore, ProjectKnowledgeEngine
from runtime.managed_execution import (
    ChangePolicy,
    ExecutionMode,
    ManagedExecutionStore,
    ManagedProductExecutionRequest,
    ManagedProductExecutionService,
    QualityGate,
    QualityGateProfile,
    ValidatedCodingResult,
)
from runtime.planning import (
    ChangePriority,
    DeterministicPlanningProvider,
    ManagedProductChangeRequest,
    ManagedProductPlanningService,
    PlanningStore,
)
from runtime.project_manager import AIProjectManager, ManagerStateStore
from runtime.projects import InMemoryProjectRegistry, ManagedProject
from runtime.tools import CommandResult, LocalWorkspaceProvider


class OfflineCommandRunner:
    def execute(self, request, *, cancellation=None):
        now = datetime.now(timezone.utc)
        return CommandResult(
            request.executable, request.arguments, 0, "offline gate passed", "",
            now, now, 0.0, False)


class OfflineGit:
    def __init__(self, github, repository):
        self.github = github
        self.repository = repository
        self.branch = "main"
        self.reviewed_changes = False
        self.commit_sha = "offline-base"
        self.parent_sha = None
        self.message = ""
        self.pushed_sha = None

    def status(self, repository_path):
        changed = ("backend/voice.py",) if self.reviewed_changes else ()
        return GitStatus(self.branch, not changed, changed)

    def create_branch(self, repository_path, branch):
        self.branch = branch
        self.reviewed_changes = True

    def current_branch(self, repository_path):
        return self.branch

    def current_commit(self, repository_path):
        return self.commit_sha

    def branch_commit(self, repository_path, branch):
        return self.commit_sha if branch == self.branch else None

    def add(self, repository_path, paths):
        assert tuple(paths) == ("backend/voice.py",)

    def commit(self, repository_path, message):
        self.parent_sha = self.commit_sha
        self.message = message
        self.commit_sha = "offline-reviewed-commit"
        self.reviewed_changes = False
        return GitCommit(self.commit_sha, self.branch)

    def commit_parent(self, repository_path, commit_sha):
        return self.parent_sha

    def commit_message(self, repository_path, commit_sha):
        return self.message

    def commit_changed_paths(self, repository_path, commit_sha):
        return ("backend/voice.py",)

    def push(self, repository_path, remote, branch):
        self.pushed_sha = self.commit_sha
        try:
            self.github.get_branch(self.repository, branch)
        except Exception:
            self.github.create_branch(self.repository, branch, self.commit_sha)

    def remote_branch_commit(self, repository_path, remote, branch):
        return self.pushed_sha


def main():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        product = root / "spoken-english-ai-fixture"
        (product / "backend").mkdir(parents=True)
        (product / "backend" / "voice.py").write_text(
            "class SpeechToTextBoundary: pass\n"
            "class AITutorBoundary: pass\n"
            "class TextToSpeechBoundary: pass\n"
            "class PronunciationAssessment: pass\n"
            "class ConsentAwareAudio: pass\n",
            encoding="utf-8",
        )
        project = ManagedProject(
            "spoken-english-ai", "Spoken English AI", "Isolated fixture",
            "https://github.com/NagarajuMarri/spoken-english-ai", "main",
            local_path=str(product))
        registry = InMemoryProjectRegistry((project,))
        state = root / "state"
        knowledge_store = KnowledgeStore(state)
        knowledge = ProjectKnowledgeEngine.create(
            project.project_id, registry, knowledge_store)
        knowledge.scan()
        knowledge.save()
        manager_store = ManagerStateStore(state)
        AIProjectManager.initialize(project.project_id, registry, manager_store).save()
        planning_store = PlanningStore(state)
        planning = ManagedProductPlanningService(
            registry, planning_store,
            lambda project_id: ProjectKnowledgeEngine.load(
                project_id, registry, knowledge_store),
            lambda project_id: AIProjectManager.load(
                project_id, registry, manager_store),
            DeterministicPlanningProvider())
        change = ManagedProductChangeRequest(
            "voice-foundation", project.project_id,
            "Real Voice and AI Provider Integration Foundation",
            "Add provider-neutral offline voice boundaries",
            "Explicitly isolated pilot",
            ("speech-to-text", "ai-tutor", "text-to-speech",
             "pronunciation-assessment", "consent-aware-audio"),
            ("Provider boundaries are deterministic and offline",),
            ("No live providers", "No secrets"),
            ("Frontend", "Payments", "Deployment"),
            ChangePriority.HIGH, "product-owner",
            datetime(2026, 1, 1, tzinfo=timezone.utc))
        planning.create_request(change)
        proposal = planning.generate_proposal(
            project.project_id, change.request_id,
            now=datetime(2026, 1, 2, tzinfo=timezone.utc))
        planning.approve_proposal(
            project.project_id, proposal.proposal_id, "planning-reviewer")
        proposal = planning.materialise_approved_proposal(
            project.project_id, proposal.proposal_id)

        github = InMemoryGitHubProvider()
        github.register_repository(GitHubRepository(project.repository_url, "main"))
        github.create_branch(project.repository_url, "main", "offline-base")
        offline_git = OfflineGit(github, project.repository_url)
        execution = ManagedProductExecutionService(
            registry, planning_store, ManagedExecutionStore(state),
            lambda project_id: AIProjectManager.load(
                project_id, registry, manager_store),
            workspace_provider=LocalWorkspaceProvider(root / "workspaces"),
            git_provider_factory=lambda _: offline_git,
            github_provider=github,
            command_runner=OfflineCommandRunner(),
            change_policies=(ChangePolicy(
                "voice-policy", ("backend/",), (".github/", ".env", "payment/")),),
            quality_gate_profiles=(QualityGateProfile(
                "voice-gates", project.project_id,
                (
                    QualityGate("compile", ("python", "-m", "compileall", "-q", "."), 30),
                    QualityGate("pytest", ("python", "-m", "pytest", "-q"), 60),
                    QualityGate("provider-boundaries",
                                ("python", "-m", "pytest", "-q", "tests/voice"), 30),
                    QualityGate("diff-validation", ("git", "diff", "--check"), 30),
                ),
                ("python", "git"),
            ),),
        )
        first_task = proposal.tasks[0]
        request = ManagedProductExecutionRequest(
            "voice-execution", project.project_id, proposal.proposal_id,
            proposal.milestone_id, (first_task.task_id,), "execution-operator",
            datetime(2026, 1, 3, tzinfo=timezone.utc), "voice-correlation",
            "main", "ascos/voice-foundation", ExecutionMode.CONTROLLED_WRITE,
            "voice-gates", "python", "isolated", "human-review",
            5, 200, 60)
        execution.create_execution_request(request)
        plan = execution.generate_execution_plan(
            project.project_id, request.execution_request_id)
        execution.approve_execution_plan(
            project.project_id, plan.execution_plan_id, "execution-reviewer")
        execution.create_runtime_work(project.project_id, plan.execution_plan_id)
        execution.prepare_workspace(
            project.project_id, plan.execution_plan_id, allow_product_write=True)
        execution.create_feature_branch(
            project.project_id, plan.execution_plan_id, allow_product_write=True)
        coding_request = execution.submit_coding_task(
            project.project_id, plan.execution_plan_id, first_task.task_id)
        result = ValidatedCodingResult(
            coding_request.external_task_id, coding_request.workspace_id,
            "SUCCEEDED", ("backend/voice.py",), 5, 0, (),
            coding_request.expected_artifacts, "Offline bounded change",
            "deterministic:voice:1", (1, 2))
        execution.process_coding_result(
            project.project_id, plan.execution_plan_id,
            coding_request, result, "voice-policy")
        execution.run_quality_gates(
            project.project_id, plan.execution_plan_id, "voice-gates")
        evidence = execution.generate_review_evidence(
            project.project_id, plan.execution_plan_id,
            (f"{plan.execution_plan_id}-{first_task.task_id}-accepted-1",),
            base_commit="offline-base")
        execution.approve_review(
            project.project_id, plan.execution_plan_id, "human-reviewer")
        execution.create_commit(
            project.project_id, plan.execution_plan_id, allow_product_write=True)
        execution.push_branch(
            project.project_id, plan.execution_plan_id, allow_product_write=True)
        pull_request = execution.create_draft_pull_request(
            project.project_id, plan.execution_plan_id, allow_product_write=True)
        print(f"plan={plan.execution_plan_id}")
        print(f"evidence={evidence.integrity_digest}")
        print(f"draft_pr={pull_request.number} draft={pull_request.draft}")
        print("real_repository_modified=false live_provider=false merge=false deployment=false")


if __name__ == "__main__":
    main()
