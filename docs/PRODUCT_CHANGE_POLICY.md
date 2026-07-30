# Product Change Policy

`ChangePolicy` is a conservative boundary supporting allowed/forbidden prefixes,
file and line limits, forbidden types, protected configuration, secret
indicators, and switches for dependency files, migrations, CI workflows,
generated files, and binaries.

Defaults reject secret/environment files, keys, workflows, security-sensitive
areas, deployment/infrastructure, payment modules, production migrations, and
protected configuration. Absolute paths, traversal, NUL bytes, unapproved
prefixes, merge/deploy requests, and limit overruns are rejected. Exceptions
must appear explicitly in review evidence; none are silently granted.
