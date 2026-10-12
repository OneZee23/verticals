-- A deleted goal can be brought back (docs/design/board-undo.md): before `core.goals.delete` removes a subtree it
-- copies the goals, and everything that cascades away with them, into one row here. `core.trash.restore` puts the
-- copy back with the same ids.
--
-- Why a copy and not a `deleted_at` column on `goals`. A soft delete would put `deleted_at IS NULL` into every query
-- that reads goals (the board, search, the tree walks, ideas, the undated list, spans, document links, evidence, the
-- MCP tools): one forgotten filter shows a deleted goal. The copy leaves every read as it is. A deleted goal is gone
-- for all of them, and exists only here.
--
--   root_id      the goal the delete named; the subtree under it is in `rows`.
--   rows         one JSON object with a list per table that holds the subtree's data, each row as `to_jsonb(row)`:
--                `goals`, `goal_evidence`, `due_acknowledgements`, `goal_doc_links`, `comment_threads` and
--                `comment_messages`. Every table with a foreign key to `goals` is named there; a test reads
--                `pg_constraint` and fails when a new one is not.
--   deleted_at   when. Entries older than the retention (`core/trash.py`) are removed by the next delete of the same
--                owner, so nothing runs by itself, the way the idempotency table is swept.
--
-- No trigger: the change feed rings from `goals` itself when the rows come back. Forward-only and safe on a populated
-- database: one new table, no existing row touched.

CREATE TABLE goal_trash (
  id          BIGSERIAL PRIMARY KEY,
  owner       TEXT        NOT NULL,
  root_id     TEXT        NOT NULL,
  deleted_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  rows        JSONB       NOT NULL,

  CONSTRAINT goal_trash_rows_is_object CHECK (jsonb_typeof(rows) = 'object')
);

-- `restore` takes the newest entry for one goal; the sweep removes one owner's old entries.
CREATE INDEX goal_trash_root ON goal_trash (owner, root_id, deleted_at DESC);
CREATE INDEX goal_trash_sweep ON goal_trash (owner, deleted_at);
