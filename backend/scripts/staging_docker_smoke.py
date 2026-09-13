"""Isolated TLS staging smoke. Uses only generated certificates and fictional secrets.

Build backend/Dockerfile as roommateledger-staging-fix before running this script.
Requires Docker; no provider settings are read. Resources are removed on exit.
"""

import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

IMAGE = "roommateledger-staging-fix"
HOST = "ep-smoke.neon.tech"
CA = "/etc/ssl/certs/ca-certificates.crt"


def docker(*args, check=True):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120)
    if check and result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result


def main():
    name = "ledger-staging-smoke-" + uuid4().hex[:10]
    api, db = name + "-api", name + "-db"
    env = {
        "APP_ENV": "staging",
        "DATABASE_URL": f"postgresql://fictional_user:fictional_password@{HOST}/roommateledger_staging?sslmode=verify-full&sslrootcert={CA}&connect_timeout=3",
        "FRONTEND_URL": "https://preview.example.test",
        "COOKIE_SECURE": "true",
        "EMAIL_VERIFICATION_REQUIRED": "true",
        "DEPLOYMENT_PROXY_REQUIRED": "true",
        "DEPLOYMENT_PROXY_KEY": "fictional-proxy-key-" * 3,
        "SMTP_HOST": "sandbox.smtp.mailtrap.io",
        "SMTP_PORT": "2525",
        "SMTP_STARTTLS": "true",
        "SMTP_USERNAME": "fictional_smtp_user",
        "SMTP_PASSWORD": "fictional_smtp_password",
        "EMAIL_FROM": "ledger-staging@example.test",
    }

    def arguments(changes=None):
        return [arg for k, v in (env | (changes or {})).items() for arg in ("-e", f"{k}={v}")]

    def safe(output):
        for value in (
            env["DATABASE_URL"],
            "fictional_user",
            "fictional_password",
            env["SMTP_USERNAME"],
            env["SMTP_PASSWORD"],
            env["DEPLOYMENT_PROXY_KEY"],
        ):
            assert value not in output, "Credential leaked into startup diagnostics"
        assert "Traceback" not in output

    with tempfile.TemporaryDirectory(prefix="ledger-staging-cert-") as directory:
        cert = str(Path(directory) / "server.crt")
        mount = ["-v", f"{cert}:{CA}:ro"]
        try:
            docker("network", "create", "--internal", name)
            # Network isolation ensures this Neon-shaped hostname stays local.
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0",
                "-v",
                f"{directory}:/fixtures",
                IMAGE,
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                f"/CN={HOST}",
                "-addext",
                f"subjectAltName=DNS:{HOST}",
                "-keyout",
                "/fixtures/server.key",
                "-out",
                "/fixtures/server.crt",
            )
            result = docker(
                "run",
                "--rm",
                "--network",
                "none",
                IMAGE,
                "python",
                "-c",
                f"import ssl; from pathlib import Path; assert Path('{CA}').is_file(); "
                f"assert ssl.create_default_context(cafile='{CA}').get_ca_certs(); print('PASS image CA bundle')",
            )
            print(result.stdout.strip(), flush=True)
            docker(
                "run",
                "-d",
                "--name",
                db,
                "--network",
                name,
                "--network-alias",
                HOST,
                "-v",
                f"{directory}:/fixtures:ro",
                "-e",
                "POSTGRES_USER=fictional_user",
                "-e",
                "POSTGRES_PASSWORD=fictional_password",
                "-e",
                "POSTGRES_DB=roommateledger_staging",
                "postgres:17-alpine",
                "sh",
                "-c",
                "cp /fixtures/server.* /tmp/ && chown postgres:postgres /tmp/server.* "
                "&& chmod 600 /tmp/server.key && exec docker-entrypoint.sh postgres "
                "-c ssl=on -c ssl_cert_file=/tmp/server.crt -c ssl_key_file=/tmp/server.key",
            )
            for _ in range(60):
                if (
                    docker("exec", db, "pg_isready", "-U", "fictional_user", check=False).returncode
                    == 0
                ):
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Local TLS PostgreSQL did not start")

            for label, changes, mounts in (
                ("ca_bundle", {}, ["--tmpfs", "/etc/ssl/certs"]),
                ("settings_validation", {"COOKIE_SECURE": "false"}, mount),
                ("staging_configuration", {"SMTP_PORT": "587"}, mount),
                (
                    "database_connection",
                    {"DATABASE_URL": env["DATABASE_URL"].replace("fictional_password", "wrong")},
                    mount,
                ),
                ("database_tls_handshake", {}, []),
                ("application_startup", {"PORT": "invalid"}, mount),
            ):
                result = docker(
                    "run",
                    "--rm",
                    "--network",
                    name,
                    *mounts,
                    *arguments(changes),
                    IMAGE,
                    "python",
                    "-m",
                    "app.staging_start",
                    check=False,
                )
                output = result.stdout + result.stderr
                safe(output)
                assert result.returncode != 0 and f"STAGING FAIL {label}" in output, output
                print(f"PASS sanitized {label} failure", flush=True)

            docker(
                "run",
                "-d",
                "--name",
                api,
                "--network",
                name,
                *mount,
                *arguments(),
                IMAGE,
                "python",
                "-m",
                "app.staging_start",
            )
            for attempt in range(2):
                for _ in range(60):
                    probe = docker(
                        "exec",
                        api,
                        "python",
                        "-c",
                        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/actuator/health/readiness', timeout=2)",
                        check=False,
                    )
                    if probe.returncode == 0:
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError("Staging readiness failed")
                output = docker("logs", api).stdout + docker("logs", api).stderr
                safe(output)
                assert "STAGING PASS alembic_migration" in output
                print(
                    f"PASS TLS, migration, application readiness (start {attempt + 1})", flush=True
                )
                if attempt == 0:
                    docker("restart", api)
        finally:
            docker("rm", "-f", "-v", api, db, check=False)
            docker("network", "rm", name, check=False)


if __name__ == "__main__":
    main()
