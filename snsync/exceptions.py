

class SNSyncException(Exception):
    """ Base exception class. All Sync related exceptions should subclass
        this class
    """
    pass


class ConfigurationFileNotFound(SNSyncException):
    """ Raised when the configuration file cannot be found """
    pass


class InvalidConfiguration(SNSyncException):
    """ Raised when the configuration is not valid """
    pass


class InstanceNotFound(SNSyncException):
    """ Raised when an instance is not found """
    pass

class LoginFailed(SNSyncException):
    """ Raised when we are not able to authenticate to an instance """
    pass


class UnknownAuthMethod(SNSyncException):
    """ Raised when an authentication method is not known """
    pass