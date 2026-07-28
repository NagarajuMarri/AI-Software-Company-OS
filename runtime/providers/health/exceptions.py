class ProviderHealthError(RuntimeError): pass
class ProviderHealthNotFoundError(ProviderHealthError): pass
class ProviderHealthVersionConflictError(ProviderHealthError): pass
class ProviderUnavailableError(ProviderHealthError): pass
class OperatorAuthorizationError(ProviderHealthError): pass
