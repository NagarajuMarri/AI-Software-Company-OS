# Provider Health

Health is tracked independently by provider and capability as `UNKNOWN`, `HEALTHY`,
`DEGRADED`, `OPEN`, `HALF_OPEN`, or `DISABLED`. State contains bounded failure codes,
counters, capacity, circuit expiry, and version—never responses or credentials.
Operator state changes require identity and reason and append an audit record.
