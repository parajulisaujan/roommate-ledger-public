"""Production entrypoint; forwarding is validated by the application's CIDR policy."""

import logging
import os
import sys
from copy import deepcopy

import uvicorn

from app.logging import JsonFormatter


class StagingServerFormatter(JsonFormatter):
    def format(self, record):
        # Uvicorn lifespan errors can embed an entire traceback in the message.
        if record.levelno >= logging.WARNING:
            return "STAGING FAIL application_startup_or_runtime; server details suppressed"
        return "STAGING SERVER " + record.levelname


class ProductionServerFormatter(JsonFormatter):
    def format(self, record):
        # Import, bind and lifespan messages can contain environment values or
        # formatted tracebacks, even when record.exc_info is absent.
        return "PRODUCTION SERVER " + record.levelname + "; details suppressed"


def main(*, sanitized=False):
    production = os.environ.get("APP_ENV") == "production"
    try:
        run_server(sanitized=sanitized, production=production)
    except (Exception, SystemExit):
        if not production:
            raise
        print(
            "PRODUCTION STARTUP FAILED; check configuration and readiness privately",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1) from None


def run_server(*, sanitized=False, production=False):
    log_config = deepcopy(uvicorn.config.LOGGING_CONFIG)
    if sanitized or production:
        log_config["formatters"] = {
            key: {"()": StagingServerFormatter if sanitized else ProductionServerFormatter}
            for key in log_config["formatters"]
        }
    if production:
        # Keep the safe formatter on the child logger too. create_app's logging
        # setup recognizes JsonFormatter subclasses and preserves this handler.
        log_config["loggers"]["uvicorn.error"]["handlers"] = ["default"]
        log_config["loggers"]["uvicorn.error"]["propagate"] = False
    config = uvicorn.Config(
        "app.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
        proxy_headers=False,
        access_log=False,
        timeout_graceful_shutdown=150,
        log_config=log_config,
    )
    server = uvicorn.Server(config)
    server.run()
    if (sanitized or production) and not server.started:
        raise RuntimeError("Application startup failed.")


if __name__ == "__main__":
    main()
