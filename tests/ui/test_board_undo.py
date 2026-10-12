"""⌘Z takes back the last change on the board (docs/design/board-undo.md). Fixture F2, the pinned clock (Saturday 8 Aug 2026).

Each scenario makes the change the way a person does, presses the keys (or the notice's Undo) and reads the database, the
board and the field. A change you can see is undone in place and nothing is said; the words of the ones that leave your view
are in `test_field_notice.py`, the movement in `test_board_undo_motion.py`."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone

import psycopg
from playwright.sync_api import Page, expect

from verticals.core import comments as core_comments, goals as core_goals
from tests.ui.conftest import UiSession, activate_column
from tests.ui.views import switch_view
from tests.ui.undo_helpers import (
    ACTION, GRIP, column_ids, expect_no_notice, expect_notice, family, goal, keys, wait_for, write_log, writes,
)

TICK = '[data-goal-id="SYNCOL01"] > .goal-card__row label.checkbox'
TICKED = '[data-goal-id="SYNCOL01"] > .goal-card__row input.checkbox__input'
ORD01_ROW = '[data-goal-id="SYNORD01"] > .goal-card__row'
MONTH_BODY = '[data-vertical="month"] .pattern-vertical-board__body'


def open_menu(page: Page, vertical: str, goal_id: str) -> None:
    activate_column(page, vertical)
    page.click(f'[data-goal-id="{goal_id}"] [data-role=goal-actions-trigger]')
    page.wait_for_selector('[data-role="goal-context-menu"]', timeout=5000)


def board(session: UiSession) -> Page:
    session.page.wait_for_selector('[data-goal-id="SYNDAY01"]', timeout=10000)
    return session.page


def test_a_tick_is_undone_and_redone_in_place(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        ticked = lambda: goal(conn, "SYNCOL01")[4]  # noqa: E731
        session.gestures.click(TICK)
        expect(page.locator(TICKED)).to_be_checked()
        wait_for(page, ticked, True, "the tick is stored")
        wait_for(page, lambda: len(writes(session)), 1, "the tick's answer is logged")

        start = len(session.request_log)
        page.keyboard.press(undo)
        expect(page.locator(TICKED)).not_to_be_checked()
        wait_for(page, ticked, False, "the tick is taken back")
        wait_for(page, lambda: writes(session, start), [("PATCH", "/goals/SYNCOL01", 200)], "one undo is one write")
        expect_no_notice(page)  # the checkbox is in view: nothing to say

        page.keyboard.press(redo)
        expect(page.locator(TICKED)).to_be_checked()
        wait_for(page, ticked, True, "the tick is played again")
        expect_no_notice(page)


def test_a_renamed_title_is_taken_back_and_played_again(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    activate_column(page, "day")
    page.click('[data-goal-id="SYNCOL06"] > [data-cap=reorder]')
    title = '[data-goal-id="SYNCOL06"] [data-cap="edit-title"]'
    page.wait_for_selector(title, timeout=5000)
    page.click(title)
    page.fill(f"{title}:is(textarea)", "Renamed for the history")
    page.press(f"{title}:is(textarea)", "Enter")
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        name = lambda: goal(conn, "SYNCOL06")[5]  # noqa: E731
        wait_for(page, name, "Renamed for the history", "the title is stored")
        page.keyboard.press(undo)
        wait_for(page, name, "Color check orange", "the old title is back")
        expect(page.locator(f'{title}:not(textarea)')).to_contain_text("Color check orange")
        page.keyboard.press(redo)
        wait_for(page, name, "Renamed for the history", "the new title is back")


def test_a_drag_between_periods_goes_back_to_its_place(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    expect(page.locator(ORD01_ROW)).to_be_visible()
    week_before = column_ids(page, "week")
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        where = lambda: goal(conn, "SYNORD01")[1:4]  # noqa: E731
        assert where() == ("week", "2026-08-05", "2026-W32")
        session.gestures.drag(ORD01_ROW, MONTH_BODY, source_position=GRIP, target_position=GRIP)
        page.wait_for_selector('[data-vertical="month"] [data-goal-id="SYNORD01"]', timeout=5000)
        wait_for(page, lambda: where()[0], "month", "the drop is stored")

        page.keyboard.press(undo)
        page.wait_for_selector('[data-vertical="week"] [data-goal-id="SYNORD01"]', timeout=5000)
        wait_for(page, where, ("week", "2026-08-05", "2026-W32"), "the goal is back in its week")
        assert column_ids(page, "week") == week_before, "the goal is back in its slot, not at the end"
        assert page.locator('[data-vertical="month"] [data-goal-id="SYNORD01"]').count() == 0
        expect_no_notice(page)  # both columns are on the screen: it was seen going and coming

        page.keyboard.press(redo)
        page.wait_for_selector('[data-vertical="month"] [data-goal-id="SYNORD01"]', timeout=5000)
        wait_for(page, lambda: where()[0], "month", "the drop is played again")
        expect_no_notice(page)


def test_a_leaf_delete_comes_back_with_its_id_and_a_subtree_with_its_subgoals(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        leaf, tree = family(conn, "SYNCOL03"), family(conn, "SYNDAY01")
        assert len(leaf) == 1 and len(tree) == 4, "SYNDAY01 stands over three subgoals"

        # A goal with nothing under it: a plain DELETE, and Undo brings the same row back.
        start = len(session.request_log)
        open_menu(page, "day", "SYNCOL03")
        page.click('#dropdownPortal [data-action="delete"]')
        wait_for(page, lambda: family(conn, "SYNCOL03"), [], "the leaf is deleted")
        wait_for(page, lambda: writes(session, start), [("DELETE", "/goals/SYNCOL03?cascade=false", 204)], "a plain DELETE")
        expect_notice(page, "Deleted “Color check green”")
        page.click(ACTION)
        wait_for(page, lambda: family(conn, "SYNCOL03"), leaf, "the leaf is back, as it was")
        page.wait_for_selector('[data-vertical="day"] [data-goal-id="SYNCOL03"]', timeout=5000)
        expect_no_notice(page)

        # A goal with subgoals goes with them in one write, with no question, and comes back with them.
        start = len(session.request_log)
        open_menu(page, "day", "SYNDAY01")
        page.click('#dropdownPortal [data-action="delete"]')
        wait_for(page, lambda: family(conn, "SYNDAY01"), [], "the subtree is deleted")
        wait_for(page, lambda: writes(session, start), [("DELETE", "/goals/SYNDAY01?cascade=true", 204)],
                 "one cascading write, no 409 first")
        expect_notice(page, "Deleted “Draft the outline” and 3 subgoals")
        page.click(ACTION)
        wait_for(page, lambda: family(conn, "SYNDAY01"), tree, "the goal and its three subgoals are back under their ids")
        page.wait_for_selector('[data-vertical="day"] [data-goal-id="SYNDAY01"]', timeout=5000)
        expect_no_notice(page)

        # Redo deletes it again, and says so.
        page.keyboard.press(redo)
        wait_for(page, lambda: family(conn, "SYNDAY01"), [], "redo deletes the subtree again")
        expect_notice(page, "Deleted “Draft the outline” and 3 subgoals")
        page.keyboard.press(undo)
        wait_for(page, lambda: family(conn, "SYNDAY01"), tree, "and undo brings it back once more")


def test_a_new_change_after_an_undo_ends_what_could_be_played_again(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        ticked = lambda goal_id: goal(conn, goal_id)[4]  # noqa: E731
        session.gestures.click(TICK)
        wait_for(page, lambda: ticked("SYNCOL01"), True, "SYNCOL01 ticked")
        page.keyboard.press(undo)
        wait_for(page, lambda: ticked("SYNCOL01"), False, "SYNCOL01 taken back")
        session.gestures.click('[data-goal-id="SYNCOL02"] > .goal-card__row label.checkbox')
        wait_for(page, lambda: ticked("SYNCOL02"), True, "SYNCOL02 ticked")
        wait_for(page, lambda: len(writes(session)), 3, "the three writes so far are logged")

        start = len(session.request_log)
        page.keyboard.press(redo)  # nothing to play: the undone tick was dropped by the new one
        page.wait_for_timeout(400)
        assert writes(session, start) == []
        assert ticked("SYNCOL01") is False and ticked("SYNCOL02") is True

        page.keyboard.press(undo)  # back through what was done since, newest first
        wait_for(page, lambda: ticked("SYNCOL02"), False, "SYNCOL02 taken back")
        page.keyboard.press(undo)  # and nothing older is left to take back
        page.wait_for_timeout(400)
        assert ticked("SYNCOL01") is False


def test_the_history_starts_when_the_app_opens(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        session.gestures.click(TICK)
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], True, "the tick is stored")
        page.reload()
        page.wait_for_selector('[data-goal-id="SYNDAY01"]', timeout=10000)
        page.keyboard.press(undo)
        page.wait_for_timeout(400)
        assert goal(conn, "SYNCOL01")[4] is True, "a reloaded page remembers nothing to take back"


def test_under_and_back_out_are_one_step_each(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        parent = lambda: goal(conn, "SYNORD03")[0]  # noqa: E731
        open_menu(page, "week", "SYNORD03")
        page.click('#dropdownPortal [data-move="under"]')
        page.click('[data-role="move-step"] [data-parent-id="SYNSCH01"]')
        wait_for(page, parent, "SYNSCH01", "the goal is under SYNSCH01")
        page.keyboard.press(undo)
        wait_for(page, parent, None, "undo takes it out again")
        page.keyboard.press(redo)
        wait_for(page, parent, "SYNSCH01", "redo puts it under again")


def test_a_task_ticked_in_the_inbox_is_brought_back_by_undo(ui_f2: UiSession) -> None:
    """The Inbox is a place the board's changes are made from too: the card leaves it when ticked, which is said, and undo
    puts it back."""
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        loose = core_goals.create(conn, owner="t1", title="SYN Inbox tick").goal.id
        done = lambda: goal(conn, loose)[4]  # noqa: E731
        page.clock.set_fixed_time(datetime.now(timezone.utc))
        page.reload()
        switch_view(page, "inbox")
        card = f'[data-role="inbox-card"][data-goal-id="{loose}"]'
        expect(page.locator(card)).to_be_visible(timeout=10000)

        page.locator(f"{card} label.goal-affordance").click()
        expect(page.locator(card)).to_have_count(0)
        wait_for(page, done, True, "the task is ticked")
        expect_notice(page, "Completed “SYN Inbox tick”")  # it left the Inbox, so it is said

        page.keyboard.press(undo)
        wait_for(page, done, False, "undo opens it again")
        expect(page.locator(card)).to_be_visible(timeout=5000)
        expect_no_notice(page)  # it is back in view

        page.keyboard.press(redo)
        wait_for(page, done, True, "redo ticks it again")
        expect(page.locator(card)).to_have_count(0)


def test_a_repeat_rule_is_taken_back_and_set_again(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    card = '[data-goal-id="SYNCOL04"]'
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        rule = lambda: conn.execute("SELECT repeat_rule FROM goals WHERE id = 'SYNCOL04'").fetchone()[0]  # noqa: E731
        assert rule() is None
        session.gestures.click(f'{card} [data-role="goal-actions-trigger"]')
        session.gestures.click('[data-role="goal-actions-menu"] [data-action="repeat"] button')
        session.gestures.click('[data-role="repeat-menu"] button[role="menuitem"]:has-text("Daily")')
        wait_for(page, rule, {"frequency": "daily", "interval": 1}, "the rule is stored")
        page.wait_for_selector(f'{card} [data-role="repeat-indicator"]', timeout=5000)

        page.keyboard.press(undo)
        wait_for(page, rule, None, "undo takes the rule away")
        expect(page.locator(f'{card} [data-role="repeat-indicator"]')).to_have_count(0)
        page.keyboard.press(redo)
        wait_for(page, rule, {"frequency": "daily", "interval": 1}, "redo sets it again")


def repeating_tick(session: UiSession) -> tuple[Page, psycopg.Connection, Callable[[], list[tuple]]]:
    """SYNCOL01 set to repeat daily (what the menu's Repeat does), then ticked the way a person does. Returns the page, a
    connection and a probe for the series as stored: (id, index, done) for every occurrence, in order."""
    conn = psycopg.connect(session.backend.dsn, autocommit=True)
    core_goals.update(conn, owner="t1", id="SYNCOL01", repeat={"frequency": "daily", "interval": 1})
    session.page.reload()
    page = board(session)
    series = lambda: conn.execute(  # noqa: E731
        "SELECT id, repeat_index, done_at IS NOT NULL FROM goals WHERE repeat_series_id = 'SYNCOL01' ORDER BY repeat_index"
    ).fetchall()
    session.gestures.click(TICK)
    wait_for(page, lambda: [row[1:] for row in series()], [(0, True), (1, False)], "the tick made the next occurrence")
    # The database has the tick before the page has logged its answer: a scenario that counts the writes after this waits for it.
    wait_for(page, lambda: len(writes(session)), 1, "the tick's answer is logged")
    return page, conn, series


def test_the_tick_of_a_repeating_goal_is_undone_with_the_occurrence_it_made(ui_f2: UiSession) -> None:
    session = ui_f2
    page, conn, series = repeating_tick(session)
    with conn:
        undo, redo = keys(page)
        first, made = series()[0][0], series()[1][0]
        assert first == "SYNCOL01"

        page.keyboard.press(undo)
        wait_for(page, series, [("SYNCOL01", 0, False)], "undo reopens the goal and takes the occurrence it made away")
        expect(page.locator(TICKED)).not_to_be_checked()
        expect(page.locator(f'[data-goal-id="{made}"]')).to_have_count(0)

        # ⇧⌘Z ticks it again, and the tick makes the occurrence again: a new goal, so a new id.
        page.keyboard.press(redo)
        wait_for(page, lambda: [row[1:] for row in series()], [(0, True), (1, False)], "redo ticks it and makes the occurrence")
        again = series()[1][0]
        assert again != made, "the occurrence is made again, not brought back"

        # The step follows the occurrence the tick made last: undo takes that one away.
        page.keyboard.press(undo)
        wait_for(page, series, [("SYNCOL01", 0, False)], "the second undo takes the second occurrence away")


def undone_and_looked_at(session: UiSession, page: Page, since: int, occurrence: str, last_read: str) -> None:
    """Waits until the undo has looked at the occurrence it may take back (the last read it makes is `last_read`), and a beat
    more: a write that was going to follow would be on its way by then. What the tests check is that none did."""
    wait_for(
        page, lambda: any(r["method"] == "GET" and r["url"].split("?")[0].endswith(f"/goals/{occurrence}{last_read}") for r in session.request_log[since:]),
        True, "the undo has looked at the occurrence",
    )
    page.wait_for_timeout(500)


def test_an_occurrence_someone_touched_stays_when_the_tick_is_undone(ui_f2: UiSession) -> None:
    session = ui_f2
    page, conn, series = repeating_tick(session)
    with conn:
        undo, redo = keys(page)
        made = series()[1][0]
        core_goals.update(conn, owner="t1", id=made, title="SYN occurrence renamed")  # touched since the tick
        start = len(session.request_log)

        page.keyboard.press(undo)
        undone_and_looked_at(session, page, start, made, "")
        assert [(row[1], row[2]) for row in series()] == [(0, False), (1, False)], "the goal is reopened, and nothing else"
        assert series()[1][0] == made, "the occurrence somebody wrote to is left alone"
        assert conn.execute("SELECT title FROM goals WHERE id = %s", (made,)).fetchone() == ("SYN occurrence renamed",)
        assert [w[0] for w in writes(session, start)] == ["PATCH"], (
            f"one write: the reopening, and no delete: {write_log(session, start)}"
        )

        # Played again, the tick finds that occurrence there, so it made nothing and the next undo takes nothing.
        played = len(session.request_log)
        page.keyboard.press(redo)
        wait_for(page, lambda: [(row[1], row[2]) for row in series()], [(0, True), (1, False)], "the tick is played again")
        # The redo's own write is logged by the page after the database has it; counted from before it, it would be the undo's.
        wait_for(page, lambda: [w[0] for w in writes(session, played)], ["PATCH"], "the redo's own write is logged")
        assert [row[0] for row in series()][1] == made and len(series()) == 2, "no second occurrence"
        start = len(session.request_log)
        page.keyboard.press(undo)
        wait_for(page, lambda: [(row[1], row[2]) for row in series()], [(0, False), (1, False)], "the goal is reopened again")
        page.wait_for_timeout(500)
        assert series()[1][0] == made, "the occurrence the tick did not make is not the tick's to take"
        assert [w[0] for w in writes(session, start)] == ["PATCH"], (
            f"the second undo is one write too: {write_log(session, start)}"
        )
        assert not any(r["method"] == "GET" and r["url"].split("?")[0].endswith(f"/goals/{made}") for r in session.request_log[start:]), (
            "it did not even look at an occurrence it did not make"
        )


def test_an_occurrence_with_a_comment_on_it_stays_too(ui_f2: UiSession) -> None:
    session = ui_f2
    page, conn, series = repeating_tick(session)
    with conn:
        undo, _ = keys(page)
        made = series()[1][0]
        core_comments.create_thread(conn, owner="t1", goal_id=made, body="SYN a word on it", author="human")
        start = len(session.request_log)

        page.keyboard.press(undo)
        undone_and_looked_at(session, page, start, made, "/comments")
        assert [(row[1], row[2]) for row in series()] == [(0, False), (1, False)], "the goal is reopened, and nothing else"
        assert series()[1][0] == made, "a comment is a touch"
        assert [w[0] for w in writes(session, start)] == ["PATCH"], (
            f"one write: the reopening, and no delete: {write_log(session, start)}"
        )


def test_the_tick_of_a_repeating_goal_with_steps_takes_back_the_steps_it_brought(ui_f2: UiSession) -> None:
    """A goal with steps repeats, and its next time comes with the steps (docs/design/goal-menu.md): they are the tick's own
    making, so undo takes the occurrence back with them. A step written to since is a touch, and the occurrence stays."""
    session = ui_f2
    page = board(session)
    box = '[data-goal-id="SYNDAY01"] > .goal-card__row [data-role="goal-affordance"]'
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        core_goals.update(conn, owner="t1", id="SYNDAY01", repeat={"frequency": "daily", "interval": 1})
        page.reload()
        page = board(session)
        undo, redo = keys(page)
        series = lambda: conn.execute(  # noqa: E731
            "SELECT id, repeat_index, done_at IS NOT NULL FROM goals WHERE repeat_series_id = 'SYNDAY01' ORDER BY repeat_index"
        ).fetchall()
        steps = lambda occurrence: [row[0] for row in conn.execute(  # noqa: E731
            "SELECT title FROM goals WHERE parent_id = %s ORDER BY position", (occurrence,)).fetchall()]

        session.gestures.click(box)
        wait_for(page, lambda: [row[1:] for row in series()], [(0, True), (1, False)], "the tick made the next occurrence")
        made = series()[1][0]
        assert steps(made) == ["Collect the sources", "Name the argument", "Cut the first pass"]
        wait_for(page, lambda: len(writes(session)), 1, "the tick's answer is logged")

        before_undo = len(session.request_log)
        page.keyboard.press(undo)
        wait_for(page, series, [("SYNDAY01", 0, False)], "undo reopens the goal and takes the occurrence it made away")
        assert steps(made) == [], "its steps went with it"
        # The database shows the undo before the page has logged its answers; count the redo's writes only after them.
        wait_for(page, lambda: sorted(w[0] for w in writes(session, before_undo)), ["DELETE", "PATCH"], "the undo's own writes are logged")

        played = len(session.request_log)
        page.keyboard.press(redo)
        wait_for(page, lambda: [row[1:] for row in series()], [(0, True), (1, False)], "redo makes the occurrence again")
        wait_for(page, lambda: [w[0] for w in writes(session, played)], ["PATCH"], "the redo's own write is logged")
        again = series()[1][0]
        first_step = conn.execute("SELECT id FROM goals WHERE parent_id = %s ORDER BY position LIMIT 1", (again,)).fetchone()[0]
        core_goals.update(conn, owner="t1", id=first_step, title="SYN a step renamed")  # touched since the tick
        start = len(session.request_log)

        page.keyboard.press(undo)
        undone_and_looked_at(session, page, start, again, "")
        assert [(row[1], row[2]) for row in series()] == [(0, False), (1, False)], "the goal is reopened, and nothing else"
        assert series()[1][0] == again and steps(again)[0] == "SYN a step renamed", "a step written to keeps the occurrence"
        assert [w[0] for w in writes(session, start)] == ["PATCH"], f"no delete: {write_log(session, start)}"


def test_a_move_of_a_goal_with_subgoals_is_taken_back_with_the_subgoals_in_their_order(ui_f2: UiSession) -> None:
    """The subgoals nested in a card travel with it (D109) and come back in the order they were drawn in, the goal in its
    slot, the column as it was. Ids are what the server once numbered them by, so the drawn order is set against them."""
    session = ui_f2
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        parent = core_goals.create(
            conn, owner="t1", title="SYN order parent", vertical="day", anchor_date=date(2026, 8, 8), before_id="SYNCOL03"
        ).goal
        kids = [
            core_goals.create(
                conn, owner="t1", title=f"SYN order kid {n}", parent_id=parent.id, vertical="day", anchor_date=date(2026, 8, 8)
            ).goal
            for n in range(4)
        ]
        drawn = [kid.id for kid in sorted(kids, key=lambda kid: kid.id, reverse=True)]
        for place, kid_id in enumerate(drawn):
            conn.execute("UPDATE goals SET position = %s WHERE id = %s", (90_000 + 1024 * place, kid_id))
        kid_order = lambda: [  # noqa: E731
            row[0] for row in conn.execute("SELECT id FROM goals WHERE parent_id = %s ORDER BY position", (parent.id,)).fetchall()
        ]
        day = lambda: conn.execute("SELECT anchor_date::text FROM goals WHERE id = %s", (parent.id,)).fetchone()[0]  # noqa: E731
        assert kid_order() == drawn

        session.page.reload()
        page = board(session)
        undo, redo = keys(page)
        column_before = column_ids(page, "day")
        assert column_before[column_before.index(parent.id) + 1:][:4] == drawn, "the card draws the subgoals in that order"

        open_menu(page, "day", parent.id)
        page.click('#dropdownPortal [data-move="tomorrow"]')
        wait_for(page, day, "2026-08-09", "the goal and its subgoals have moved to tomorrow")
        wait_for(page, lambda: [row[0] for row in conn.execute("SELECT anchor_date::text FROM goals WHERE parent_id = %s", (parent.id,)).fetchall()], ["2026-08-09"] * 4, "the subgoals went with it")
        assert kid_order() == drawn, "moving the family does not shuffle the subgoals"

        page.keyboard.press(undo)
        wait_for(page, day, "2026-08-08", "undo brings the goal back to its day")
        wait_for(page, lambda: [row[0] for row in conn.execute("SELECT anchor_date::text FROM goals WHERE parent_id = %s", (parent.id,)).fetchall()], ["2026-08-08"] * 4, "the subgoals came back with it")
        assert kid_order() == drawn, "the subgoals are back in their order"
        wait_for(page, lambda: column_ids(page, "day"), column_before, "the column is as it was: the goal in its slot, the subgoals under it")

        page.keyboard.press(redo)
        wait_for(page, day, "2026-08-09", "redo moves the family again")
        assert kid_order() == drawn, "and keeps their order again"


def test_a_goal_you_add_is_taken_away_by_undo_and_comes_back_under_its_id_by_redo(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    add = '[data-vertical="day"] [data-cap=create-goal]'
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        made = lambda: conn.execute("SELECT id FROM goals WHERE title = 'SYN undo made'").fetchall()  # noqa: E731
        activate_column(page, "day")
        page.click(add)
        editor = f'{add} [data-role="column-add-editor"]'
        page.wait_for_selector(editor, timeout=5000)
        page.fill(editor, "SYN undo made")
        page.press(editor, "Enter")
        wait_for(page, lambda: len(made()), 1, "the goal is made")
        (goal_id,) = made()[0]
        page.wait_for_selector(f'[data-vertical="day"] [data-goal-id="{goal_id}"]', timeout=5000)
        expect_no_notice(page)  # it is in view

        page.keyboard.press(undo)
        wait_for(page, made, [], "undo takes the goal away")
        expect(page.locator(f'[data-goal-id="{goal_id}"]')).to_have_count(0)
        expect_notice(page, "Removed “SYN undo made”")  # it left the view, and Redo is at hand
        expect(page.locator(ACTION)).to_have_text("Redo")

        page.click(ACTION)
        wait_for(page, made, [(goal_id,)], "Redo brings it back under the same id")
        page.wait_for_selector(f'[data-vertical="day"] [data-goal-id="{goal_id}"]', timeout=5000)
        expect_no_notice(page)


def test_words_written_in_the_inbox_are_taken_back_and_put_again(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    page.clock.set_fixed_time(datetime.now(timezone.utc))
    page.reload()
    switch_view(page, "inbox")
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        made = lambda: conn.execute("SELECT id FROM goals WHERE title = 'SYN written in the Inbox'").fetchall()  # noqa: E731
        field = '[data-cap="search-input"] textarea'
        page.locator(field).fill("SYN written in the Inbox")
        page.locator(field).press("Enter")
        wait_for(page, lambda: len(made()), 1, "the words are a goal")
        (goal_id,) = made()[0]
        card = f'[data-role="inbox-card"][data-goal-id="{goal_id}"]'
        expect(page.locator(card)).to_be_visible(timeout=5000)
        page.locator(field).blur()  # the field is the field's own; the keys are the board's

        page.keyboard.press(undo)
        wait_for(page, made, [], "undo takes the card away")
        expect(page.locator(card)).to_have_count(0)
        page.keyboard.press(redo)
        wait_for(page, made, [(goal_id,)], "redo brings it back under the same id")
        expect(page.locator(card)).to_be_visible(timeout=5000)


def test_several_undos_in_a_row_go_back_through_the_steps_in_order(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    ids = ["SYNCOL01", "SYNCOL02", "SYNCOL03"]
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        done = lambda: [goal(conn, i)[4] for i in ids]  # noqa: E731
        for goal_id in ids:
            session.gestures.click(f'[data-goal-id="{goal_id}"] > .goal-card__row label.checkbox')
        wait_for(page, done, [True, True, True], "three ticks are stored")
        for _ in ids:  # pressed one after the other without waiting: each waits its turn
            page.keyboard.press(undo)
        wait_for(page, done, [False, False, False], "three undos take the three ticks back")
        for _ in ids:
            page.keyboard.press(redo)
        wait_for(page, done, [True, True, True], "three redos play them again")


def test_the_keys_wait_while_a_goal_is_in_the_hand(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        ticked = lambda: goal(conn, "SYNCOL01")[4]  # noqa: E731
        session.gestures.click(TICK)
        wait_for(page, ticked, True, "the tick is stored")
        box = page.locator(ORD01_ROW).bounding_box()
        assert box is not None
        page.mouse.move(box["x"] + GRIP["x"], box["y"] + GRIP["y"])
        page.mouse.down()
        page.mouse.move(box["x"] + GRIP["x"] + 30, box["y"] + GRIP["y"] + 20, steps=4)
        expect(page.locator('[data-role="drag-overlay"]')).to_have_count(1)
        page.keyboard.press(undo)  # a goal is in the hand: it lands first
        page.wait_for_timeout(400)
        assert ticked() is True
        page.keyboard.press("Escape")  # the drag is cancelled, the goal goes back, the hand is empty
        page.mouse.up()
        page.wait_for_timeout(600)
        page.keyboard.press(undo)
        wait_for(page, ticked, False, "with the hand empty the keys work again")


def test_a_step_whose_goal_is_gone_is_told_and_let_go(ui_f2: UiSession) -> None:
    session = ui_f2
    session.expects_network_failures = True  # the goal is deleted behind the page's back: its 404 is the subject
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        session.gestures.click('[data-goal-id="SYNCOL03"] > .goal-card__row label.checkbox')
        wait_for(page, lambda: goal(conn, "SYNCOL03")[4], True, "the tick is stored")
        conn.execute("DELETE FROM goals WHERE id = 'SYNCOL03'")
        page.keyboard.press(undo)
        expect(page.locator(".toast-stack .toast__text", has_text="is gone, so this can’t be taken back")).to_have_text(
            "“Color check green” is gone, so this can’t be taken back.", timeout=5000
        )
        page.keyboard.press(undo)  # the step is gone from the history: nothing older is touched
        page.wait_for_timeout(400)
        assert goal(conn, "SYNCOL02")[4] is False


def test_a_reorder_inside_a_column_goes_back_to_its_slot(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    activate_column(page, "week")
    first, fourth = '[data-goal-id="SYNORD01"] > [data-cap="reorder"]', '[data-goal-id="SYNORD04"] > [data-cap="reorder"]'
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        order = lambda: [  # noqa: E731
            r[0] for r in conn.execute(
                "SELECT id FROM goals WHERE id IN ('SYNORD01','SYNORD02','SYNORD03','SYNORD04') ORDER BY position, id"
            ).fetchall()
        ]
        was = ["SYNORD01", "SYNORD02", "SYNORD03", "SYNORD04"]
        assert order() == was
        a, b = page.locator(first).bounding_box(), page.locator(fourth).bounding_box()
        assert a is not None and b is not None
        sx, sy = a["x"] + GRIP["x"], a["y"] + GRIP["y"]
        tx, ty = b["x"] + min(GRIP["x"], b["width"] * 0.45), b["y"] + b["height"] * 0.15
        page.mouse.move(sx, sy)
        page.mouse.down()
        page.mouse.move(sx + 8, sy)
        page.wait_for_timeout(50)
        page.mouse.move((sx + tx) / 2, (sy + ty) / 2, steps=5)
        page.mouse.move(tx, ty, steps=5)
        page.wait_for_timeout(50)
        page.mouse.up()
        wait_for(page, lambda: order()[0], "SYNORD02", "the goal has left the first slot")
        moved = order()
        assert moved != was and moved.index("SYNORD01") > 0

        page.keyboard.press(undo)
        wait_for(page, order, was, "undo puts it back first")
        assert [i for i in column_ids(page, "week") if i in was] == was
        expect_no_notice(page)
        page.keyboard.press(redo)
        wait_for(page, order, moved, "redo puts it where the drop left it")
        assert [i for i in column_ids(page, "week") if i in was] == moved


def test_undo_sets_back_only_what_the_step_changed(ui_f2: UiSession) -> None:
    """The agent (or a second window) renames a goal after you ticked it: taking your tick back leaves its new title alone."""
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        session.gestures.click(TICK)
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], True, "the tick is stored")
        conn.execute("UPDATE goals SET title = 'Renamed by someone else' WHERE id = 'SYNCOL01'")
        expect(page.locator('[data-goal-id="SYNCOL01"] .goal-card__title-text').first).to_contain_text("Renamed by someone else", timeout=8000)

        page.keyboard.press(undo)
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "the tick is taken back")
        assert goal(conn, "SYNCOL01")[5] == "Renamed by someone else", "the other change is left as it is"
        page.keyboard.press(redo)
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], True, "and played again")
        assert goal(conn, "SYNCOL01")[5] == "Renamed by someone else"
