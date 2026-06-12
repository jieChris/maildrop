from pathlib import Path
import os
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "maildrop-production-check.sh"
DOCKERFILE = ROOT / "Dockerfile"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    path.chmod(0o755)


def _run_script(tmp_path: Path, *, dig_script: str, ssh_script: str) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir / "dig", dig_script)
    _write_executable(
        bin_dir / "curl",
        """\
        #!/bin/sh
        case "$*" in
          *"/api/health"*) exit 0 ;;
          *"/internal/ingest"*) printf '404'; exit 0 ;;
          *"/admin"*) printf '401'; exit 0 ;;
          *) exit 1 ;;
        esac
        """,
    )
    _write_executable(bin_dir / "ssh", ssh_script)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "MAILDROP_SKIP_PUBLIC_SMTP_CHECK": "1",
    }
    return subprocess.run(
        [str(SCRIPT), "aiprot.space", "emailengine", "167.71.29.22"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


GOOD_DIG = """\
#!/bin/sh
case "$*" in
  *"A mail.aiprot.space"*) printf '167.71.29.22\\n' ;;
  *"MX aiprot.space"*) printf '10 mail.aiprot.space.\\n' ;;
  *"TXT aiprot.space"*) printf '"v=spf1 -all"\\n' ;;
  *"TXT _dmarc.aiprot.space"*) printf '"v=DMARC1; p=reject; sp=reject"\\n' ;;
esac
"""


GOOD_SSH = """\
#!/bin/sh
case "$*" in
  *"docker compose"*) printf '{"Service":"app","State":"running","Health":"healthy"}\\n{"Service":"postgres","State":"running","Health":"healthy"}\\n'; exit 0 ;;
  *"postconf -n"*) printf 'virtual_transport = mailapi\\nmailapi_destination_recipient_limit = 1\\n'; exit 0 ;;
  *"postmap -q"*) printf 'catchall\\n'; exit 0 ;;
  *"mail-api-ingest.env"*) exit 0 ;;
  *"systemctl is-active"*) exit 0 ;;
  *":25 "*) exit 0 ;;
  *"127.0.0.1:8000"*) exit 0 ;;
  *) exit 0 ;;
esac
"""


def test_production_check_passes_when_dns_and_services_are_ready(tmp_path):
    result = _run_script(tmp_path, dig_script=GOOD_DIG, ssh_script=GOOD_SSH)

    assert result.returncode == 0
    assert "READY Maildrop production checks passed." in result.stdout


def test_production_check_falls_back_to_tcp_dns_when_udp_times_out(tmp_path):
    dig_script = """\
    #!/bin/sh
    case "$*" in
      *"+tcp"* )
        case "$*" in
          *"A mail.aiprot.space"*) printf '167.71.29.22\\n' ;;
          *"MX aiprot.space"*) printf '10 mail.aiprot.space.\\n' ;;
          *"TXT aiprot.space"*) printf '"v=spf1 -all"\\n' ;;
          *"TXT _dmarc.aiprot.space"*) printf '"v=DMARC1; p=reject; sp=reject"\\n' ;;
        esac
        exit 0
        ;;
      * )
        printf ';; connection timed out; no servers could be reached\\n' >&2
        exit 9
        ;;
    esac
    """

    result = _run_script(tmp_path, dig_script=dig_script, ssh_script=GOOD_SSH)

    assert result.returncode == 0
    assert "PASS aiprot.space MX -> 10 mail.aiprot.space." in result.stdout


def test_dockerfile_disables_uvicorn_access_log_to_avoid_query_token_leaks():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert '"--no-access-log"' in dockerfile


def test_production_check_warns_when_old_mx_records_remain(tmp_path):
    dig_script = GOOD_DIG.replace(
        "10 mail.aiprot.space.\\n",
        "10 mail.aiprot.space.\\n0 mx1.efwd.spaceship.net.\\n",
    )

    result = _run_script(tmp_path, dig_script=dig_script, ssh_script=GOOD_SSH)

    assert result.returncode == 2
    assert "DNS_NOT_READY" in result.stdout


def test_production_check_fails_when_docker_service_is_unhealthy(tmp_path):
    ssh_script = GOOD_SSH.replace('"Health":"healthy"', '"Health":"unhealthy"', 1)

    result = _run_script(tmp_path, dig_script=GOOD_DIG, ssh_script=ssh_script)

    assert result.returncode == 1
    assert "FAIL server docker compose health" in result.stdout
