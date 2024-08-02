class RoxywiGroupMismatch(Exception):
    """ Raised when not superAdmin tris update resource not from its group. """

    def __init__(self):
        super(RoxywiGroupMismatch, self).__init__('Group ID does not match')


class RoxywiGroupNotFound(Exception):
    """ Raised when a group not found. """

    def __init__(self):
        super(RoxywiGroupNotFound, self).__init__('Group not found')


class RoxywiResourceNotFound(Exception):
    """ This class represents an exception raised when a resource is not found. """

    def __init__(self, message='Resource not found'):
        super(RoxywiResourceNotFound, self).__init__(message)


class RoxywiCheckLimits(Exception):
    """ This class represents an exception raised when a check limit is exceeded. """

    def __init__(self, message='You have reached limit for Free plan'):
        super(RoxywiCheckLimits, self).__init__(message)


class RoxywiValidationError(Exception):
    """ This class represents an exception raised when a validation error occurs. """

    def __init__(self, message='Validation error'):
        super(RoxywiValidationError, self).__init__(message)
