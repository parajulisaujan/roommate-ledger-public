"""An additional origin gate; application authentication and CSRF still apply."""

from secrets import compare_digest

from starlette.responses import JSONResponse


class DeploymentIngress:
    def __init__(self, app, key: str):
        self.app = app
        self.key = key.encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        # Read-only provider probes disclose no user or database details.
        probe = scope["method"] in {"GET", "HEAD"} and scope["path"] in {
            "/health",
            "/actuator/health/liveness",
            "/actuator/health/readiness",
        }
        values = [v for k, v in scope["headers"] if k.lower() == b"x-ledger-proxy-key"]
        if not probe and (len(values) != 1 or not compare_digest(values[0], self.key)):
            response = JSONResponse(
                {"code": "NOT_FOUND", "message": "Not found."},
                status_code=404,
                headers={"Cache-Control": "no-store"},
            )
            return await response(scope, receive, send)
        # Never pass the origin credential into endpoint handling or request logging.
        scope = dict(scope)
        scope["headers"] = [
            (k, v) for k, v in scope["headers"] if k.lower() != b"x-ledger-proxy-key"
        ]
        return await self.app(scope, receive, send)
