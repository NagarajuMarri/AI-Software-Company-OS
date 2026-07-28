# Git Integration

`LocalGitProvider` invokes Git only through the safe command runner. It
validates repository roots, branches, commit messages, selected paths, and
repository URLs. Writes and pushes to `main` and `master` are denied by
default; force push is not exposed.

Remote credentials belong to an injected, deployment-local credential
strategy. Values must never enter arguments, output, events, exceptions, or
checkpoints. Network Git is not required by the test suite.
