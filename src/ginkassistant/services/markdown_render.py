"""
Python-side markdown -> HTML, the same markdown+pygments approach
ui/code_block.py (PySide6) used -- kept here in Python rather than
loading a JS markdown library into the WebView, so the chat feed's HTML
shell stays fully self-contained with no CDN/network dependency just to
render.

```document ... ``` blocks (services/groq_worker.py's system prompt
asks for these on long-form writing -- essays, articles, letters, and
similar) get pulled out and rendered separately, in natural prose
styling rather than a monospace code block, wrapped in a container with
Copy and Download actions. Pygments has no real lexer for "document" as
a language, and fighting its class-naming for a non-code use wasn't
worth it -- this extracts those blocks with a regex before the main
markdown pass, renders their contents through the same markdown() call
(so formatting inside the document still looks right), and reinserts the
result as custom HTML after.

Regular (non-document) fenced code blocks now get the same Copy +
Download treatment, plus one more thing: a leading comment line that's
just a filename (# tic_tac_toe.py, // app.js, -- schema.sql, /* style.css
*/) gets pulled out of the code itself and shown as a title in the
block's header bar instead -- the way Claude's own code blocks show a
filename, not as a comment baked into the first line of actual code.
When no such line is found, the block's language (python, javascript,
etc.) is shown there instead. This runs as a pre-pass on the plain-text
fence content (stripping a line from a string is simple and reliable)
before codehilite ever syntax-highlights it, rather than trying to
surgically edit the highlighted HTML afterward -- doing it on already-
tokenized spans would be far messier. The detected filename (or None)
for each fence is tracked in source order, then matched back up with
each rendered <div class="codehilite"> by that same order once
markdown.markdown() is done -- codehilite's actual output structure was
checked directly rather than assumed, so this wrapping targets exactly
what it produces.
"""

import html as html_module
import re
import uuid

import markdown
import markdown.extensions
import markdown.treeprocessors
from pygments.formatters import HtmlFormatter

PYGMENTS_CSS = HtmlFormatter(style="monokai").get_style_defs(".codehilite")

_DOCUMENT_BLOCK_RE = re.compile(r"```document[ \t]*\r?\n(.*?)\r?\n```", re.DOTALL)
_FENCE_RE = re.compile(r"```(\w*)[ \t]*\r?\n(.*?)\r?\n```", re.DOTALL)
_FILENAME_LINE_RE = re.compile(r"^[ \t]*(?:#|//|--|/\*)[ \t]*([\w\-. ]+\.[a-zA-Z0-9]{1,10})[ \t]*(?:\*/)?[ \t]*$")
_CODEHILITE_DIV_RE = re.compile(r'<div class="codehilite">')
_MD_EXTENSIONS = ["fenced_code", "codehilite", "tables", "nl2br"]
_MD_EXTENSION_CONFIGS = {"codehilite": {"css_class": "codehilite", "guess_lang": False}}

class _NoRawHtml(markdown.extensions.Extension):
    """SECURITY: show raw HTML in text as text. Chat text can come from the AI, from
    web pages it read, or from synced chats; HTML in it (<script>, <img onerror=...>)
    must never run inside Gink's window. Removes Markdown's raw-HTML block and inline
    handlers, so '<' and '>' are escaped like any other character."""

    def extendMarkdown(self, md):
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")
        md.treeprocessors.register(_SafeLinks(md), "gink_safe_links", 0)


_SAFE_LINK = ("http://", "https://", "mailto:", "tel:", "gink://", "#")
_SAFE_IMG = ("http://", "https://", "data:image/png", "data:image/jpeg", "data:image/gif", "data:image/webp")


class _SafeLinks(markdown.treeprocessors.Treeprocessor):
    """SECURITY: only safe link / image targets. '[x](javascript:...)' must not run code."""

    def run(self, root):
        for el in root.iter():
            for attr, allowed in (("href", _SAFE_LINK), ("src", _SAFE_IMG)):
                v = el.get(attr)
                if v is None:
                    continue
                clean = "".join(ch for ch in v if ch > " ").lower()     # no tricks like 'java\tscript:'
                if not clean.startswith(allowed) and ":" in clean.split("/")[0]:
                    el.set(attr, "#")
        return root


def _to_html(text: str) -> str:
    return markdown.markdown(text, extensions=list(_MD_EXTENSIONS) + [_NoRawHtml()],
                             extension_configs=_MD_EXTENSION_CONFIGS)



