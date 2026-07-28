# Worker Shutdown

SIGINT, SIGTERM where available, operator requests, and limits stop new claims.
The loop finishes current synchronous local work and records a terminal worker status.
Uncertain provider calls remain governed by outbox reconciliation and claim fencing.
