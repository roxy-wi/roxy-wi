class RoxywiPublicError(Exception):
    """Base class for domain errors whose message is safe to return to a client."""

    def __init__(self, message: str):
        self.public_message = message
        super().__init__(message)


class RoxywiGroupMismatch(Exception):
    """ Raised when not superAdmin tris update resource not from its group. """

    def __init__(self):
        super(RoxywiGroupMismatch, self).__init__('Group ID does not match')


class RoxywiGroupNotFound(Exception):
    """ Raised when a group not found. """

    def __init__(self):
        super(RoxywiGroupNotFound, self).__init__('Group not found')


class RoxywiResourceNotFound(RoxywiPublicError):
    """ This class represents an exception raised when a resource is not found. """

    def __init__(self, message='Resource not found'):
        super().__init__(message)


class RoxywiCheckLimits(Exception):
    """ This class represents an exception raised when a check limit is exceeded. """

    def __init__(self, message='You have reached limit for Free plan'):
        super(RoxywiCheckLimits, self).__init__(message)


class RoxywiValidationError(RoxywiPublicError):
    """ This class represents an exception raised when a validation error occurs. """

    def __init__(self, message='Validation error'):
        super().__init__(message)


class RoxywiPermissionError(RoxywiPublicError):
    """ This class represents an exception raised when a permission error occurs. """

    def __init__(self, message='Forbidden'):
        super().__init__(message)


class RoxywiInputError(RoxywiPublicError, ValueError):
    """Deliberate input validation with a client-safe message.

    Keep ValueError compatibility for existing validators. Never wrap an
    underlying exception, command output or database error in this type.
    """


class RoxywiConflictError(RoxywiPublicError):
    """ This class represents an exception raised when a conflict error occurs."""

    def __init__(self, message='Conflict'):
        super().__init__(message)
