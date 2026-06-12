# Maildrop Export Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add admin export for existing aliases as `email latest.txt API URL` lines.

**Architecture:** Because plaintext API tokens are not stored, export generates fresh tokens for selected aliases and replaces their token hashes in the same transaction. The admin UI supports row selection plus an export-all button; both paths require Basic Auth and CSRF and return a plain-text attachment.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Jinja2, pytest.

---

## Files

- Modify `src/maildrop/app.py`: add export endpoint and token rotation helper.
- Modify `src/maildrop/templates/aliases.html`: add row checkboxes, select-all checkbox, and export buttons.
- Modify `src/maildrop/static/admin.css`: style compact export controls.
- Modify `tests/maildrop/test_admin.py`: add selected export and export-all regression tests.
- Modify `README.md`, `docs/maildrop-ops.md`, `MAILDROP_MAIN.md`: document export behavior and token rotation tradeoff.

## Tasks

- [x] Write failing tests for selected export and export-all export.
- [x] Implement endpoint and UI.
- [x] Run targeted and full tests.
- [x] Deploy to `/opt/maildrop` and run production checks.
- [x] Update docs and `MAILDROP_MAIN.md`.
- [x] Commit the feature.
