"""
Builds the Gink website:  website/pages/*.html  ->  website/_site/

    python tools/build_website.py          # then open website/_site/index.html

Every page in website/pages/ holds only its own content plus a small header:

    <!--
    title: Features
    description: One sentence for search engines and link previews.
    -->
    ...page content...

The shared layout (head, menu, footer) lives here, so a menu change is one edit.
The snowflake (header, footer, the hero's "thinking" Gink) comes from the app's own
src/ginkassistant/ui/logo_svg.py. Placeholders in pages: {{SNOWFLAKE}} (big),
{{FLAKE}} (small, for a Gink avatar), {{REPO}}, {{YEAR}}, {{API}} (the server).
No trackers or third-party requests: the one font (Lexend, SIL Open Font License)
is self-hosted in website/assets/fonts, so the site loads nothing from anyone else
(privacy.html says so).
GitHub Pages: .github/workflows/website.yml runs this and publishes website/_site.
"""
import html
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "website")
OUT = os.path.join(SRC, "_site")
sys.path.insert(0, os.path.join(ROOT, "src"))
from ginkassistant.ui.logo_svg import logo_svg          # noqa: E402

SITE_NAME = "Gink"
YEAR = "2026"
NAV = [("features.html", "Features"), ("pricing.html", "Pricing"), ("demo.html", "Demo"),
       ("developers.html", "Developers"), ("blog.html", "Blog"), ("contact.html", "Contact")]
FOOTER = [
    ("Product", [("features.html", "Features"), ("pricing.html", "Pricing"), ("demo.html", "Try the demo"),
                 ("download.html", "Download")]),
    ("Gink", [("vision.html", "Vision and mission"), ("blog.html", "Blog"), ("community.html", "Community"),
              ("developers.html", "Developers"), ("https://gink-server.onrender.com/developers#docs", "API reference"),
              ("contact.html", "Contact")]),
    ("Legal", [("privacy.html", "Privacy policy"), ("terms.html", "Terms of service: Consumer"),
               ("terms-commercial.html", "Terms of service: Commercial"), ("dpa.html", "Data Processing Agreement"),
               ("usage-policy.html", "Usage policy"), ("responsible-disclosure.html", "Responsible disclosure"),
               ("memory.html", "How memory works"), ("delete-account.html", "Delete your account")]),
]
REPO = "https://github.com/amgib00/ginkassistant"
API = "https://gink-server.onrender.com"
SITE_URL = "https://amgib00.github.io/GinkAssistant/"     # GitHub Pages (the apps link here: GINK_SITE)

LAYOUT = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="theme-color" content="#151D23">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:type" content="website">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{site_url}assets/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Think. Talk. Create. Gink answering a voice message with a real street map of Zurich.">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="{url}">
<link rel="icon" type="image/png" sizes="32x32" href="assets/icon-32.png">
<link rel="apple-touch-icon" href="assets/icon-180.png">
<link rel="manifest" href="assets/site.webmanifest">
<link rel="preload" href="assets/fonts/lexend-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="assets/styles.css">
</head>
<body class="page-{slug}">
<a class="skip" href="#content">Skip to content</a>
<header class="site-header night">
  <div class="wrap header-row">
    <a class="brand" href="index.html" aria-label="Gink home">
      {flake}
      <span>Gink</span>
    </a>
    <button class="menu-toggle" aria-expanded="false" aria-controls="site-nav">
      <span class="menu-bars" aria-hidden="true"></span><span class="sr">Menu</span>
    </button>
    <nav id="site-nav" class="site-nav" aria-label="Main">
{nav}
      <a class="button button-small" href="download.html"{download_current}>Download</a>
    </nav>
  </div>
</header>
<main id="content">
{body}
</main>
<footer class="site-footer night">
  <div class="wrap footer-grid">
    <div class="footer-brand">
      <a class="brand" href="index.html">{flake}<span>Gink</span></a>
      <p>Think. Talk. Create.</p>
    </div>
{footer}
  </div>
  <div class="wrap footer-base">
    <p>&copy; {year} Gink AI</p>
    <p><a href="{repo}">Gink on GitHub</a></p>
  </div>
</footer>
<script src="assets/site.js"></script>{extra_scripts}
</body>
</html>
"""


def parse_page(text):
    m = re.match(r"\s*<!--(.*?)-->\s*", text, re.S)
    meta = {}
    if m:
        for line in m.group(1).strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        text = text[m.end():]
    return meta, text


def build():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    shutil.copytree(os.path.join(SRC, "assets"), os.path.join(OUT, "assets"))
    snowflake = logo_svg(320, cls="hero-flake")
    flake = logo_svg(30, cls="brand-flake")
    small = logo_svg(22, cls="avatar-flake")
    pages = sorted(f for f in os.listdir(os.path.join(SRC, "pages")) if f.endswith(".html"))
    for name in pages:
        meta, body = parse_page(open(os.path.join(SRC, "pages", name), encoding="utf-8").read())
        slug = name[:-5]
        title = meta.get("title", SITE_NAME)
        full_title = f"{title} | {SITE_NAME}" if slug != "index" else f"{SITE_NAME}: {title}"
        current = ' aria-current="page"'                 # (no backslashes inside f-strings: Python 3.11 can't)
        nav = "\n".join(
            f'      <a href="{href}"{current if href == name else ""}>{label}</a>' for href, label in NAV)
        footer = "\n".join(
            f'    <div class="footer-col"><h2>{head}</h2><ul>'
            + "".join(f'<li><a href="{h}">{l}</a></li>' for h, l in links) + "</ul></div>" for head, links in FOOTER)
        extra = "".join(f'\n<script src="assets/{s.strip()}"></script>' for s in meta.get("scripts", "").split(",") if s.strip())
        body = (body.replace("{{SNOWFLAKE}}", snowflake).replace("{{FLAKE}}", small).replace("{{REPO}}", REPO)
                .replace("{{API}}", API).replace("{{YEAR}}", YEAR))
        page = LAYOUT.format(title=html.escape(full_title), description=html.escape(meta.get("description", "")),
                             slug=slug, nav=nav, body=body, flake=flake, site_url=SITE_URL,
                             url=SITE_URL + ("" if name == "index.html" else name),
                             download_current=current if name == "download.html" else "",
                             footer=footer, year=YEAR, repo=REPO, extra_scripts=extra)
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(page)
    print(f"built {len(pages)} pages -> {os.path.relpath(OUT, ROOT)}/")
    return pages


if __name__ == "__main__":
    build()
