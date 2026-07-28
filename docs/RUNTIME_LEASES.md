# Runtime Leases

Leases optionally restrict active database writers per runtime. Acquisition
uses a caller-supplied owner ID and returns an opaque identity with UTC expiry
and a monotonic fencing token. Only the token hash is stored.

Renewal and release verify owner, hash, and fencing token. Expired, released,
and superseded leases cannot commit. Breaking removes only an expired record.
Every new acquisition increments persistent fencing, invalidating old owners.
