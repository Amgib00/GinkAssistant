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

Regular (non-document) fenced code blocks (0.1.160: highlighted here with Pygments
and Gink's own light/dark colours -- render_code_block -- not by Markdown's codehilite;
shell commands get their own lexer: the command apart from its arguments) get the same
Copy + Download treatment, plus one more thing: a leading comment line that's
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
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name, get_lexer_for_filename
from pygments.lexers.shell import BashLexer
from pygments.token import Comment, Keyword, Name, Operator, Punctuation, String, Text
from pygments.util import ClassNotFound

# Code colours (0.1.160): Gink's own light and dark palettes, like a code editor's, instead of Pygments' dark
# "monokai" everywhere. Tokens keep Pygments' short class names; the colours are CSS variables, so the same
# HTML follows the page's light or dark theme (body.theme-dark).
CODE_TOKEN_CSS = """
.codehilite { --tk-kw: #0550AE; --tk-fn: #6639BA; --tk-str: #116329; --tk-num: #953800; --tk-com: #6E7781;
  --tk-var: #8A4600; --tk-tag: #116329; --tk-attr: #0550AE; --tk-op: #57606A; --tk-del: #82071E; --tk-ins: #116329; }
body.theme-dark .codehilite { --tk-kw: #79C0FF; --tk-fn: #D2A8FF; --tk-str: #7EE787; --tk-num: #FFA657; --tk-com: #8B949E;
  --tk-var: #FFA657; --tk-tag: #7EE787; --tk-attr: #79C0FF; --tk-op: #9DA7B1; --tk-del: #FFA198; --tk-ins: #7EE787; }
.codehilite .c, .codehilite .ch, .codehilite .cm, .codehilite .c1, .codehilite .cs, .codehilite .cpf { color: var(--tk-com); }
.codehilite .k, .codehilite .kd, .codehilite .kn, .codehilite .kp, .codehilite .kr, .codehilite .ow, .codehilite .cp { color: var(--tk-kw); }
.codehilite .nb, .codehilite .bp, .codehilite .si { color: var(--tk-kw); }
.codehilite .kc, .codehilite .m, .codehilite .mb, .codehilite .mf, .codehilite .mh, .codehilite .mi, .codehilite .il, .codehilite .mo, .codehilite .se { color: var(--tk-num); }
.codehilite .kt, .codehilite .nc, .codehilite .nf, .codehilite .fm, .codehilite .nd, .codehilite .ne, .codehilite .nl { color: var(--tk-fn); }
.codehilite .s, .codehilite .sa, .codehilite .sb, .codehilite .sc, .codehilite .dl, .codehilite .sd, .codehilite .s2, .codehilite .sh, .codehilite .sx, .codehilite .sr, .codehilite .s1, .codehilite .ss { color: var(--tk-str); }
.codehilite .nv, .codehilite .vc, .codehilite .vg, .codehilite .vi, .codehilite .vm { color: var(--tk-var); }
.codehilite .nt { color: var(--tk-tag); }
.codehilite .na { color: var(--tk-attr); }
.codehilite .o { color: var(--tk-op); }
.codehilite .gd { color: var(--tk-del); }
.codehilite .gi { color: var(--tk-ins); }
.codehilite .gh, .codehilite .gu { color: var(--tk-kw); font-weight: 600; }
.codehilite .gp, .codehilite .go { color: var(--tk-com); }
.codehilite .err { color: inherit; border: 0; background: none; }
""".strip()
PYGMENTS_CSS = CODE_TOKEN_CSS            # the name the chat page already uses


def code_css_for_media() -> str:
    """The same code colours for a page that follows the system's dark mode (Gink Genie) instead of body.theme-dark."""
    text = CODE_TOKEN_CSS
    start = text.index("body.theme-dark .codehilite {")
    end = text.index("}", start) + 1
    dark = text[start:end].replace("body.theme-dark .codehilite", ".codehilite", 1)
    return text[:start] + text[end:].lstrip("\n") + "\n@media (prefers-color-scheme: dark) { " + dark + " }"

