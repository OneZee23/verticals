"""Pictures inside a text (verticals/core/pictures.py, docs/design/bug-reports.md): an agent reads each as `[picture N]` and
every word as it is, a placeholder it keeps is the picture again when it writes the text back, and an excerpt has none. Pure
functions over sample text; the SQL twin of the pattern is exercised by tests/core/test_docs_desk.py."""

from __future__ import annotations

import time

from verticals.core import pictures

JPG = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgICAgMCAgICAwMDAwQGBAQEBAQIBgYFBgkICgoJCAkJCgwPDAoLDgsJCQ0RDQ4PEBAREAoMEhMSEBMPEBAQ" * 20
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
ONE = f"![Picture 1](data:image/jpeg;base64,{JPG})"
TWO = f"![Picture 2](data:image/png;base64,{PNG})"
TAIL = "Verticals 0.4, macOS 27 (arm64)\n\n## App log\n`app: up`"
REPORT = f"I dragged the card to Friday and it jumped back\n\n{ONE}\n{TWO}\n\n{TAIL}"


def test_an_agent_reads_the_words_and_a_placeholder_for_each_picture() -> None:
    read = pictures.for_agent(REPORT)
    assert read == f"I dragged the card to Friday and it jumped back\n\n[picture 1]\n[picture 2]\n\n{TAIL}"
    assert len(REPORT) > 2500 and len(read) < 200, "the base64 is what made it large"


def test_an_outline_of_many_goals_shows_a_picture_unnumbered() -> None:
    assert pictures.for_agent(f"a\n{ONE}\nb\n{TWO}", numbered=False) == "a\n[picture]\nb\n[picture]"


def test_a_text_with_no_picture_is_read_as_it_is() -> None:
    for text in ("", "Words.", "![a web picture](https://example.com/a.png) and [a link](https://example.com)",
                 "![an svg](data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=) is not a picture here",
                 "![](data:image/png;base64,AAAA", "![x]() [picture 1]"):
        assert pictures.for_agent(text) == text
        assert pictures.without_pictures(text) == text


def test_pictures_are_found_anywhere_in_a_line_and_by_any_alt_text() -> None:
    text = "see ![](data:image/gif;base64,R0lGODlhAQABAAAAACw=) here, and ![a longer alt text](data:image/WEBP;base64,UklGRg==)."
    assert pictures.for_agent(text) == "see [picture 1] here, and [picture 2]."
    assert pictures.without_pictures(text) == "see  here, and ."


def test_a_placeholder_the_agent_kept_is_its_picture_again_and_the_words_it_changed_land() -> None:
    read = pictures.for_agent(REPORT)
    edited = read.replace("jumped back", "went back to where it was")
    written = pictures.from_agent(edited, REPORT)
    assert written == REPORT.replace("jumped back", "went back to where it was")
    assert ONE in written and TWO in written
    # Nothing to restore from, or nothing to restore: the text is as it was written.
    assert pictures.from_agent(read, "no pictures here") == read
    assert pictures.from_agent("no placeholder", REPORT) == "no placeholder"


def test_a_placeholder_taken_out_is_a_picture_taken_out_and_one_moved_moves_its_picture() -> None:
    read = pictures.for_agent(REPORT)
    without_first = read.replace("[picture 1]\n", "")
    assert pictures.from_agent(without_first, REPORT) == REPORT.replace(f"{ONE}\n", "")
    swapped = read.replace("[picture 1]\n[picture 2]", "[picture 2]\n[picture 1]")
    assert pictures.from_agent(swapped, REPORT) == REPORT.replace(f"{ONE}\n{TWO}", f"{TWO}\n{ONE}")
    # A number the text has no picture for is only text.
    assert pictures.from_agent("[picture 3] and [picture 0]", REPORT) == "[picture 3] and [picture 0]"


def test_a_preview_has_every_word_and_no_picture() -> None:
    assert pictures.without_pictures(REPORT) == f"I dragged the card to Friday and it jumped back\n\n\n\n\n{TAIL}"


def test_a_text_that_only_looks_like_a_picture_costs_one_pass() -> None:
    started = time.time()
    for text in ("![a](data:image/png;base64," * 30000, "![" * 150000 + "data:image/", "![x](data:image/png;base64," + "A" * 400000):
        assert pictures.for_agent(text) == text
    assert time.time() - started < 5
