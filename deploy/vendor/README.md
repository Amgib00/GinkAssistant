# Server-only libraries

Served by Gink's server at `/vendor/{name}` like `src/ginkassistant/services/web_app/vendor`, but kept OUT of the
apps' packages (Briefcase packages only `src/ginkassistant`): the pages load them from the server when needed.

- `mermaid.min.js`: Mermaid 11.17.2 (https://github.com/mermaid-js/mermaid), MIT licence (`MERMAID-LICENSE.txt`).
  Unchanged except the source-map comment removed. Draws diagram artifacts (0.1.161) inside the sealed preview.
- `lexend-latin-wght-normal.woff2`, `lexend-latin-ext-wght-normal.woff2`: Lexend (variable weight), SIL Open Font
  License (`LEXEND-LICENSE.txt`) -- the same files as the website's `website/assets/fonts`. The sign-in page
  (`web_app/auth.html`) uses them, so signing in looks like the website.

The server image copies this folder to `/srv/vendor` (deploy/Dockerfile).
To update: `npm pack mermaid@11.x`, copy `dist/mermaid.min.js` (minus its last `//# sourceMappingURL=` line) and
`LICENSE`, then change `MERMAID_VERSION` in `ui/chat_extras.py`.