def _render_document_block(raw_text: str) -> str:
    inner_html = _to_html(raw_text)
    # Copy/Download (ui/web_chat_view.py's copyDocBlock/downloadDocBlock)
    # read this body's rendered innerText at click time, not a stored raw
    # markdown source -- that way **bold**/# headings/etc. come out as
    # clean prose (the browser already turned them into real formatting),
    # not literal markdown syntax characters. No data-raw attribute needed.
    return (
        '<div class="doc-block">'
        '<div class="doc-block-bar">'
        '<span class="doc-block-label">Document</span>'
        '<button class="doc-copy-btn" onclick="copyDocBlock(this)">Copy</button>'
        '<button class="doc-download-btn" onclick="downloadDocBlock(this)">Download</button>'
        "</div>"
        f'<div class="doc-block-body">{inner_html}</div>'
        "</div>"
    )


def _strip_filename_line(language: str, content: str):
    """Returns (possibly-shortened content, detected filename or None)."""
    lines = content.split("\n")
    if not lines:
        return content, None
    m = _FILENAME_LINE_RE.match(lines[0])
    if not m:
        return content, None
    filename = m.group(1).strip()
    remaining = "\n".join(lines[1:]).lstrip("\n")
    if not remaining:
        # The whole block was just that one line -- nothing left to show
        # as code, so leave the original content alone rather than
        # rendering an empty block.
        return content, None
    return remaining, filename


def render_markdown_body(text: str) -> str:
    """Full markdown -> HTML. Fenced code blocks get a header bar with a
    detected filename (or the language, as a fallback) plus Copy and
    Download actions; ```document blocks render as copyable/downloadable
    prose instead of code."""
    doc_placeholders = {}

    def _stash_document(match: re.Match) -> str:
        token = f"DOCBLOCKPLACEHOLDER{uuid.uuid4().hex}"
        doc_placeholders[token] = _render_document_block(match.group(1))
        return token

    text = _DOCUMENT_BLOCK_RE.sub(_stash_document, text)

    code_block_info = []  # [(language, filename_or_None), ...] in source order

    def _strip_fence(match: re.Match) -> str:
        language = match.group(1) or ""
        content = match.group(2)
        new_content, filename = _strip_filename_line(language, content)
        code_block_info.append((language, filename))
        return f"```{language}\n{new_content}\n```"

    text = _FENCE_RE.sub(_strip_fence, text)

    html_out = _to_html(text)

    code_block_iter = iter(code_block_info)

    def _wrap_code_block(match: re.Match) -> str:
        try:
            language, filename = next(code_block_iter)
        except StopIteration:
            return match.group(0)  # shouldn't happen; leave unwrapped rather than crash
        label = html_module.escape(filename) if filename else html_module.escape(language or "code")
        return (
            '<div class="code-block">'
            '<div class="code-block-bar">'
            f'<span class="code-block-label">{label}</span>'
            '<button class="code-copy-btn" onclick="copyCodeBlock(this)">Copy</button>'
            '<button class="code-download-btn" onclick="downloadCodeBlock(this)">Download</button>'
            "</div>"
            f'<div class="code-block-body">{match.group(0)}'
        )

    # Each codehilite div needs a matching closing </div> for the new
    # wrapper -- easiest done by wrapping the opening tag here, then
    # closing every wrapper in one pass afterward (the codehilite divs
    # are never nested, so a straight count-for-count match is safe).
    html_out = _CODEHILITE_DIV_RE.sub(_wrap_code_block, html_out)
    # _wrap_code_block only replaces the codehilite div's OPENING tag
    # (that's all _CODEHILITE_DIV_RE matches) with its own opening markup
    # plus two new wrapper divs (code-block, code-block-body) -- the
    # codehilite div's actual content and its own original closing </div>
    # are untouched, still sitting right where they were. So two wrapper
    # divs need closing here, not one: codehilite's own structure always
    # ends with the exact sequence "</code></pre></div>" (confirmed
    # directly against its real output, not assumed), and that exact
    # three-tag sequence doesn't occur anywhere else in the page, so two
    # extra </div> right after it closes exactly these two wrappers and
    # nothing else.
    html_out = html_out.replace("</code></pre></div>", "</code></pre></div></div></div>")

    for token, block_html in doc_placeholders.items():
        html_out = html_out.replace(f"<p>{token}</p>", block_html)
        html_out = html_out.replace(token, block_html)
    return html_out


def escape_for_plain_text(text: str) -> str:
    """For streaming raw tokens into the DOM before the full markdown
    parse happens -- same escaping innerHTML would need, done on the
    Python side so the JS side can stay a simple += append."""
    return html_module.escape(text)