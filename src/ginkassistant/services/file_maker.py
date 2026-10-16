"""
Gink makes real files: "make this a PDF", "create a Word CV", "put the
budget in an Excel sheet".

    make_file(kind, title, content="", rows=None) -> MadeFile

kind: pdf | docx | xlsx | csv | md | html | txt
  * documents (pdf/docx/html/md/txt) take `content` written in Markdown
    (headings, **bold**, lists, tables)
  * spreadsheets (xlsx/csv) take `rows` -- a list of lists, first row = headers
    (or a Markdown table in `content`)

Pure-Python libraries only, so it works on Android too: fpdf2 (PDF) and
openpyxl (Excel). Word files are written directly as Office Open XML (no
python-docx, which needs lxml). PDFs use a Unicode font found on the device
so accents and non-Latin scripts print; without one they fall back to a
built-in font with characters it can't show replaced.

Files go to the app's data folder (files/); the chat shows a card with
Open and Save as...
"""

import csv
import html as _html
import io
import os
import re
import time
import zipfile
from dataclasses import dataclass
from typing import List, Optional

KINDS = {"pdf", "docx", "xlsx", "csv", "md", "html", "txt", "png", "jpg"}
MIME = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "text/csv",
        "md": "text/markdown", "html": "text/html", "txt": "text/plain", "png": "image/png", "jpg": "image/jpeg"}
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",          # macOS
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/system/fonts/NotoSans-Regular.ttf", "/system/fonts/Roboto-Regular.ttf",   # Android
    "C:\\Windows\\Fonts\\arial.ttf", "C:\\Windows\\Fonts\\segoeui.ttf",          # Windows
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",                            # Linux
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]


class FileMakerError(Exception):
    pass


@dataclass
class MadeFile:
    path: str
    name: str
    kind: str
    size: int

    def card_markdown(self) -> str:
        """Markdown the chat page turns into a file card."""
        icon = {"pdf": "\U0001F4D5", "docx": "\U0001F4C4", "xlsx": "\U0001F4CA", "csv": "\U0001F4CA",
                "png": "\U0001F5BC\ufe0f", "jpg": "\U0001F5BC\ufe0f"}.get(self.kind, "\U0001F4C3")
        from urllib.parse import quote
        return f"[{icon} {self.name} \u00b7 {human_size(self.size)}](gink://file/{quote(self.name)})"


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} MB"


def safe_name(title: str, kind: str) -> str:
    base = re.sub(r"[^\w\- ]+", "", title or "Gink file", flags=re.UNICODE).strip()[:60] or "Gink file"
    return f"{base}.{kind}"


def unique_path(folder: str, name: str) -> str:
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(name)
    path, n = os.path.join(folder, name), 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{stem} ({n}){ext}")
        n += 1
    return path


# ---------------------------------------------------------------- markdown helpers
def md_to_html_body(md: str) -> str:
    import markdown
    return markdown.markdown(md or "", extensions=["tables", "fenced_code", "sane_lists"])


def md_table_rows(md: str) -> List[List[str]]:
    rows = []
    for line in (md or "").splitlines():
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            rows.append(cells)
    return rows


def _cell(v):
    """Numbers stay numbers in spreadsheets ("1 250" / "1,250.50" / "15%")."""
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    t = s.replace("\u202f", "").replace(" ", "").replace(",", "")
    try:
        if t.endswith("%"):
            return float(t[:-1]) / 100
        return int(t) if re.fullmatch(r"-?\d+", t) else float(t) if re.fullmatch(r"-?\d*\.\d+", t) else s
    except ValueError:
        return s


# ---------------------------------------------------------------- PDF
def _find_font() -> Optional[str]:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def make_pdf(path: str, title: str, md: str) -> None:
    from fpdf import FPDF
    pdf = FPDF(format="A4")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_title(title or "Gink document")
    pdf.set_creator("Gink Assistant")
    font = _find_font()
    family = "Helvetica"
    if font:
        try:
            pdf.add_font("GinkSans", "", font)
            pdf.add_font("GinkSans", "B", font)
            pdf.add_font("GinkSans", "I", font)
            pdf.add_font("GinkSans", "BI", font)
            family = "GinkSans"
        except Exception:
            family = "Helvetica"
    pdf.add_page()
    pdf.set_font(family, size=11)
    body = md_to_html_body(md)
    if title and not re.match(r"\s*<h1", body):
        body = f"<h1>{_html.escape(title)}</h1>" + body
    if family == "Helvetica":                  # built-in font: Latin-1 only
        body = (body.replace("\u2014", "-").replace("\u2013", "-").replace("\u2019", "'").replace("\u2018", "'")
                .replace("\u201c", '"').replace("\u201d", '"').replace("\u2026", "...").replace("\u2022", "-"))
        body = body.encode("latin-1", "replace").decode("latin-1")
    from fpdf.fonts import FontFace
    dark, green = (28, 33, 29), (63, 130, 18)
    styles = {"h1": FontFace(color=dark, size_pt=22, emphasis="BOLD"),
              "h2": FontFace(color=green, size_pt=15, emphasis="BOLD"),
              "h3": FontFace(color=dark, size_pt=12.5, emphasis="BOLD"),
              "a": FontFace(color=green), "code": FontFace(color=(90, 96, 90))}
    try:
        pdf.write_html(body, font_family=family, tag_styles=styles, li_prefix_color=green,
                       table_line_separators=True)
    except TypeError:                          # older fpdf2 without these options
        pdf.write_html(body, font_family=family)
    pdf.output(path)


