"""Domain errors raised by services; main.py converts them to JSON HTTP responses.

Services never import FastAPI, so business rules stay testable without HTTP.
"""


class DomainError(Exception):
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class BadRequestError(DomainError):
    status_code = 400


class PermissionDeniedError(DomainError):
    status_code = 403


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409
