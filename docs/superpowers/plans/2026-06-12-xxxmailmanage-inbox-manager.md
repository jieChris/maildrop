# Xxxmailmanage Inbox Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/xxxmailmanage`, a protected Maildrop inbox manager that imports exported `email API-link` rows and tracks each row as `待消耗`, `已消耗`, or `错误`.

**Architecture:** Add a `managed_inboxes` table with Alembic migration and SQLAlchemy model. Put import parsing and manager database operations in a new `maildrop.manager` module, then expose server-rendered FastAPI routes under `/xxxmailmanage` using the existing Basic Auth and CSRF helpers. The UI uses a dedicated Jinja template and CSS file modeled on the provided Outlook manager HTML: gradient shell, white container, batch import textarea, toolbar stats, dense status rows, and row details.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Jinja2, lightweight JavaScript, pytest, Docker Compose.

---

## Files

- Create `src/maildrop/manager.py`: parse import text, upsert manager rows, update status, fetch/update previews.
- Modify `src/maildrop/models.py`: add `ManagedInbox`.
- Create `migrations/versions/20260612_0002_create_managed_inboxes.py`: create/drop manager table.
- Modify `tests/maildrop/test_migrations.py`: assert Alembic head creates `managed_inboxes`.
- Create `tests/maildrop/test_manager.py`: parser and repository-level manager behavior.
- Create `tests/maildrop/test_xxxmailmanage.py`: route, auth, CSRF, filter, bulk update, delete, refresh behavior.
- Modify `src/maildrop/app.py`: mount `/xxxmailmanage` routes using helpers from `maildrop.manager`.
- Create `src/maildrop/templates/xxxmailmanage.html`: manager page.
- Create `src/maildrop/static/xxxmailmanage.css`: visual style based on the provided template.
- Modify `src/maildrop/templates/base.html`: add nav link to `/xxxmailmanage`.
- Modify `pyproject.toml`: include new static CSS in package data if current wildcard is insufficient.
- Modify `README.md`, `docs/maildrop-ops.md`, `MAILDROP_MAIN.md`: document usage, deployment, and production result.

## Task 1: Data Model and Migration

- [x] Add a failing migration test that upgrades a database to head and asserts `managed_inboxes` exists with columns `email`, `api_url`, `status`, `note`, `last_preview`, `last_error`, `last_checked_at`, `created_at`, and `updated_at`.
- [x] Run `.venv/bin/python -m pytest tests/maildrop/test_migrations.py -q`; expected failure is missing `managed_inboxes`.
- [x] Add `ManagedInbox` model with unique indexed lowercase `email`, required `api_url`, `status`, `note`, preview/error/check timestamps, and created/updated timestamps.
- [x] Add migration `20260612_0002_create_managed_inboxes.py` with `down_revision = "20260612_0001"`.
- [x] Run `.venv/bin/python -m pytest tests/maildrop/test_migrations.py -q`; expected pass.

## Task 2: Manager Parser and Repository

- [x] Create failing parser tests for space, `----`, tab, and comma separators plus invalid rows.
- [x] Create failing repository tests for import upsert preserving existing status/note, bulk status updates, delete, and stats counts.
- [x] Run `.venv/bin/python -m pytest tests/maildrop/test_manager.py -q`; expected failure because `maildrop.manager` does not exist.
- [x] Implement `parse_import_rows(text)`, `import_managed_inboxes(db, text)`, `manager_stats(db)`, `bulk_update_status(db, ids, status)`, and `delete_managed_inbox(db, item_id)`.
- [x] Run `.venv/bin/python -m pytest tests/maildrop/test_manager.py -q`; expected pass.

## Task 3: Protected Routes

- [x] Add failing route tests for `/xxxmailmanage` Basic Auth, CSRF on import, successful import summary, status filter/search, bulk status update, single delete, refresh success, and refresh error.
- [x] Run `.venv/bin/python -m pytest tests/maildrop/test_xxxmailmanage.py -q`; expected failures because routes do not exist.
- [x] Add FastAPI routes under `/xxxmailmanage` in `src/maildrop/app.py`.
- [x] Implement server-side refresh with `httpx.Client(timeout=10)`, bounded preview storage, and status `error` on failures.
- [x] Run `.venv/bin/python -m pytest tests/maildrop/test_xxxmailmanage.py -q`; expected pass.

## Task 4: UI Template and Styling

- [x] Create `xxxmailmanage.html` with batch import textarea, toolbar filters/stats, bulk status buttons, paginated row list, row details, copy buttons, and delete/refresh actions.
- [x] Create `xxxmailmanage.css` with the provided template's gradient shell, white container, compact controls, status chips, row list, and responsive behavior.
- [x] Add `/xxxmailmanage` to the top nav.
- [x] Run `.venv/bin/python -m pytest tests/maildrop/test_xxxmailmanage.py -q`; expected pass and HTML assertions should see Chinese page copy.

## Task 5: Documentation and Full Local Verification

- [x] Update `README.md` with `/xxxmailmanage`, import format, and status meanings.
- [x] Update `docs/maildrop-ops.md` with manager deployment and smoke procedure.
- [x] Update `MAILDROP_MAIN.md` with implementation context.
- [x] Run `.venv/bin/python -m pytest tests/maildrop -q`; expected pass.
- [x] Run `git diff --check`; expected no output.

## Task 6: Deploy and Production Smoke

- [x] Sync code to `/opt/maildrop` with the established `rsync` exclude list.
- [x] Build app image: `ssh emailengine 'cd /opt/maildrop && docker compose -f docker-compose.maildrop.yml build app'`.
- [x] Run migration: `ssh emailengine 'cd /opt/maildrop && docker compose -f docker-compose.maildrop.yml run --rm app alembic upgrade head'`.
- [x] Restart app: `ssh emailengine 'cd /opt/maildrop && docker compose -f docker-compose.maildrop.yml up -d app'`.
- [x] Run `scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22`; expected exit `0`.
- [x] Run a manager smoke over HTTPS: create/import one temporary row into `/xxxmailmanage/import`, mark it `已消耗`, and verify database status is `used`.
- [x] Run `scripts/maildrop-public-smoke.py aiprot.space emailengine 167.71.29.22`; expected exit `0`.
- [x] Commit with `feat: add xxxmailmanage inbox manager`.