# ---------------------------------------------------------------- Word (.docx, written directly)
def _docx_runs(text: str) -> str:
    """**bold**, *italic*, `code` -> Word runs."""
    out = []
    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)", text):
        if not part:
            continue
        props = ""
        if part.startswith("**") and part.endswith("**"):
            part, props = part[2:-2], "<w:b/>"
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            part, props = part[1:-1], "<w:i/>"
        elif part.startswith("`") and part.endswith("`"):
            part, props = part[1:-1], '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>'
        part = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", part)
        out.append(f'<w:r>{"<w:rPr>" + props + "</w:rPr>" if props else ""}'
                   f'<w:t xml:space="preserve">{_html.escape(part, quote=False)}</w:t></w:r>')
    return "".join(out)


def _docx_para(text: str, style: str = "") -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}{_docx_runs(text)}</w:p>"


def _docx_table(rows: List[List[str]]) -> str:
    if not rows:
        return ""
    cols = max(len(r) for r in rows)
    grid = "".join('<w:gridCol w:w="%d"/>' % (9000 // cols) for _ in range(cols))
    body = []
    for i, r in enumerate(rows):
        cells = "".join(
            f'<w:tc><w:tcPr><w:tcW w:w="{9000 // cols}" w:type="dxa"/>'
            + ('<w:shd w:val="clear" w:color="auto" w:fill="E8F2DC"/>' if i == 0 else "")
            + f"</w:tcPr>{_docx_para(('**' + c + '**') if i == 0 and c else c)}</w:tc>"
            for c in (r + [""] * (cols - len(r))))
        body.append(f"<w:tr>{cells}</w:tr>")
    borders = "".join(f'<w:{b} w:val="single" w:sz="4" w:color="C9CFC6"/>'
                      for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
    return (f'<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/><w:tblBorders>{borders}</w:tblBorders></w:tblPr>'
            f"<w:tblGrid>{grid}</w:tblGrid>{''.join(body)}</w:tbl><w:p/>")


def make_docx(path: str, title: str, md: str) -> None:
    paras, table = [], []

    def flush_table():
        if table:
            paras.append(_docx_table(md_table_rows("\n".join(table))))
            table.clear()
    if title and not (md or "").lstrip().startswith("# "):
        paras.append(_docx_para(title, "Title"))
    in_code = False
    for raw in (md or "").splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            paras.append(f'<w:p><w:pPr><w:pStyle w:val="Code"/></w:pPr><w:r><w:t xml:space="preserve">'
                         f"{_html.escape(line, quote=False)}</w:t></w:r></w:p>")
            continue
        if line.strip().startswith("|"):
            table.append(line)
            continue
        flush_table()
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            paras.append(_docx_para(m.group(2), {1: "Heading1", 2: "Heading2", 3: "Heading3"}[len(m.group(1))]))
        elif re.match(r"^\s*[-*\u2022]\s+", line):
            paras.append(_docx_para("\u2022  " + re.sub(r"^\s*[-*\u2022]\s+", "", line), "ListParagraph"))
        elif re.match(r"^\s*\d+[.)]\s+", line):
            paras.append(_docx_para(line.strip(), "ListParagraph"))
        elif line.strip():
            paras.append(_docx_para(line.strip()))
    flush_table()
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>'
                + "".join(paras) +
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1300" w:right="1300" w:bottom="1300" '
                'w:left="1300" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')

    def style(sid, name, size, bold=False, color="1C211D", before=0, after=120, font=None):
        rfont = f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>' if font else ""
        default = ' w:default="1"' if sid == "Normal" else ""
        return (f'<w:style w:type="paragraph"{default} w:styleId="{sid}"><w:name w:val="{name}"/>'
                f'<w:pPr><w:spacing w:before="{before}" w:after="{after}"/></w:pPr>'
                f'<w:rPr>{rfont}{"<w:b/>" if bold else ""}<w:color w:val="{color}"/><w:sz w:val="{size}"/></w:rPr></w:style>')
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
              '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Arial"/>'
              '<w:sz w:val="22"/></w:rPr></w:rPrDefault></w:docDefaults>'
              + style("Normal", "Normal", 22)
              + style("Title", "Title", 40, True, "1C211D", 0, 240)
              + style("Heading1", "heading 1", 32, True, "3F8212", 240, 120)
              + style("Heading2", "heading 2", 26, True, "1C211D", 200, 100)
              + style("Heading3", "heading 3", 23, True, "1C211D", 160, 80)
              + style("ListParagraph", "List Paragraph", 22, after=60)
              + style("Code", "Code", 19, after=0, font="Consolas")
              + "</w:styles>")
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                     '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                     '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                     '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '</Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '</Relationships>')
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{_html.escape(title or "")}</dc:title><dc:creator>Gink Assistant</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created></cp:coreProperties>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("docProps/core.xml", core)