_DOCUMENT_BLOCK_RE = re.compile(r"```document[ \t]*\r?\n(.*?)\r?\n```", re.DOTALL)
# A fenced block on its own lines (also indented, inside a list): its indent, language, code
_FENCE_RE = re.compile(r"^([ \t]*)(```|~~~)[ \t]*([\w+#.\-]*)[^\n`]*\n(.*?)\n?[ \t]*\2[ \t]*$", re.MULTILINE | re.DOTALL)
_FILENAME_LINE_RE = re.compile(r"^[ \t]*(?:#|//|--|/\*)[ \t]*([\w\-. ]+\.[a-zA-Z0-9]{1,10})[ \t]*(?:\*/)?[ \t]*$")
_MD_EXTENSIONS = ["tables", "nl2br"]
_MD_EXTENSION_CONFIGS = {}
_FORMATTER = HtmlFormatter(cssclass="codehilite", wrapcode=True)

LANG_ALIASES = {
    "sh": "bash", "shell": "bash", "zsh": "bash", "console": "bash", "terminal": "bash", "shell-session": "bash",
    "bat": "batch", "cmd": "batch", "ps": "powershell", "ps1": "powershell", "pwsh": "powershell",
    "py": "python", "python3": "python", "py3": "python", "js": "javascript", "node": "javascript", "mjs": "javascript",
    "ts": "typescript", "yml": "yaml", "md": "markdown", "html5": "html", "htm": "html", "c++": "cpp", "c#": "csharp",
    "cs": "csharp", "kt": "kotlin", "rb": "ruby", "rs": "rust", "golang": "go", "sqlite": "sql", "postgres": "sql",
    "dockerfile": "docker", "plaintext": "text", "txt": "text", "plain": "text", "json5": "json", "jsonc": "json",
    "objc": "objective-c", "vue": "html", "svelte": "html",
}
NO_HIGHLIGHT = {"", "text", "map", "ask", "mermaid", "output", "log"}     # map/ask: the page turns these into a map / choices
SHELL_COMMANDS = {
    "cd", "ls", "git", "gh", "npm", "npx", "pnpm", "yarn", "pip", "pip3", "python", "python3", "node", "brew", "apt",
    "apt-get", "sudo", "curl", "wget", "mkdir", "rm", "cp", "mv", "cat", "echo", "export", "docker", "unzip", "tar",
    "chmod", "chown", "bash", "sh", "source", "conda", "cargo", "make", "ssh", "scp", "grep", "touch", "open",
    "briefcase", "pytest", "gink", "flutter", "go", "java", "javac", "kubectl", "systemctl", "winget", "choco",
}
_PREFIX_COMMANDS = {"sudo", "doas", "time", "nohup", "exec", "env", "nice", "xargs", "watch"}
_CMD_STARTERS = {"|", "||", "&&", ";", "&", "(", "$(", "`", "!", "{", "then", "do", "else", "elif", "if", "while", "until"}


class _ShellLexer(BashLexer):
    """Bash as people read a command line: the command (the first word, blue) apart from its arguments (green),
    like the code blocks people know from other assistants. Pygments' own Bash lexer only colours builtins."""
    name = "Shell (Gink)"
    aliases = []

    def get_tokens_unprocessed(self, text):
        at_cmd, value_next, arg_assign = True, False, False
        for index, tok, val in super().get_tokens_unprocessed(text):
            word = val.strip()
            if not word:                                     # spaces and newlines
                if "\n" in val:
                    at_cmd, value_next = True, False
                arg_assign = False
                yield index, tok, val
                continue
            if arg_assign and (word == "=" or tok is Text):  # -f version=v1.2: one argument, all of it
                if word != "=":
                    arg_assign = False
                yield index, String, val
                continue
            if tok in Comment:
                at_cmd = True                                # a comment runs to the end of the line
                yield index, tok, val
                continue
            if tok in Operator or tok in Punctuation or tok in Keyword:
                if word == "=" and value_next:
                    yield index, tok, val                    # FOO=bar: what follows is the value
                    continue
                if word in _CMD_STARTERS:
                    at_cmd = True
                yield index, tok, val
                continue
            if tok in Name.Variable:
                if not at_cmd and not val.startswith("$"):   # name=value inside an argument, not a variable
                    arg_assign = True
                    yield index, String, val
                    continue
                value_next = at_cmd                          # an assignment before the command
                yield index, tok, val
                continue
            if tok is Text or tok in Name.Builtin:
                if value_next:
                    value_next = False
                    yield index, String, val
                elif at_cmd:
                    at_cmd = word in _PREFIX_COMMANDS        # sudo apt install: apt is the command too
                    yield index, Name.Builtin, val
                else:
                    yield index, String, val                 # an argument, a flag, a path
                continue
            yield index, tok, val


