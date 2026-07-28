class GitProviderError(RuntimeError):
    pass


class InvalidBranchNameError(GitProviderError):
    pass


class ProtectedBranchError(GitProviderError):
    pass


class InvalidRepositoryError(GitProviderError):
    pass