# ---------------------------------------------------------------- spreadsheets
def make_xlsx(path: str, title: str, rows: List[List]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = re.sub(r"[\[\]:*?/\\]", "", title or "Sheet")[:31] or "Sheet"
    for r in rows:
        ws.append([_cell(v) for v in r])
    if rows:
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="3F8212")
            c.alignment = Alignment(vertical="center")
        ws.freeze_panes = "A2"
        for i in range(1, max(len(r) for r in rows) + 1):
            width = max(len(str(r[i - 1])) if i - 1 < len(r) else 0 for r in rows)
            ws.column_dimensions[get_column_letter(i)].width = min(max(10, width + 2), 50)
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if isinstance(c.value, float) and 0 < abs(c.value) < 1 and "%" in str(rows[c.row - 1][c.column - 1]):
                    c.number_format = "0%"
                elif isinstance(c.value, (int, float)):
                    c.number_format = "#,##0.##"
    wb.save(path)


def make_csv(path: str, rows: List[List]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:      # BOM: Excel opens accents correctly
        csv.writer(f).writerows(rows)


# ---------------------------------------------------------------- html / md / txt
HTML_PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{title}</title><style>body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;margin:40px auto;
padding:0 20px;line-height:1.6;color:#1C211D}}h1,h2{{color:#1C211D}}h1{{border-bottom:3px solid #A8F03C;padding-bottom:6px}}
table{{border-collapse:collapse}}th,td{{border:1px solid #C9CFC6;padding:6px 10px}}th{{background:#E8F2DC}}
code,pre{{background:#F1F3EE;border-radius:6px}}pre{{padding:12px;overflow:auto}}</style></head><body>{body}
<p style="color:#888;font-size:12px;margin-top:40px">Made with Gink Assistant</p></body></html>"""


def make_file(folder: str, kind: str, title: str, content: str = "", rows: Optional[List[List]] = None) -> MadeFile:
    kind = (kind or "").lower().lstrip(".")
    kind = {"word": "docx", "doc": "docx", "excel": "xlsx", "xls": "xlsx", "markdown": "md", "text": "txt",
            "spreadsheet": "xlsx", "sheet": "xlsx"}.get(kind, kind)
    if kind not in KINDS - {"png", "jpg"}:
        raise FileMakerError(f"I can't make .{kind} files yet. I can make PDF, Word, Excel, CSV, Markdown, HTML or text.")
    if kind in ("xlsx", "csv"):
        rows = rows or md_table_rows(content)
        if not rows:
            raise FileMakerError("A spreadsheet needs a table \u2014 give me the rows and columns.")
    elif not (content or "").strip():
        raise FileMakerError("There's nothing to put in the file yet.")
    path = unique_path(folder, safe_name(title, kind))
    try:
        if kind == "pdf":
            make_pdf(path, title, content)
        elif kind == "docx":
            make_docx(path, title, content)
        elif kind == "xlsx":
            make_xlsx(path, title, rows)
        elif kind == "csv":
            make_csv(path, rows)
        elif kind == "html":
            with open(path, "w", encoding="utf-8") as f:
                f.write(HTML_PAGE.format(title=_html.escape(title or "Gink"), body=md_to_html_body(content)))
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write((f"# {title}\n\n" if kind == "md" and title and not content.lstrip().startswith("#") else "") + content)
    except FileMakerError:
        raise
    except Exception as exc:
        if os.path.exists(path):
            os.remove(path)
        raise FileMakerError(f"Couldn't make the {kind.upper()} file ({exc.__class__.__name__}).")
    return MadeFile(path=path, name=os.path.basename(path), kind=kind, size=os.path.getsize(path))


def save_image(folder: str, title: str, data: bytes, mime: str = "image/png") -> MadeFile:
    kind = "jpg" if "jpeg" in (mime or "") else "png"
    path = unique_path(folder, safe_name(title, kind))
    with open(path, "wb") as f:
        f.write(data)
    return MadeFile(path=path, name=os.path.basename(path), kind=kind, size=len(data))
