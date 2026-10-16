"""
Turns a file you attach (+ menu, paste, or drag into the message box) into
something the AI can use:

* Photos (png, jpg, jpeg, webp, gif, heic*, bmp) -> resized JPEG data URL
  for a Groq vision model, plus a small thumbnail for the chip/bubble.
* PDF -> its text (pypdf). Scanned PDFs with no text layer say so.
* Word .docx -> its text (read straight from the file's XML, no extra library).
* Text and code (txt, md, csv, json, py, js, html, ...) -> the text.

Only the AI request carries the content; chat history stores the file NAMES
(so history and sync stay small).

* HEIC needs pillow-heif; without it HEIC photos are refused politely.
"""

import base64
import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from typing import Optional

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_SIDE = 1568           # plenty for reading text in photos, keeps requests small
MAX_TEXT_CHARS = 60_000         # per document, before it reaches the prompt
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".heic", ".heif"}
TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".ini", ".toml",
            ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".kt", ".c", ".h", ".cpp", ".cs", ".go", ".rs",
            ".rb", ".php", ".swift", ".sql", ".html", ".htm", ".css", ".sh", ".log", ".srt"}


class AttachmentError(Exception):
    pass


@dataclass
class Attachment:
    name: str
    kind: str                        # "image" or "text"
    data_url: str = ""               # images: full-size (resized) JPEG for the AI
    thumb: str = ""                  # images: small preview for the UI
    text: str = ""                   # documents: extracted text
    note: str = ""                   # e.g. "first 60,000 characters"
    pages: Optional[int] = None

    def chip(self) -> dict:
        return {"name": self.name, "kind": self.kind, "thumb": self.thumb,
                "note": f"{self.pages} pages" if self.pages else self.note}


def _image_from_bytes(raw: bytes, name: str) -> Attachment:
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise AttachmentError("Photos need the Pillow package.")
    if name.lower().endswith((".heic", ".heif")):
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            raise AttachmentError("HEIC photos aren't supported here yet \u2014 export it as JPEG first.")
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
    except Exception:
        raise AttachmentError(f"Couldn't open {name} as an image.")
    if img.mode not in ("RGB", "L"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        try:
            bg.paste(img, mask=img.convert("RGBA").split()[-1])
        except Exception:
            bg.paste(img.convert("RGB"))
        img = bg
    img = img.convert("RGB")
    full = img.copy()
    full.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buf = io.BytesIO()
    full.save(buf, "JPEG", quality=85, optimize=True)
    thumb = img.copy()
    thumb.thumbnail((160, 160))
    tbuf = io.BytesIO()
    thumb.save(tbuf, "JPEG", quality=75)
    return Attachment(name=name, kind="image",
                      data_url="data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
                      thumb="data:image/jpeg;base64," + base64.b64encode(tbuf.getvalue()).decode())


def _pdf_text(raw: bytes, name: str) -> Attachment:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise AttachmentError("Reading PDFs needs the pypdf package (pip install pypdf).")
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise AttachmentError(f"{name} is password-protected.")
        parts = []
        for i, page in enumerate(reader.pages):
            t = (page.extract_text() or "").strip()
            if t:
                parts.append(f"[Page {i + 1}]\n{t}")
        text = "\n\n".join(parts)
    except AttachmentError:
        raise
    except Exception as exc:
        raise AttachmentError(f"Couldn't read {name}: {exc}")
    if not text.strip():
        raise AttachmentError(f"{name} has no text layer (it's probably a scan). "
                              "Take a photo or screenshot of the page and attach that instead.")
    return _text_attachment(name, text, pages=len(reader.pages))


def _docx_text(raw: bytes, name: str) -> Attachment:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except Exception:
        raise AttachmentError(f"Couldn't open {name} as a Word document.")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    xml = re.sub(r"<w:br/>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        text = text.replace(a, b)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise AttachmentError(f"{name} looks empty.")
    return _text_attachment(name, text)


def _text_attachment(name: str, text: str, pages: Optional[int] = None) -> Attachment:
    note = ""
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
        note = f"first {MAX_TEXT_CHARS:,} characters"
    return Attachment(name=name, kind="text", text=text, note=note, pages=pages)


def load_bytes(raw: bytes, name: str) -> Attachment:
    if len(raw) > MAX_FILE_BYTES:
        raise AttachmentError(f"{name} is over {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    ext = os.path.splitext(name.lower())[1]
    if ext in IMAGE_EXT:
        return _image_from_bytes(raw, name)
    if ext == ".pdf":
        return _pdf_text(raw, name)
    if ext == ".docx":
        return _docx_text(raw, name)
    if ext in TEXT_EXT or not ext:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("latin-1")
            except Exception:
                raise AttachmentError(f"Couldn't read {name} as text.")
        if "\x00" in text[:2000]:
            raise AttachmentError(f"{name} isn't a text file.")
        return _text_attachment(name, text)
    raise AttachmentError(f"Gink can't read {ext} files yet. Try a photo, PDF, Word (.docx) or text file.")


def load_path(path: str) -> Attachment:
    path = str(path)
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        raise AttachmentError(f"Couldn't open the file: {exc}")
    return load_bytes(raw, os.path.basename(path))


def load_data_url(data_url: str, name: str) -> Attachment:
    """From the chat page (pasted or dropped files)."""
    m = re.match(r"data:([^;,]*)(;base64)?,(.*)", data_url or "", re.S)
    if not m:
        raise AttachmentError("That file couldn't be read.")
    raw = base64.b64decode(m.group(3)) if m.group(2) else m.group(3).encode()
    if not os.path.splitext(name)[1] and m.group(1).startswith("image/"):
        name += "." + m.group(1).split("/")[1].replace("jpeg", "jpg")
    return load_bytes(raw, name)


def build_prompt_text(message: str, attachments) -> str:
    """User message + the text of any attached documents, for the AI."""
    docs = [a for a in attachments if a.kind == "text"]
    if not docs:
        return message
    blocks = []
    for a in docs:
        extra = f" ({a.note})" if a.note else ""
        blocks.append(f'<attached_file name="{a.name}"{extra}>\n{a.text}\n</attached_file>')
    ask = message or "Please read the attached file(s) and summarise the important points."
    return "\n\n".join(blocks) + "\n\n" + ask


def history_text(message: str, attachments) -> str:
    """What gets saved to chat history (names only, not contents)."""
    if not attachments:
        return message
    names = ", ".join(a.name for a in attachments)
    return (message + "\n\n" if message else "") + f"\U0001F4CE {names}"
