"""User-facing errors. Messages are safe to print; they carry no message body."""


class HailerError(Exception):
    """Expected failure the operator can fix."""


class ConfigError(HailerError):
    """hailer.toml is missing or invalid."""


class TooManyAccounts(HailerError):
    """The operator tried to watch more than the supported account cap."""


class NotifyFromNotAuthorized(HailerError):
    """notify_from is not one of the OAuth-connected accounts."""
