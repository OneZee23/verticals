-- Sources (docs/design/sources.md): a source is a document under `sources/`, and the app checks it every hour with no
-- model. The check itself lives in the document (a fenced JSON block, `core/source_checks.py`); this table keeps only
-- what the timer learns about it, one row per source document, gone with it.
--
--   ran_hash        the hash of the check that gave the last answer. A check edited since then is a new check: the old
--                   answer says nothing about it and the failures start again.
--   approved_hash   the hash of the check the owner pressed Approve on. An address, an MCP tool, a command or a file is
--                   run only while it equals the hash of the check in the document right now, so any change pauses the
--                   source until the owner approves the new text (a host-name lookup needs none). Only the HTTP route
--                   writes it, never an MCP tool.
--   checked_at, ok, detail, value, ms   the last answer: when, whether it passed, one printable line of why, the number
--                   worth showing, how long it took.
--   failures, failing_since, last_failure_at   the two-failures rule. A source turns red on its second failure in a row,
--                   at least five minutes after the first; `failing_since` is the first of them ("not answering since").
--   next_check_at   when to look next: an hour after an answer, five minutes after a first failure.
--   leased_until    set while a pass is running the check, so two passes never run one check twice; a pass that dies
--                   leaves a lease that runs out by itself.
--
-- No colour is stored. Red, grey and green are worked out from these columns and the clock at read time, so a Mac that
-- was asleep shows grey ("not checked since"), never a red it did not earn.
--
-- `docs_id_owner_unique` (014) is what the composite foreign key needs, as for `doc_revisions`: a state row cannot
-- belong to another owner than its document.

CREATE TABLE source_state (
  doc_id           TEXT NOT NULL PRIMARY KEY,
  owner            TEXT NOT NULL,
  ran_hash         TEXT,
  approved_hash    TEXT,
  approved_at      TIMESTAMPTZ,
  checked_at       TIMESTAMPTZ,
  ok               BOOLEAN,
  detail           TEXT NOT NULL DEFAULT '',
  value            DOUBLE PRECISION,
  ms               INTEGER,
  failures         INTEGER NOT NULL DEFAULT 0,
  failing_since    TIMESTAMPTZ,
  last_failure_at  TIMESTAMPTZ,
  next_check_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  leased_until     TIMESTAMPTZ,

  CONSTRAINT source_state_failures_not_negative CHECK (failures >= 0),
  FOREIGN KEY (doc_id, owner) REFERENCES docs (id, owner) ON DELETE CASCADE
);

-- The change feed (012): a new answer reaches the open app the way a board write does.
CREATE TRIGGER source_state_change_feed
AFTER INSERT OR UPDATE OR DELETE ON source_state
FOR EACH ROW EXECUTE FUNCTION notify_goals_changed();
