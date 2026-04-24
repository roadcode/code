class WebRpaError(Exception):
    """Base class for actionable Web RPA errors."""

    code = "WebRpaError"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class InvalidFlow(WebRpaError):
    code = "InvalidFlow"


class MissingVariable(WebRpaError):
    code = "MissingVariable"


class SelectorNotFound(WebRpaError):
    code = "SelectorNotFound"


class SelectorAmbiguous(WebRpaError):
    code = "SelectorAmbiguous"


class WaitTimeout(WebRpaError):
    code = "WaitTimeout"


class BrowserLaunchFailed(WebRpaError):
    code = "BrowserLaunchFailed"
