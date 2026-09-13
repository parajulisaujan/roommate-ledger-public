class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


def invalid(message: str = "Check the required fields, dates and amounts.") -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", message)


def forbidden() -> ApiError:
    return ApiError(403, "FORBIDDEN", "You do not have access to this record.")


def missing() -> ApiError:
    return ApiError(404, "NOT_FOUND", "Record not found.")


def conflict(
    message: str = "This record conflicts with existing data. Refresh and try again.",
) -> ApiError:
    return ApiError(409, "CONFLICT", message)
