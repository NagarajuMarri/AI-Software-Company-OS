"""Exercise the GitHub contract without network access or merging."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.integrations.github import (
    CIStatus, CreatePullRequestRequest, GitHubRepository,
    InMemoryGitHubProvider,
)


def main():
    provider = InMemoryGitHubProvider()
    provider.register_repository(GitHubRepository("example/project"))
    provider.create_branch("example/project", "main", "a" * 40)
    provider.create_branch("example/project", "agent/change", "b" * 40)
    pull_request = provider.create_draft_pull_request(
        CreatePullRequestRequest(
            "example/project", "Safe change", "Initial description",
            "main", "agent/change",
        )
    )
    provider.update_pull_request(
        "example/project", pull_request.number, body="Verified description"
    )
    provider.set_ci_status(
        "example/project", pull_request.number, CIStatus.SUCCESS
    )
    pull_request = provider.mark_ready_for_review(
        "example/project", pull_request.number
    )
    provider.add_comment(
        "example/project", pull_request.number,
        "Explicitly approved for review; merge intentionally not requested.",
    )
    print(
        f"pr={pull_request.number} state={pull_request.state.value} "
        f"draft={pull_request.draft} merged=false"
    )


if __name__ == "__main__":
    main()
