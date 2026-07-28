from dataclasses import dataclass


@dataclass(frozen=True)
class GitStatus:
    branch: str
    clean: bool
    changed_paths: tuple[str, ...]


@dataclass(frozen=True)
class GitCommit:
    sha: str
    branch: str
