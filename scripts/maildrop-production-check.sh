#!/bin/sh
set -u

DOMAIN="${1:-aiprot.space}"
SERVER_HOST="${2:-emailengine}"
SERVER_IP="${3:-167.71.29.22}"

DNS_WARNINGS=0
FAILURES=0

pass() {
  printf 'PASS %s\n' "$1"
}

warn() {
  DNS_WARNINGS=$((DNS_WARNINGS + 1))
  printf 'WARN %s\n' "$1"
}

fail() {
  FAILURES=$((FAILURES + 1))
  printf 'FAIL %s\n' "$1"
}

need_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "missing command: $1"
  fi
}

need_command curl
need_command dig
need_command python3
need_command ssh

if [ "$FAILURES" -ne 0 ]; then
  exit 1
fi

dig_short() {
  record_type="$1"
  record_name="$2"
  result="$(dig +short "$record_type" "$record_name" @1.1.1.1 2>&1 | sort)"
  if [ -z "$result" ] || printf '%s\n' "$result" | grep -qi 'connection timed out'; then
    result="$(dig +tcp +short "$record_type" "$record_name" @1.1.1.1 2>/dev/null | sort)"
  fi
  printf '%s\n' "$result"
}

MAIL_A_RECORDS="$(dig_short A "mail.$DOMAIN")"
MX_RECORDS="$(dig_short MX "$DOMAIN")"
SPF_RECORDS="$(dig_short TXT "$DOMAIN" | tr -d '"')"
DMARC_RECORDS="$(dig_short TXT "_dmarc.$DOMAIN" | tr -d '"')"

if [ "$MAIL_A_RECORDS" = "$SERVER_IP" ]; then
  pass "mail.$DOMAIN A -> $SERVER_IP"
else
  warn "mail.$DOMAIN A is '${MAIL_A_RECORDS:-empty}', expected exactly '$SERVER_IP'"
fi

EXPECTED_MX="10 mail.$DOMAIN."
if [ "$MX_RECORDS" = "$EXPECTED_MX" ]; then
  pass "$DOMAIN MX -> $EXPECTED_MX"
else
  warn "$DOMAIN MX is '${MX_RECORDS:-empty}', expected exactly '$EXPECTED_MX'"
fi

if printf '%s\n' "$SPF_RECORDS" | grep -Fx 'v=spf1 -all' >/dev/null 2>&1; then
  pass "$DOMAIN SPF receive-only policy"
else
  warn "$DOMAIN SPF is '${SPF_RECORDS:-empty}', expected 'v=spf1 -all'"
fi

if printf '%s\n' "$DMARC_RECORDS" | python3 -c '
import sys
records = [line.strip() for line in sys.stdin if line.strip()]
for record in records:
    tags = {}
    for part in record.split(";"):
        if "=" in part:
            key, value = part.strip().split("=", 1)
            tags[key.strip().lower()] = value.strip().lower()
    if tags.get("v", "").lower() == "dmarc1" and tags.get("p") == "reject":
        raise SystemExit(0)
raise SystemExit(1)
'; then
  pass "_dmarc.$DOMAIN reject policy"
else
  warn "_dmarc.$DOMAIN is '${DMARC_RECORDS:-empty}', expected DMARC p=reject"
fi

if curl -fsS "https://$DOMAIN/api/health" >/dev/null 2>&1; then
  pass "HTTPS health endpoint"
else
  fail "HTTPS health endpoint"
fi

INTERNAL_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' "https://$DOMAIN/internal/ingest" || true)"
if [ "$INTERNAL_STATUS" = "404" ]; then
  pass "public /internal/* blocked"
else
  fail "public /internal/* returned HTTP $INTERNAL_STATUS, expected 404"
fi

ADMIN_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' "https://$DOMAIN/admin" || true)"
if [ "$ADMIN_STATUS" = "401" ]; then
  pass "admin requires authentication"
else
  fail "admin returned HTTP $ADMIN_STATUS, expected 401 without credentials"
