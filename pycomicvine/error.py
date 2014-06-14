class InvalidResourceError(Exception):
    pass

class InvalidAPIKeyError(Exception):
    pass

class ObjectNotFoundError(Exception):
    pass

class ErrorInURLFormatError(Exception):
    pass

class JSONError(Exception):
    pass

class FilterError(Exception):
    pass

class SubscriberOnlyError(Exception):
    pass

class RateLimitExceededError(Exception):
    pass

class UnknownStatusError(Exception):
    pass

class IllegalArquementException(Exception):
    pass

class NotConvertableError(Exception):
    pass

EXCEPTION_MAPPING = {
        100: InvalidAPIKeyError,
        101: ObjectNotFoundError,
        102: ErrorInURLFormatError,
        103: JSONError,
        104: FilterError,
        105: SubscriberOnlyError,
        107: RateLimitExceededError,
    }
