# Maildrop Operations

## Current Production Status

Maildrop, PostgreSQL, Postfix, and Caddy are already deployed on `167.71.29.22`.
DNS has been cut over from Spaceship Email Forwarding Free to the self-hosted
Maildrop receive path.

Current public DNS target:

```text
NS aiprot.space             launch1.spaceship.net.
NS aiprot.space             launch2.spaceship.net.
SOA aiprot.space            launch1.spaceship.net. support.spaceship.com.
mail.aiprot.space A         167.71.29.22
aiprot.space MX             10 mail.aiprot.space.
aiprot.space TXT            "v=spf1 -all"
_dmarc.aiprot.space TXT     "v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s"
```

Last verified on 2026-06-12 with:

```bash
scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22
scripts/maildrop-public-smoke.py aiprot.space emailengine 167.71.29.22
```

Both commands exited `0`; the public smoke message landed in
`unassigned_messages`. Latest post-deploy smoke recipient:
`public-smoke-1781258315-4d3046ac@aiprot.space`.

## DNS

Set these records for `aiprot.space`:

```text
mail.aiprot.space.  A    167.71.29.22
aiprot.space.       MX   10 mail.aiprot.space.
aiprot.space.       TXT  "v=spf1 -all"
_dmarc.aiprot.space TXT  "v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s"
*.exa.aiprot.space. MX   10 mail.aiprot.space.
*.exa.aiprot.space. TXT  "v=spf1 -all"
exa.aiprot.space.   MX   10 mail.aiprot.space.
exa.aiprot.space.   TXT  "v=spf1 -all"
```

Maildrop is receive-only. If `aiprot.space` later needs to send mail, replace the SPF and DMARC policy with records for the actual sending provider before sending production mail.

Registered `exa` subdomains are controlled by the app, not by wildcard DNS
alone. Postfix is configured once to pass single-level `*.exa.aiprot.space`
recipients to Maildrop. Use `/admin/subdomains` to add names such as
`c.exa.aiprot.space`; the new suffix immediately appears in the bulk generator.
Unregistered names can reach the app through SMTP, but Maildrop keeps them out
of normal alias generation and records them as unsupported unless the domain is
registered in the app.

## API Tokens And Logs

Public inbox URLs use query tokens so they can be opened directly:

```text
https://aiprot.space/api/inbox/{prefix}/latest.txt?token={token}
```

Plain tokens are only shown once after bulk alias generation or token rotation.
If a link is lost, open `/admin`, find the alias, and click `轮换 token`. The old
link stops working immediately and the new link is shown once.

To export existing aliases, open `/admin`, select aliases and click
`导出选中并轮换 token`, or click `导出全部并轮换 token`. Export returns a
plain-text attachment with one `email latest.txt-url` pair per line. Exporting
rotates the affected aliases' tokens; old links stop working immediately. An
exported alias moves to the `已导出` category. Aliases that have never been
exported remain in `未导出`.

Aliases can be soft-deleted from `/admin`. Deletion sets `deleted_at`, disables
the alias, and moves it to `已删除`. Historical messages stay attached to the
alias for review. Public API links for deleted aliases return `403`; future
mail to the same prefix lands in `unassigned_messages` with reason
`alias_deleted`. Deleted aliases are excluded from `导出全部并轮换 token`.

## Xxxmailmanage Inbox Manager

`/xxxmailmanage` is a protected inbox manager that uses the same Basic Auth and
CSRF protection as `/admin`. It stores imported mailbox API links in PostgreSQL
instead of browser localStorage.

Accepted import formats:

```text
user001@aiprot.space https://aiprot.space/api/inbox/user001/latest.txt?token=...
user002@aiprot.space----https://aiprot.space/api/inbox/user002/latest.txt?token=...
```

Rows can be marked `待消耗`, `已消耗`, or `错误`. The `查看最新` action fetches
the stored API URL server-side, saves a bounded plaintext preview on success,
and marks the row `错误` on fetch failure.

Do not enable access logging that records full request URIs for Maildrop public
API paths. The production app starts Uvicorn with `--no-access-log`; Caddy should
remain without a site access-log directive unless query strings are explicitly
redacted.

## Deploy App

Generate secrets and start the app:

```bash
cd /opt/maildrop
cp .env.maildrop.example .env.maildrop
openssl rand -hex 24
openssl rand -hex 24
openssl rand -hex 24
vim .env.maildrop
docker compose -f docker-compose.maildrop.yml up -d --build
curl -fsS http://127.0.0.1:8000/api/health
```

Use the three random values for `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`, and `INGEST_TOKEN`. Keep `DATABASE_URL` and `POSTGRES_PASSWORD` in sync. Keep `MAX_MESSAGE_BYTES` and Postfix `message_size_limit` in sync so oversized mail is rejected at SMTP time instead of being accepted and then rejected by HTTP ingest.

For deploys that include schema changes, run migrations before restarting the
long-running app container:

```bash
cd /opt/maildrop
docker compose -f docker-compose.maildrop.yml build app
docker compose -f docker-compose.maildrop.yml run --rm app alembic upgrade head
docker compose -f docker-compose.maildrop.yml up -d app
```

## Install Postfix

Install packages and create the local pipe user:

```bash
apt-get update
apt-get install -y postfix curl
useradd -r -s /usr/sbin/nologin mailapi || true
```

Install the ingest script and token file:

```bash
cd /opt/maildrop
install -m 0755 deploy/postfix/mail-api-ingest /usr/local/bin/mail-api-ingest
tmp_env="$(mktemp)"
printf 'INGEST_TOKEN=%s\n' "$(grep '^INGEST_TOKEN=' .env.maildrop | cut -d= -f2-)" > "$tmp_env"
install -o root -g mailapi -m 0640 "$tmp_env" /etc/mail-api-ingest.env
rm -f "$tmp_env"
```

Apply `main.cf` settings idempotently:

```bash
cd /opt/maildrop
while IFS= read -r line; do
  case "$line" in
    ''|'#'*) continue ;;
  esac
  postconf -e "$line"
done < deploy/postfix/main.cf.maildrop
```

Create the virtual domain and catch-all recipient maps:

```bash
install -m 0644 deploy/postfix/virtual_mailbox_domains_regexp /etc/postfix/virtual_mailbox_domains_regexp
install -m 0644 deploy/postfix/virtual_mailbox_regexp /etc/postfix/virtual_mailbox_regexp
postmap -q 'a.exa.aiprot.space' regexp:/etc/postfix/virtual_mailbox_domains_regexp
postmap -q 'probe@aiprot.space' regexp:/etc/postfix/virtual_mailbox_regexp
```

Install the `mailapi` transport idempotently:

```bash
postconf -M -e 'mailapi/unix=mailapi unix - n n - - pipe flags=Rq user=mailapi argv=/usr/local/bin/mail-api-ingest ${recipient}'
```

Validate and restart:

```bash
postfix check
sudo -u mailapi sh -c '. /etc/mail-api-ingest.env; test -n "$INGEST_TOKEN"'
systemctl restart postfix
systemctl enable postfix
```

## Verify Receive Path

Check DNS:

```bash
dig +short A mail.aiprot.space @1.1.1.1
dig +short MX aiprot.space @1.1.1.1
```

Send a local SMTP test if `swaks` is available:

```bash
swaks --to testunknown@aiprot.space --from sender@example.net --server 127.0.0.1
```

Inspect app logs:

```bash
docker compose -f docker-compose.maildrop.yml logs --tail=100 app
```

Unknown recipients should appear in `/admin/unassigned`.

Run the repeatable production check from the project root:

```bash
scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22
```

Exit codes:

- `0`: DNS, HTTPS, Docker, and Postfix checks passed.
- `1`: service or server check failed.
- `2`: services are reachable but DNS is not fully switched to Maildrop yet.

The script requires exact DNS cutover: `mail.aiprot.space` must have only the
expected A record, and `aiprot.space` must have only the Maildrop MX record. It
also checks Caddy, Docker health, Postfix mailapi settings, catch-all regexp,
mailapi token readability, and public SMTP port reachability once DNS is ready.
If UDP DNS queries to `1.1.1.1` time out locally, the script retries the same
checks over TCP before marking DNS as not ready.
If the machine running the check cannot open outbound SMTP 25, the final SMTP
check falls back to an SSH server-side connection to `mail.aiprot.space:25`.

After the production check exits `0`, run a real public SMTP smoke test:

```bash
scripts/maildrop-public-smoke.py aiprot.space emailengine 167.71.29.22
```

This sends a unique message to `public-smoke-...@aiprot.space` through
`mail.aiprot.space:25`, then queries PostgreSQL on the server to confirm the
message landed in `unassigned_messages`. If local outbound SMTP 25 is blocked,
the script sends the same smoke message from the server side and still verifies
the database result. Latest smoke recipient after the `/xxxmailmanage` deploy:
`public-smoke-1781265874-77509bc7@aiprot.space`.

For `/xxxmailmanage`, a production HTTPS smoke can import one temporary row,
mark it `已消耗`, and confirm `managed_inboxes.status = 'used'`. Latest smoke
record:

```text
managesmoke1781265819@aiprot.space status=used
```

## Back Up PostgreSQL

Create a compressed backup:

```bash
cd /opt/maildrop
docker compose -f docker-compose.maildrop.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "maildrop-$(date +%F).sql.gz"
```

Restore into an empty database:

```bash
cd /opt/maildrop
gunzip -c maildrop-YYYY-MM-DD.sql.gz | docker compose -f docker-compose.maildrop.yml exec -T postgres \
  psql -U "$POSTGRES_USER" "$POSTGRES_DB"
```

## Clean Up Old Mail

Maildrop keeps registered alias mail for `MESSAGE_RETENTION_DAYS` and
unassigned mail for `UNASSIGNED_RETENTION_DAYS`. Defaults:

```dotenv
MESSAGE_RETENTION_DAYS=180
UNASSIGNED_RETENTION_DAYS=30
```

Run cleanup manually:

```bash
cd /opt/maildrop
docker compose -f docker-compose.maildrop.yml exec -T app python -m maildrop.cli cleanup --dry-run
docker compose -f docker-compose.maildrop.yml exec -T app python -m maildrop.cli cleanup
```

Run `--dry-run` first after changing retention settings or before enabling cron
on a production database.

Install a daily cron job:

```bash
cat >/etc/cron.d/maildrop-cleanup <<'EOF'
17 3 * * * root cd /opt/maildrop && flock -n /var/lock/maildrop-cleanup.lock docker compose -f docker-compose.maildrop.yml exec -T app python -m maildrop.cli cleanup >> /var/log/maildrop-cleanup.log 2>&1
EOF
```

## Roll Back To EmailEngine

Do not delete Maildrop or EmailEngine volumes during the first production test window.

```bash
cd /opt/emailengine
docker compose up -d
```