def _looks_like_shell(code: str) -> bool:
    lines = [ln.strip() for ln in code.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not lines or len(lines) > 40:
        return False
    hits = sum(1 for ln in lines if ln.lstrip("$ ").split(" ", 1)[0] in SHELL_COMMANDS)
    return hits / len(lines) >= 0.6


def code_language(fence_lang: str, code: str, filename=None) -> str:
    """The language key a fence's code is highlighted and labelled with ("" = plain)."""
    key = (fence_lang or "").strip().lower()
    key = LANG_ALIASES.get(key, key)
    if not key and _looks_like_shell(code):
        return "bash"
    return key


def _lexer_for(key: str, filename=None):
    if key in NO_HIGHLIGHT:
        return TextLexer()
    if key == "bash":
        return _ShellLexer()
    try:
        return get_lexer_by_name(key)
    except ClassNotFound:
        pass
    if filename:
        try:
            return get_lexer_for_filename(filename)
        except ClassNotFound:
            pass
    return TextLexer()


def render_code_block(fence_lang: str, code: str) -> str:
    """One fenced block: a header (the file's name or the language) with Copy and Download, then the code,
    coloured for its language. The chat page (ui/chat_extras.py) turns the header into icon buttons."""
    code, filename = _strip_filename_line(fence_lang, code)
    key = code_language(fence_lang, code, filename)
    shown = (fence_lang or "").strip()
    label = filename or (shown if shown and LANG_ALIASES.get(shown.lower(), shown.lower()) == key else key) or "code"
    body = highlight(code, _lexer_for(key, filename), _FORMATTER)
    return (
        f'<div class="code-block" data-lang="{html_module.escape(key or "text")}">'
        '<div class="code-block-bar">'
        f'<span class="code-block-label">{html_module.escape(label)}</span>'
        '<button class="code-copy-btn" onclick="copyCodeBlock(this)">Copy</button>'
        '<button class="code-download-btn" onclick="downloadCodeBlock(this)">Download</button>'
        "</div>"
        f'<div class="code-block-body">{body}</div>'
        "</div>"
    )

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



# Blocks the AI writes without a blank line before them (0.1.160). Python-Markdown only starts a list, a table or a
# quote after a blank line, so "**Key points**\n- one\n- two" and "Models:\n| A | B |\n|---|---|" came out as plain
# text with "-" and "|" in it (a Bugatti answer in the owner's recording). Real Markdown readers (GitHub, other
# assistants) start them anyway -- so a blank line is added where one is missing, outside code.
_LIST_ITEM = re.compile(r"^ {0,3}(?:[-*+]|\d{1,3}[.)])[ \t]+\S")
_TABLE_DELIM = re.compile(r"^ {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
_QUOTE_LINE = re.compile(r"^ {0,3}>")
_ANY_ITEM = re.compile(r"^( *)(?:[-*+]|\d{1,3}[.)])[ \t]+\S")


def _nest_lists(lines: list) -> list:
    """Sub-lists indented by 2 or 3 spaces (how AIs often write them) indented by 4, so they nest instead of
    flattening into the list above: "- a\n  - b" -> "- a\n    - b"."""
    out, stack = [], []
    for line in lines:
        m = _ANY_ITEM.match(line)
        if m:
            ind = len(m.group(1))
            while stack and stack[-1] > ind:
                stack.pop()
            if not stack:
                if ind > 3:
                    out.append(line)
                    continue
                stack.append(ind)
            elif ind > stack[-1]:
                stack.append(ind)
            out.append("    " * (len(stack) - 1) + line.lstrip(" "))
            continue
        if line.strip() and not line[:1].isspace():
            stack = []                                 # text at the margin: the list is over
        out.append(line)
    return out


def _block_breaks(text: str) -> str:
    lines, out, in_table = _nest_lists(text.split("\n")), [], False
    for i, line in enumerate(lines):
        prev = out[-1] if out else ""
        if in_table:
            if line.strip() and "|" in line:
                out.append(line)
                continue
            in_table = False
            if line.strip():
                out.append("")                         # text right after a table is its own paragraph, not a row
                prev = ""
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if "|" in line and "|" in nxt and "-" in nxt and _TABLE_DELIM.match(nxt):   # a table's header row
            if prev.strip():
                out.append("")
            out.append(line)
            in_table = True
            continue
        if prev.strip() and not prev[:1].isspace():
            if _LIST_ITEM.match(line) and not _LIST_ITEM.match(prev):
                out.append("")

            elif _QUOTE_LINE.match(line) and not _QUOTE_LINE.match(prev):
                out.append("")
        out.append(line)
    return "\n".join(out)


def _md_with_code(text: str) -> str:
    """Markdown with fenced code rendered by render_code_block (header, colours) and put back after the Markdown
    pass, so Markdown never touches the code (no <br> in it) and a block indented in a list keeps its own indent."""
    blocks = {}

    def _stash_fence(match: re.Match) -> str:
        indent, language, content = match.group(1), match.group(3) or "", match.group(4)
        if indent:
            content = "\n".join(ln[len(indent):] if ln.startswith(indent) else ln.lstrip(" \t") for ln in content.split("\n"))
        token = f"CODEBLOCKPLACEHOLDER{uuid.uuid4().hex}"
        blocks[token] = render_code_block(language, content)
        return f"\n\n{indent}{token}\n\n"

    out = _to_html(_block_breaks(_FENCE_RE.sub(_stash_fence, text)))
    for token, block_html in blocks.items():
        out = out.replace(f"<p>{token}</p>", block_html).replace(token, block_html)
    return out


def _render_document_block(raw_text: str) -> str:
    inner_html = _md_with_code(raw_text)
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


# Narrow / thin spaces (U+202F, U+2009, U+200A, U+2006, U+2005, U+2007) -- GPT-OSS models
# often write "2:23\u202fPM" or "Saturday,\u202fOctober". They're only ~1/5 of a normal space,
# so words look glued together ("Saturday,October17"). Shown as normal spaces instead.
_NARROW_SPACES = dict.fromkeys(map(ord, "\u202f\u2009\u200a\u2006\u2005\u2007"), " ")


def _normal_spaces(text: str) -> str:
    return text.translate(_NARROW_SPACES)


def render_markdown_body(text: str) -> str:
    """Full markdown -> HTML. Fenced code blocks get a header bar with a
    detected filename (or the language, as a fallback) plus Copy and
    Download actions; ```document blocks render as copyable/downloadable
    prose instead of code."""
    text = _normal_spaces(text or "")
    doc_placeholders = {}

    def _stash_document(match: re.Match) -> str:
        token = f"DOCBLOCKPLACEHOLDER{uuid.uuid4().hex}"
        doc_placeholders[token] = _render_document_block(match.group(1))
        return token

    text = _DOCUMENT_BLOCK_RE.sub(_stash_document, text)
    html_out = _md_with_code(text)

    for token, block_html in doc_placeholders.items():
        html_out = html_out.replace(f"<p>{token}</p>", block_html)
        html_out = html_out.replace(token, block_html)
    return html_out


def escape_for_plain_text(text: str) -> str:
    """For streaming raw tokens into the DOM before the full markdown
    parse happens -- same escaping innerHTML would need, done on the
    Python side so the JS side can stay a simple += append."""
    return html_module.escape(text)
