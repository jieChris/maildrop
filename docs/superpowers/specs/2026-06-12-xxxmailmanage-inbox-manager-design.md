# Xxxmailmanage Inbox Manager Design

## Goal

Build a Maildrop-integrated inbox manager at:

```text
https://aiprot.space/xxxmailmanage
```

The manager imports Maildrop-exported `email API-link` rows, stores them on the server, and lets the operator mark each imported mailbox as `待消耗`, `已消耗`, or `错误`.

## Non-Goals

- Do not create a separate service, port, or domain.
- Do not replace the existing `/admin` alias management backend.
- Do not store or display administrator credentials.
- Do not implement multi-user roles in the first version.
- Do not automatically change Maildrop alias lifecycle state when a manager row is marked `已消耗` or `错误`.

## Deployment Shape

Implement this inside the existing FastAPI Maildrop app and deploy with the current Docker Compose stack on `167.71.29.22`.

The page uses the same Basic Auth and CSRF protection as `/admin`. Caddy can keep proxying to the same app because the route is served by FastAPI.

## Data Model

Add a new table, for example `managed_inboxes`:

- `id`: integer primary key.
- `email`: unique lowercase email address.
- `api_url`: full latest.txt API URL.
- `status`: one of `pending`, `used`, `error`.
- `note`: optional text, default empty.
- `last_preview`: latest fetched plaintext preview, nullable.
- `last_error`: latest fetch error text, nullable.
- `last_checked_at`: nullable timestamp.
- `created_at`: timestamp.
- `updated_at`: timestamp.

Status labels:

- `pending` -> `待消耗`
- `used` -> `已消耗`
- `error` -> `错误`

Schema changes must use Alembic. Existing production rows are unaffected.

## Import Behavior

The import form accepts one row per mailbox. Supported separators:

- Space between email and URL, matching current Maildrop export.
- `----`, matching the provided template.
- Tab.
- Comma.

Examples:

```text
alpha@aiprot.space https://aiprot.space/api/inbox/alpha/latest.txt?token=...
beta@aiprot.space----https://aiprot.space/api/inbox/beta/latest.txt?token=...
gamma@aiprot.space	https://aiprot.space/api/inbox/gamma/latest.txt?token=...
```

Rules:

- Normalize email to lowercase.
- Ignore empty rows.
- Reject rows without both email and URL.
- Upsert by email: update `api_url`, keep existing `status` and `note`.
- New rows default to `pending`.
- Show an import summary: created count, updated count, invalid count.

## Manager UI

Use the provided `outlook邮箱管理.html` as visual reference:

- Purple-blue gradient page background.
- White rounded main container.
- Compact header.
- Large batch import textarea.
- Toolbar with search, status filter, stats, and bulk actions.
- Dense row list with status chips and row actions.
- Expandable details area for URL, note, preview, and last error.

Adapt the copy and controls to Maildrop:

- Title: `收件管理器`
- Subtitle: `导入邮箱和 API 链接，按消耗状态管理收件入口`
- Import button: `批量导入`
- Status filters: `全部`, `待消耗`, `已消耗`, `错误`
- Bulk status buttons: `标记待消耗`, `标记已消耗`, `标记错误`
- Row actions: `查看最新`, `复制链接`, `复制邮箱`, `删除`

The first version should be server-rendered Jinja2 with lightweight JavaScript for row selection, copy buttons, and optional expand/collapse. Data persistence belongs in PostgreSQL, not browser localStorage.

## Fetch Latest Mail

Each row can fetch its `api_url` server-side from a protected admin action. This avoids browser CORS issues and keeps behavior consistent.

Behavior:

- Admin clicks `查看最新`.
- Server requests the stored `api_url` with a short timeout.
- On HTTP 200, save a bounded plaintext preview to `last_preview`, clear `last_error`, update `last_checked_at`.
- On non-200 or network error, save `last_error`, update `last_checked_at`, and optionally mark status `error`.
- The preview should be bounded to avoid storing unexpectedly large responses.

## Routes

Use these route names:

- `GET /xxxmailmanage`: list/search/filter manager rows.
- `POST /xxxmailmanage/import`: import pasted rows.
- `POST /xxxmailmanage/status`: bulk update selected rows to `pending`, `used`, or `error`.
- `POST /xxxmailmanage/{item_id}/status`: update a single row status.
- `POST /xxxmailmanage/{item_id}/refresh`: fetch latest plaintext mail through `api_url`.
- `POST /xxxmailmanage/{item_id}/delete`: delete one manager row.

All POST routes require Basic Auth and CSRF.

## Filtering and Scale

Support at least 1000 imported rows:

- Pagination with configurable page size up to 200.
- Search by email and URL.
- Status filter.
- Stats for total, pending, used, error.

The page should avoid rendering excessively large unbounded lists.

## Testing

Add tests for:

- Import parser supports space, `----`, tab, and comma separators.
- Import creates new rows and updates duplicate email URLs without resetting status.
- Invalid rows are counted and ignored.
- `/xxxmailmanage` requires Basic Auth.
- CSRF is required for import and status changes.
- Status filters return the expected rows.
- Bulk status update changes selected rows only.
- Single delete removes a manager row.
- Refresh stores preview on success.
- Refresh stores error and marks row `error` on failure.
- Alembic migration creates the manager table.

## Documentation

Update:

- `README.md`: manager URL and import format.
- `docs/maildrop-ops.md`: deployment and manager behavior.
- `MAILDROP_MAIN.md`: current state and future context.

## Acceptance Criteria

- `https://aiprot.space/xxxmailmanage` is reachable with admin Basic Auth.
- Batch import accepts the current Maildrop export file format.
- Rows can be marked `待消耗`, `已消耗`, or `错误`.
- Search, status filter, and pagination work.
- Latest mail fetch works through stored API links.
- Production deploy passes local tests, Alembic migration, production check, and a manager smoke test.

