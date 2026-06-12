# Maildrop Alias Categories and Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add admin alias categories (`未导出`, `已导出`, `已删除`) and soft-delete actions with production-safe schema migration.

**Architecture:** Store lifecycle state as nullable `aliases.exported_at` and `aliases.deleted_at` timestamps. Admin category filters derive state from those fields, exports set `exported_at`, deletes set `deleted_at` and disable the alias. Deleted aliases keep historical messages, are excluded from normal export, return `403` on public API access, and future incoming mail goes to `unassigned_messages` with reason `alias_deleted`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, SQLite tests, Jinja2, pytest.

---

## Files

- Create `alembic.ini`: Alembic CLI configuration using `src` on `prepend_sys_path`.
- Create `migrations/env.py`: imports `maildrop.models.Base.metadata`, reads `DATABASE_URL`, supports offline and online migrations.
- Create `migrations/versions/20260612_0001_add_alias_export_delete_timestamps.py`: adds nullable `exported_at` and `deleted_at` columns to `aliases`.
- Modify `src/maildrop/models.py`: add `exported_at` and `deleted_at` to `Alias`.
- Modify `src/maildrop/repository.py`: make deleted aliases ingest as `alias_deleted`.
- Modify `src/maildrop/app.py`: add category filtering, soft-delete endpoints, export state updates, and deleted-alias exclusions.
- Modify `src/maildrop/templates/aliases.html`: add category filter tabs, category display, delete buttons, and bulk delete control.
- Modify `tests/maildrop/test_admin.py`: cover category filters, export state, delete, bulk delete, and deleted export exclusions.
- Modify `tests/maildrop/test_repository.py`: cover ingest to deleted alias.
- Create `tests/maildrop/test_migrations.py`: cover Alembic upgrade from a pre-migration schema.
- Modify `README.md`, `docs/maildrop-ops.md`, `MAILDROP_MAIN.md`: document categories, soft-delete behavior, migration/deploy status.

## Task 1: Migration and Model

- [x] Write a failing migration/model test in `tests/maildrop/test_migrations.py` that creates a pre-migration SQLite `aliases` table without lifecycle columns, runs Alembic upgrade to head, and asserts `exported_at` and `deleted_at` exist and existing rows keep nullable values.
- [x] Run `.venv/bin/python -m pytest tests/maildrop/test_migrations.py -q`; expected failure is missing Alembic config or missing lifecycle columns.
- [x] Add Alembic files and the timestamp migration.
- [x] Add `Alias.exported_at` and `Alias.deleted_at` mapped columns in `src/maildrop/models.py`.
- [x] Run `.venv/bin/python -m pytest tests/maildrop/test_migrations.py -q`; expected pass.

## Task 2: Ingest Deleted Alias Behavior

- [x] Add `test_ingest_deleted_alias_goes_to_unassigned` to `tests/maildrop/test_repository.py`: create alias, set `deleted_at`, set `enabled = False`, ingest mail to that prefix, assert result is `unassigned`, reason is `alias_deleted`, and no `Message` is created.
- [x] Run `.venv/bin/python -m pytest tests/maildrop/test_repository.py::test_ingest_deleted_alias_goes_to_unassigned -q`; expected failure because deleted aliases currently use `alias_disabled`.
- [x] Update `ingest_parsed_message()` to check `alias.deleted_at is not None` before `enabled`.
- [x] Run the targeted test; expected pass.

## Task 3: Admin Export State and Filtering

- [x] Add admin tests asserting selected export sets `exported_at` only on selected aliases, export all excludes deleted aliases, and `/admin?category=unexported|exported|deleted|all` shows the expected aliases.
- [x] Run the targeted admin tests; expected failures because category filtering and `exported_at` updates do not exist.
- [x] Update `paged_alias_context()` to accept `category`, filter `Alias.deleted_at`/`Alias.exported_at`, and include `category` in template context.
- [x] Update `admin_aliases()` to accept `category` query param.
- [x] Update export endpoint to select only active non-deleted aliases and set `exported_at = utcnow()` for exported aliases.
- [x] Update `aliases.html` to render category links and category labels.
- [x] Run targeted admin tests; expected pass.

## Task 4: Admin Soft Delete

- [x] Add tests for single delete and bulk delete: delete requires CSRF, sets `deleted_at`, sets `enabled = False`, preserves historical messages, makes public API return `403`, and deleted aliases appear under `category=deleted`.
- [x] Run the targeted delete tests; expected failures because delete endpoints do not exist.
- [x] Add helper to soft-delete aliases idempotently in `src/maildrop/app.py`.
- [x] Add `POST /admin/aliases/{prefix}/delete` and `POST /admin/aliases/delete`.
- [x] Update `aliases.html` with per-row `删除` button and bulk `删除选中` button; hide token rotation for deleted aliases.
- [x] Run targeted delete tests; expected pass.

## Task 5: Documentation and Production Status

- [x] Update `README.md` with lifecycle category behavior.
- [x] Update `docs/maildrop-ops.md` with Alembic upgrade command and soft-delete semantics.
- [x] Update `MAILDROP_MAIN.md` with this feature's current implementation/deployment context.
- [x] Run `.venv/bin/python -m pytest tests/maildrop -q`; expected pass.

## Task 6: Deploy and Verify

- [x] Sync code to `/opt/maildrop` with the established `rsync` exclude list.
- [x] Build the new app image on the server: `ssh emailengine 'cd /opt/maildrop && docker compose -f docker-compose.maildrop.yml build app'`.
- [x] Run migration on the server: `ssh emailengine 'cd /opt/maildrop && docker compose -f docker-compose.maildrop.yml run --rm app alembic upgrade head'`.
- [x] Restart app: `ssh emailengine 'cd /opt/maildrop && docker compose -f docker-compose.maildrop.yml up -d app'`.
- [x] Run `scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22`; expected exit `0`.
- [x] Run `scripts/maildrop-public-smoke.py aiprot.space emailengine 167.71.29.22`; expected exit `0`.
- [x] Run `git diff --check`; expected no output.
- [x] Commit with `feat: add alias categories and soft delete`.
