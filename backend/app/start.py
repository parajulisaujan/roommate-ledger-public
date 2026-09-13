"""Container entrypoint: production runtime never performs schema changes."""

import os


def main():
    environment = os.environ.get("APP_ENV", "development")
    if environment == "staging":
        from app.staging_start import main as staging

        staging()
        return
    if environment == "development":
        from alembic.config import Config

        from alembic import command

        command.upgrade(Config("alembic.ini"), "head")
    from app.serve import main as serve

    serve()


if __name__ == "__main__":
    main()
