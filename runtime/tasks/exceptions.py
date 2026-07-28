class ExternalTaskError(RuntimeError): pass
class ExternalTaskNotFoundError(ExternalTaskError): pass
class InvalidExternalTaskTransitionError(ExternalTaskError): pass
class ApprovalPolicyError(ExternalTaskError): pass
class ExternalOperationError(ExternalTaskError): pass
