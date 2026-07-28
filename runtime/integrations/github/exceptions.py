class GitHubProviderError(RuntimeError): pass
class RepositoryNotFoundError(GitHubProviderError): pass
class BranchNotFoundError(GitHubProviderError): pass
class PullRequestConflictError(GitHubProviderError): pass
class PullRequestNotMergeableError(GitHubProviderError): pass
class GitHubAuthenticationError(GitHubProviderError): pass
class GitHubRateLimitError(GitHubProviderError): pass
class ExternalProviderUnavailableError(GitHubProviderError): pass
