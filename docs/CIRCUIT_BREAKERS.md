# Circuit Breakers

Failures degrade a provider and open its circuit at a configured threshold. An
injected clock moves an expired circuit to half-open with bounded probe concurrency.
Success closes it. Operator-disabled state cannot be bypassed automatically.
