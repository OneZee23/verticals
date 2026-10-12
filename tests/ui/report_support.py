"""What the report scenarios share (docs/design/bug-reports.md): sample pictures made here, and the ways a picture reaches the
page the way a person's hand sends one: dropped on the window, or pasted into the field. Sample data only: the pictures are
small coloured PNGs this file draws, and nothing in them is real."""

from __future__ import annotations

import base64
import struct
import zlib

from playwright.sync_api import Page

FIELD = '[data-cap="search-input"] textarea'
SHAPE = ".circle-field__shape"
ITEM = '[data-role="field-picture"]'
PIC = f"{ITEM} .field-pictures__pic"
ANSWER = '[data-role="circle-answer"]'
STACK_GAP = 8
PICTURE_HEIGHT = 56


def png(width: int, height: int, seed: int = 0) -> bytes:
    """A PNG of `width` x `height`: a diagonal wash of colour, different for each `seed`, so a picture has something in it."""
    rows = b"".join(
        b"\x00" + bytes(
            channel
            for x in range(width)
            for channel in ((x * 255 // width + seed * 53) % 256, (y * 255 // height + seed * 29) % 256, (255 - (x + y) * 255 // (width + height) + seed * 71) % 256)
        )
        for y in range(height)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


def file(name: str, width: int = 160, height: int = 100, seed: int = 0) -> dict:
    """A picture as the page's `File` is made from it: a name, a type and the bytes in base64."""
    return {"name": name, "type": "image/png", "b64": base64.b64encode(png(width, height, seed)).decode()}


def files(count: int, width: int = 160, height: int = 100) -> list[dict]:
    return [file(f"picture-{n + 1}.png", width, height, seed=n) for n in range(count)]


def text_file(name: str = "notes.txt") -> dict:
    return {"name": name, "type": "text/plain", "b64": base64.b64encode(b"nothing to see").decode()}


_DATA = """
const data = new DataTransfer()
for (const f of files) {
  const bytes = Uint8Array.from(atob(f.b64), (c) => c.charCodeAt(0))
  data.items.add(new File([bytes], f.name, { type: f.type }))
}
"""

_DRAG = f"""({{ files, types, x, y }}) => {{
  {_DATA}
  const target = document.elementFromPoint(x, y) || document.body
  const taken = []
  for (const type of types) {{
    const event = new DragEvent(type, {{ dataTransfer: data, bubbles: true, cancelable: true, clientX: x, clientY: y }})
    taken.push(!target.dispatchEvent(event))  // true when the page took it (kept the browser from opening the file)
  }}
  return taken
}}"""

_PASTE = f"""({{ files, text }}) => {{
  {_DATA}
  if (text) data.setData('text/plain', text)
  const field = document.querySelector('{FIELD}')
  field.focus()
  return !field.dispatchEvent(new ClipboardEvent('paste', {{ clipboardData: data, bubbles: true, cancelable: true }}))
}}"""


def drag(page: Page, picked: list[dict], types: list[str], at: tuple[float, float] = (700, 300)) -> list[bool]:
    """The events of a drag of files over the window, in order; what each returns is whether the page took it."""
    return page.evaluate(_DRAG, {"files": picked, "types": types, "x": at[0], "y": at[1]})


def drop(page: Page, picked: list[dict], at: tuple[float, float] = (700, 300)) -> bool:
    """Files let go on the window: enter, over, drop. True when the page took the drop."""
    return drag(page, picked, ["dragenter", "dragover", "drop"], at)[-1]


def paste(page: Page, picked: list[dict], text: str = "") -> bool:
    """The field pasted into, with these files (and these words) on the clipboard. True when the page took the paste."""
    return page.evaluate(_PASTE, {"files": picked, "text": text})


def box(page: Page, selector: str, nth: int = 0) -> dict:
    found = page.locator(selector).nth(nth).bounding_box()
    assert found is not None, selector
    return found
