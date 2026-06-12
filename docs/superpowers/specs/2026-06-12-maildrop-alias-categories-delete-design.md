# Maildrop Alias Categories and Delete Design

## Goal

Add lifecycle categories for mailbox aliases in the admin console:

- `未导出`: alias exists and has never been exported through the admin export action.
- `已导出`: alias exists and has been exported at least once.
- `已删除`: alias has been soft-deleted and is no longer usable for API access or normal export.

Add delete actions before relying on the `已删除` category.

## Scope

This feature applies to registered aliases in the admin alias list. It does not change the existing `未登记邮件` list, except that future mail to a deleted alias should be stored there with a distinct reason.

The first version will not add a restore button. Soft-deleted data remains available in the database so restore can be added later without recovering from backups.

## Data Model

Add nullable timestamp columns to `aliases`:

- `exported_at`: set when an alias is exported by `/admin/aliases/export`.
- `deleted_at`: set when an alias is deleted from admin.

Category is derived from these fields:

- `已删除`: `deleted_at is not null`
- `已导出`: `deleted_at is null and exported_at is not null`
- `未导出`: `deleted_at is null and exported_at is null`

Because production already has data, this must ship with an Alembic migration. Existing aliases start as `未导出` because historical export state was not recorded before this feature.

## Admin Behavior

The alias list gets a category filter with these modes:

- `全部`: all aliases, including deleted aliases.
- `未导出`: active aliases with no `exported_at`.
- `已导出`: active aliases with `exported_at`.
- `已删除`: soft-deleted aliases.

The table shows a category/status column. Deleted aliases should display as deleted and not show normal token rotation or export actions.

Deletion behavior:

- Each active alias row has a `删除` action.
- The existing checkbox selection can also be reused for `删除选中`.
- Delete requires admin Basic Auth and CSRF, like export and token rotation.
- Delete is soft delete: set `deleted_at`, set `enabled = false`, and commit.
- Repeated delete on an already deleted alias is idempotent.
- Deleting an alias does not delete its historical messages.

Export behavior:

- Export selected aliases rotates tokens only for active, not-deleted aliases.
- Export all exports only active, not-deleted aliases.
- Export sets `exported_at` on every alias included in the export.
- Deleted aliases are excluded from export all and cannot be exported by selection.

## API and Ingest Behavior

Public API access:

- A deleted alias must behave like a disabled alias and return `403`.
- Existing token links stop working after deletion because `enabled = false`.

Incoming mail:

- If a recipient prefix matches a soft-deleted alias, store the message in `unassigned_messages`.
- Use reason `alias_deleted`.
- Do not increment the deleted alias message count.

This preserves the operator's ability to see mail arriving for deleted addresses without silently reviving or modifying the alias.

## Migration and Deployment

Introduce Alembic project files if they are not already present:

- `alembic.ini`
- `migrations/env.py`
- `migrations/versions/<revision>_add_alias_export_delete_timestamps.py`

Deployment order:

1. Sync code to `/opt/maildrop`.
2. Run the Alembic migration inside the app environment.
3. Rebuild/restart the app container.
4. Run production checks and public SMTP smoke.

The migration must be safe for existing production rows and should only add nullable columns.

## Tests

Add regression tests for:

- Export selected sets `exported_at` only for exported aliases.
- Export all excludes deleted aliases.
- Admin list category filters return the expected aliases.
- Single delete soft-deletes an alias, disables API access, and preserves messages.
- Bulk delete soft-deletes selected aliases.
- Incoming mail to deleted aliases goes to `unassigned_messages` with reason `alias_deleted`.
- Alembic migration can upgrade an existing schema with aliases.

Keep the existing production check and public smoke tests green.

## Documentation

Update:

- `README.md`: admin categories, delete behavior, and export status.
- `docs/maildrop-ops.md`: soft-delete semantics and migration deployment command.
- `MAILDROP_MAIN.md`: current status and future context.