fi

if ssh "$SERVER_HOST" 'cd /opt/maildrop && docker compose -f docker-compose.maildrop.yml ps --format json' | python3 -c '
import json
import sys

required = {"app", "postgres"}
seen = {}
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    item = json.loads(line)
    service = item.get("Service") or item.get("Name")
    if service in required:
        seen[service] = item

if set(seen) != required:
    raise SystemExit(1)

for service, item in seen.items():
    health = str(item.get("Health") or "").lower()
    state = str(item.get("State") or "").lower()
    if health != "healthy" or state not in {"running", "up"}:
        raise SystemExit(1)
' >/dev/null 2>&1; then
  pass "server docker compose reports healthy services"
else
  fail "server docker compose health"
fi

if ssh "$SERVER_HOST" 'systemctl is-active --quiet postfix' >/dev/null 2>&1; then
  pass "server postfix active"
else
  fail "server postfix active"
fi

if ssh "$SERVER_HOST" 'postconf -n | grep -Fx "virtual_transport = mailapi" >/dev/null && postconf -n | grep -Fx "mailapi_destination_recipient_limit = 1" >/dev/null' >/dev/null 2>&1; then
  pass "server postfix mailapi transport settings"
else
  fail "server postfix mailapi transport settings"
fi

if ssh "$SERVER_HOST" "postmap -q 'probe@$DOMAIN' regexp:/etc/postfix/virtual_mailbox_regexp | grep -Fx catchall >/dev/null" >/dev/null 2>&1; then
  pass "server postfix catch-all regexp"
else
  fail "server postfix catch-all regexp"
fi

if ssh "$SERVER_HOST" "runuser -u mailapi -- sh -c '. /etc/mail-api-ingest.env; test -n \"\$INGEST_TOKEN\"'" >/dev/null 2>&1; then
  pass "server mailapi can read ingest token"
else
  fail "server mailapi can read ingest token"
fi

if ssh "$SERVER_HOST" 'ss -ltn | grep -q ":25 "' >/dev/null 2>&1; then
  pass "server listens on SMTP 25"
else
  fail "server listens on SMTP 25"
fi

if ssh "$SERVER_HOST" 'ss -ltn | grep -q "127.0.0.1:8000"' >/dev/null 2>&1; then
  pass "maildrop app bound to 127.0.0.1:8000"
else
  fail "maildrop app bound to 127.0.0.1:8000"
fi

if [ "$FAILURES" -ne 0 ]; then
  exit 1
fi

if [ "$DNS_WARNINGS" -ne 0 ]; then
  printf 'DNS_NOT_READY %s warning(s); update DNS provider records and rerun this script.\n' "$DNS_WARNINGS"
  exit 2
fi

if [ "${MAILDROP_SKIP_PUBLIC_SMTP_CHECK:-}" = "1" ]; then
  pass "public SMTP 25 connection skipped"
elif python3 - "$DOMAIN" 2>/dev/null <<'PY'
import socket
import sys

domain = sys.argv[1]
with socket.create_connection((f"mail.{domain}", 25), timeout=10) as sock:
    banner = sock.recv(256)
    if not banner.startswith(b"220"):
        raise SystemExit(1)
PY
then
  pass "public SMTP 25 connection to mail.$DOMAIN"
elif ssh "$SERVER_HOST" "python3 - '$DOMAIN'" <<'PY' >/dev/null 2>&1
import socket
import sys

domain = sys.argv[1]
with socket.create_connection((f"mail.{domain}", 25), timeout=10) as sock:
    banner = sock.recv(256)
    if not banner.startswith(b"220"):
        raise SystemExit(1)
PY
then
  pass "public SMTP 25 connection to mail.$DOMAIN from server fallback"
else
  fail "public SMTP 25 connection to mail.$DOMAIN"
fi

if [ "$FAILURES" -ne 0 ]; then
  exit 1
fi

printf 'READY Maildrop production checks passed.\n'
