# Managed Project Registry

Milestone 12.0 introduces the ASCOS boundary for product identity and routing.
`ManagedProject` records stable identity, descriptive metadata, repository
location, default branch, lifecycle, optional local routing, and tags. It does
not own product source code, credentials, deployment configuration, or product
runtime state.

Day 5 deliberately keeps execution declarations outside this identity record. A
`ManagedProductRuntimeConfiguration` references a registered project and snapshots the repository
URL, expected branch, and exact commit alongside commands, endpoints, environment policy, opaque
secret references, and an acceptance-profile digest. Registry metadata can evolve without rewriting
an already-authorized runtime configuration or acceptance run. A future provider must independently
verify the registered repository and observed exact SHA before execution.

`ProjectRegistry` is the provider-neutral contract. The in-memory implementation
is composed once per runtime and publishes a registration event through the
shared event boundary. Registration rejects duplicate project IDs and normalized
repository URLs; lookup, listing, and lifecycle filtering are deterministic.

`FileProjectRegistry` persists the same model in schema-versioned JSON. Writes
use a temporary file, flush and synchronize it, then atomically replace the
registry. A failed save rolls back the in-memory registration, while invalid or
unsupported persisted data is rejected rather than partially loaded.

The approved catalog registers Spoken English AI using its canonical GitHub URL
and deliberately omits a local path. The examples therefore neither read nor
modify the product checkout. The Day 5 runtime-configuration example uses a generic deterministic
demo product and does not invent product-specific startup commands. Exact-SHA environment lifecycle,
browser execution, discovery adapters, and operator APIs remain future work.
