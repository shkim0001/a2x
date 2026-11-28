"""서비스 계층 오류. API 계층이 HTTP 응답으로 바꾼다."""


class ServiceError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFound(ServiceError):
    status = 404
    code = "not_found"


class Unauthorized(ServiceError):
    status = 401
    code = "unauthorized"


class Forbidden(ServiceError):
    status = 403
    code = "forbidden"


class Conflict(ServiceError):
    status = 409
    code = "conflict"


class Invalid(ServiceError):
    status = 422
    code = "invalid"
