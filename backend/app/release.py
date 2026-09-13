"""Explicit, sanitized production migration preflight/apply; no runtime DDL."""

import argparse
import contextlib
import io
import logging
import ssl
import sys
from pathlib import Path

from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.config import Settings
from app.db import engine_for


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        print("RELEASE FAIL arguments", file=sys.stderr)
        raise SystemExit(1)


def prepare(settings: Settings, expected_database: str, *, apply: bool = False):
    url = settings.sqlalchemy_url
    ca = "/etc/ssl/certs/ca-certificates.crt"
    if (
        settings.app_env != "production"
        or not expected_database
        or expected_database == "roommateledger_staging"
        or url.database != expected_database
        or not url.host
        or url.query.get("sslmode") != "verify-full"
        or url.query.get("sslrootcert") != ca
    ):
        raise RuntimeError("Release configuration rejected.")
    ssl.create_default_context(cafile=ca)
    engine = engine_for(settings, pool_size=1, max_overflow=0, migration=True)
    try:
        with engine.connect() as connection:
            if (
                connection.execute(text("SELECT current_database()")).scalar_one()
                != expected_database
            ):
                raise RuntimeError("Release database identity rejected.")
            if connection.connection.driver_connection.pgconn.ssl_in_use is not True:
                raise RuntimeError("Release TLS unavailable.")
            connection.rollback()
            if apply:
                config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
    finally:
        engine.dispose()


def main():
    parser = SafeParser(description=__doc__)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    previous = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        # Third-party migration output is never suitable for a shared release log.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            prepare(Settings(), args.expected_database, apply=args.apply)
    except (Exception, SystemExit):
        print("RELEASE FAIL preflight_or_migration", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        logging.disable(previous)
    print("RELEASE PASS migration" if args.apply else "RELEASE PASS connection_preflight")


if __name__ == "__main__":
    main()
