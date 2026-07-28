class CodingAgentError(RuntimeError): pass
class DuplicateCodingAgentProviderError(CodingAgentError): pass
class CodingAgentProviderNotFoundError(CodingAgentError): pass
class CodingAgentProviderUnavailableError(CodingAgentError): pass
class NoCompatibleCodingAgentProviderError(CodingAgentError): pass
class CodingAgentTaskError(CodingAgentError): pass
