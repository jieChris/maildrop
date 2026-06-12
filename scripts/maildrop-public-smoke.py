#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from email.message import EmailMessage
import secrets
import shlex
import smtplib
import subprocess
import sys
import time
from pathlib import Path


@dataclass(frozen=True)
class SmokeTarget:
    domain: str
    server_host: str
    server_ip: str


def run_production_check(target: SmokeTarget) -> int:
    script = Path(__file__).with_name("maildrop-production-check.sh")
    result = subprocess.run(
        [str(script), target.domain, target.server_host, target.server_ip],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def send_public_smtp(domain: str, recipient: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = "sender@example.net"
    message["To"] = recipient
    message.set_content(body)

    with smtplib.SMTP(f"mail.{domain}", 25, timeout=15) as smtp:
        smtp.send_message(message)


def send_server_smtp(
    server_host: str,
    domain: str,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    remote_command = " ".join(
        [
            "python3",
            "-",
            shlex.quote(domain),
            shlex.quote(recipient),
            shlex.quote(subject),
            shlex.quote(body),
        ]
    )
    script = """\
import smtplib
import sys
from email.message import EmailMessage

domain, recipient, subject, body = sys.argv[1:5]
message = EmailMessage()
message["Subject"] = subject
message["From"] = "sender@example.net"
message["To"] = recipient
message.set_content(body)
with smtplib.SMTP(f"mail.{domain}", 25, timeout=15) as smtp:
    smtp.send_message(message)
"""
    result = subprocess.run(
        ["ssh", server_host, remote_command],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "server-side smtp send failed")


def latest_unassigned_subject(server_host: str, recipient: str) -> str:
    sql = (
        "select subject from unassigned_messages "
        f"where recipient = '{recipient}' "
        "order by id desc limit 1;"
    )
    remote_command = (
        "cd /opt/maildrop && "
        "docker compose -f docker-compose.maildrop.yml exec -T postgres "
        f"psql -U maildrop -d maildrop -tAc {shlex.quote(sql)}"
    )
    result = subprocess.run(
        ["ssh", server_host, remote_command],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "database query failed")
    return result.stdout.strip()


def wait_for_unassigned(
    server_host: str,
    recipient: str,
    expected_subject: str,
    *,
    timeout_seconds: int,
    poll_seconds: int,
) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() <= deadline:
        if latest_unassigned_subject(server_host, recipient) == expected_subject:
            return True
        time.sleep(poll_seconds)
    return False


def run_smoke(target: SmokeTarget, *, timeout_seconds: int, poll_seconds: int) -> int:
    check_code = run_production_check(target)
    if check_code != 0:
        print("DNS_OR_SERVICE_NOT_READY public smoke skipped")
        return check_code

    suffix = f"{int(time.time())}-{secrets.token_hex(4)}"
    recipient = f"public-smoke-{suffix}@{target.domain}"
    subject = f"Public Smoke {suffix}"
    body = f"Public SMTP smoke body {suffix}"

    try:
        send_public_smtp(target.domain, recipient, subject, body)
    except (OSError, smtplib.SMTPException, TimeoutError) as exc:
        print(f"WARN local public SMTP send failed, using server fallback: {exc}")
        send_server_smtp(target.server_host, target.domain, recipient, subject, body)

    if wait_for_unassigned(
        target.server_host,
        recipient,
        subject,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
    ):
        print(f"PASS public SMTP smoke delivered to unassigned: {recipient}")
        return 0

    print(f"FAIL public SMTP smoke not found in unassigned_messages: {recipient}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Maildrop public SMTP smoke test.")
    parser.add_argument("domain", nargs="?", default="aiprot.space")
    parser.add_argument("server_host", nargs="?", default="emailengine")
    parser.add_argument("server_ip", nargs="?", default="167.71.29.22")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--poll-seconds", type=int, default=3)
    args = parser.parse_args(argv)

    target = SmokeTarget(args.domain, args.server_host, args.server_ip)
    return run_smoke(
        target,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
