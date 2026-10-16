"""
Gink's single colour theme -- every screen imports from here, so changing
a colour once changes it everywhere (before this, each screen had its own
copy of the palette and they had drifted apart: cream chat, white login,
blue Media Studio).

Light theme. The logo is a neon-lime circuit snowflake (#A8F03C), which
is nearly invisible on white, so wherever it appears it sits on a small
dark rounded tile (LOGO_TILE) -- like an app icon. Buttons and links use a
deeper green from the same family (ACCENT) so white text on them stays
readable.

Contrast (WCAG): TEXT_MAIN on white ~16:1, TEXT_MUTED on white ~4.7:1,
white on ACCENT ~4.9:1 -- all above the 4.5:1 body-text bar.
"""

# Surfaces (light theme)
BG_MAIN = "#FFFFFF"       # app background, chat feed
BG_SURFACE = "#FFFFFF"    # header, composer area
BG_SIDEBAR = "#F6F7F3"    # sidebar -- a whisper of green-grey
BG_ELEVATED = "#F1F3EE"   # cards, inputs, selected rows, user bubbles
BG_HOVER = "#E6EADF"      # pressed / flash state
BORDER = "#E2E5DC"

# Text
TEXT_MAIN = "#1C211D"
TEXT_MUTED = "#6E756D"

# Brand
LOGO_LIME = "#A8F03C"     # the logo's own colour -- only ever on the dark logo tile
LOGO_TILE = "#0E1611"     # dark rounded tile the logo sits on, so it pops on white
ACCENT = "#3F8212"        # lime deepened enough for white text on it (4.9:1)
ACCENT_DIM = "#5C9E22"    # secondary accent
ACCENT_SOFT = "#EEF8E1"   # tinted background behind accent text
ON_ACCENT = "#FFFFFF"     # text placed ON an accent button

# Status
DANGER = "#C93B32"
WARNING = "#B7791F"

# Back-compat names the older screens used
COLOR_PRIMARY = ACCENT
VOICE_ACTIVE_COLOR = ACCENT


def css_vars() -> str:
    """The same palette as CSS custom properties, for the WebView pages
    (chat feed, login header), so HTML and native widgets always match."""
    return (
        f"--bg: {BG_MAIN}; --surface: {BG_SURFACE}; --elevated: {BG_ELEVATED}; "
        f"--border: {BORDER}; --text-main: {TEXT_MAIN}; --text-muted: {TEXT_MUTED}; "
        f"--accent: {ACCENT}; --accent-dim: {ACCENT_DIM}; --accent-soft: {ACCENT_SOFT}; "
        f"--on-accent: {ON_ACCENT}; --danger: {DANGER}; --sidebar: {BG_SIDEBAR}; "
        f"--logo-lime: {LOGO_LIME}; --logo-tile: {LOGO_TILE};"
    )
