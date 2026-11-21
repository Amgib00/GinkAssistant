"""
Gink works with code projects on this computer (0.1.161): "what's in my GinkAssistant project?", "where is sign-in
handled?", "fix the failing test", "add a dark mode to my site". The agent maps a project (project_overview), finds
where things are (search_code), reads and changes files with the file tools (read_text_file / edit_text_file, a
backup first) and runs the project's OWN tests, linter or build to check its work (run_project_check).

SAFETY: read-only except run_project_check, which only ever runs a command Gink chose from the project's own files
(pytest, npm test, go test, cargo test, gradle, ...): never a command written by the AI or found in the conversation.
Run without a shell, in the project folder, with a time limit. As part of a longer task it asks first (agent.py:
ASK_IN_CHAIN). Projects must be inside the home folder. On phones it says plainly that it works on computers.
GitHub repositories (and Gink's own code) are read by the server instead: services/code_reader.py.
"""
import json
import os
import re
import shutil
import sys
import time
from typing import Dict, List, Optional, Tuple

from ._shell import run

MOBILE = hasattr(sys, "getandroidapilevel") or sys.platform == "ios"
WIN = sys.platform.startswith("win")
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env", ".env", "build", "dist",
             ".gradle", "target", ".idea", ".vscode", ".next", ".nuxt", "Pods", "DerivedData", ".tox", ".mypy_cache",
             ".pytest_cache", ".ruff_cache", "coverage", ".dart_tool", ".expo", "vendor", "out", "bin", "obj",
             ".terraform", ".cache", "site-packages", "logs"}
ROOT_MARKERS = (".git", "pyproject.toml", "setup.py", "package.json", "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
                "build.gradle.kts", "pubspec.yaml", "Gemfile", "composer.json", "requirements.txt", "Package.swift",
                "CMakeLists.txt", "Makefile", "deno.json", "mix.exs")
LANGS = {".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
         ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".swift": "Swift",
         ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".c": "C", ".h": "C", ".cc": "C++",
         ".cpp": "C++", ".hpp": "C++", ".m": "Objective-C", ".mm": "Objective-C", ".dart": "Dart", ".scala": "Scala",
         ".lua": "Lua", ".sh": "Shell", ".ps1": "PowerShell", ".sql": "SQL", ".html": "HTML", ".htm": "HTML",
         ".css": "CSS", ".scss": "CSS", ".vue": "Vue", ".svelte": "Svelte", ".r": "R", ".jl": "Julia", ".ex": "Elixir",
         ".exs": "Elixir", ".zig": "Zig"}
TEXT_EXT = set(LANGS) | {".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".md", ".txt", ".xml", ".gradle", ".env.example",
                         ".graphql", ".proto", ".tf", ".rst", ".csv", ".lock"}
MAX_FILES = 6000
MAX_MATCHES = 80
CHECK_TIMEOUT = 300
OUTPUT_TAIL = 6000


def _ok(msg, **extra):
    return {"ok": True, "message": msg, **extra}


def _no(msg):
    return {"ok": False, "message": msg}


class Codebase:
    def __init__(self, computer):
        self.pc = computer                     # ComputerControl: finding folders by name, the home-folder rule
        self.last_root: Optional[str] = None

    # ---------------- which project ----------------
    def root(self, which: str = "") -> Tuple[Optional[str], str]:
        """(project folder, why not). A file inside it, a folder's name ("GinkAssistant"), a path, or the last one."""
        if MOBILE:
            return None, "Working on code projects needs Gink on a computer (Mac, Windows or Linux)."
        w = (which or "").strip().strip('"')
        path = self.pc.resolve_path(w) if w else self.last_root
        if not path:
            return None, (f"I couldn't find a project called “{w}”. Give its folder's name or path." if w else
                          "Which project? Give its folder's name or path.")
        path = os.path.realpath(path)
        home = os.path.realpath(os.path.expanduser("~"))
        if not (path == home or path.startswith(home + os.sep)):
            return None, "I only work on projects inside your home folder."
        if os.path.isfile(path):
            path = os.path.dirname(path)
        probe = path                            # a folder inside a project: its project's own folder
        while probe.startswith(home + os.sep):
            if any(os.path.exists(os.path.join(probe, m)) for m in ROOT_MARKERS):
                path = probe
                break
            parent = os.path.dirname(probe)
            if parent == probe:
                break
            probe = parent
        if path == home:
            return None, "That's your whole home folder: which project folder in it?"
        self.last_root = path
        return path, ""

    def _files(self, root: str) -> List[str]:
        out = []
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and not d.endswith(".egg-info"))
            for f in sorted(files):
                if f.startswith(".") and f not in (".gitignore", ".env.example"):
                    continue
                out.append(os.path.relpath(os.path.join(dirpath, f), root))
                if len(out) >= MAX_FILES:
                    return out
        return out

    # ---------------- project_overview ----------------
    def overview(self, which: str = "") -> dict:
        root, why = self.root(which)
        if not root:
            return _no(why)
        files = self._files(root)
        langs: Dict[str, int] = {}
        for f in files:
            lang = LANGS.get(os.path.splitext(f)[1].lower())
            if lang:
                langs[lang] = langs.get(lang, 0) + 1
        top: Dict[str, int] = {}
        for f in files:
            head = f.split(os.sep)[0] + (os.sep if os.sep in f else "")
            top[head] = top.get(head, 0) + 1
        lines = [f"Project {os.path.basename(root)} ({root.replace(os.path.expanduser('~'), '~')}): {len(files)} files"
                 + (" (or more)" if len(files) >= MAX_FILES else "")]
        if langs:
            lines.append("Languages: " + ", ".join(f"{k} {v}" for k, v in sorted(langs.items(), key=lambda kv: -kv[1])[:8]))
        lines.append("Top level: " + ", ".join(f"{k}" + (f" ({v} files)" if k.endswith(os.sep) else "")
                                                for k, v in sorted(top.items(), key=lambda kv: (not kv[0].endswith(os.sep), kv[0]))[:40]))
        for note in self._manifests(root):
            lines.append(note)
        git = self._git(root)
        if git:
            lines.append(git)
        checks = [k for k in ("tests", "lint", "build") if self._command(root, k)[0]]
        if checks:
            lines.append("Checks I can run: " + ", ".join(checks) + " (run_project_check)")
        readme = next((f for f in ("README.md", "README.rst", "README.txt", "README") if os.path.isfile(os.path.join(root, f))), "")
        if readme:
            try:
                with open(os.path.join(root, readme), encoding="utf-8", errors="replace") as fh:
                    lines.append(f"{readme} (start):\n" + fh.read(1500).strip())
            except OSError:
                pass
        if len(files) <= 300:
            lines.append("Files:\n" + "\n".join(files))
        return _ok("\n".join(lines), root=root, files=len(files), languages=langs)

    def _manifests(self, root: str) -> List[str]:
        out = []
        pj = os.path.join(root, "package.json")
        if os.path.isfile(pj):
            try:
                with open(pj, encoding="utf-8") as f:
                    data = json.load(f)
                scripts = ", ".join(list((data.get("scripts") or {}).keys())[:12])
                out.append(f"package.json: {data.get('name') or ''}" + (f" -- scripts: {scripts}" if scripts else ""))
            except (OSError, ValueError):
                pass
        pp = os.path.join(root, "pyproject.toml")
        if os.path.isfile(pp):
            try:
                with open(pp, encoding="utf-8") as f:
                    text = f.read(20000)
                name = re.search(r'(?m)^name\s*=\s*"([^"]+)"', text)
                ver = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
                tools = [t for t in ("pytest", "ruff", "briefcase", "poetry", "flake8", "mypy", "black") if t in text]
                out.append("pyproject.toml: " + (name.group(1) if name else "") + (f" {ver.group(1)}" if ver else "")
                           + (f" -- uses {', '.join(tools)}" if tools else ""))
            except OSError:
                pass
        for f, label in (("Cargo.toml", "Rust (cargo)"), ("go.mod", "Go module"), ("pom.xml", "Maven"),
                         ("build.gradle", "Gradle"), ("build.gradle.kts", "Gradle"), ("pubspec.yaml", "Dart/Flutter"),
                         ("Gemfile", "Ruby (bundler)"), ("composer.json", "PHP (composer)"), ("requirements.txt", "pip requirements"),
                         ("Package.swift", "Swift package"), ("Makefile", "Makefile")):
            if os.path.isfile(os.path.join(root, f)):
                out.append(f"{f}: {label}")
        return out

    def _git(self, root: str) -> str:
        if not os.path.isdir(os.path.join(root, ".git")) or not shutil.which("git"):
            return ""
        ok, branch = run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
        ok2, status = run(["git", "-C", root, "status", "--porcelain"], timeout=15)
        ok3, last = run(["git", "-C", root, "log", "-1", "--pretty=%s (%cr)"], timeout=10)
        changed = [ln[3:] for ln in status.splitlines() if ln.strip()] if ok2 else []
        bits = [f"Git: branch {branch.strip()}" if ok else "Git"]
        if ok3 and last.strip():
            bits.append(f"last commit: {last.strip()[:120]}")
        bits.append(f"{len(changed)} changed file{'s' if len(changed) != 1 else ''}" + (": " + ", ".join(changed[:12]) if changed else ""))
        return " -- ".join(bits)

    # ---------------- search_code ----------------
    def search(self, text: str, which: str = "", regex: bool = False, glob: str = "") -> dict:
        root, why = self.root(which)
        if not root:
            return _no(why)
        text = str(text or "")
        if not text.strip():
            return _no("What should I look for in the code?")
        try:
            pat = re.compile(text if regex else re.escape(text), re.I)
        except re.error as exc:
            return _no(f"That pattern doesn't work ({exc}).")
        globs = [g.strip() for g in str(glob or "").split(",") if g.strip()]
        import fnmatch
        hits, scanned, started = [], 0, time.time()
        for rel in self._files(root):
            ext = os.path.splitext(rel)[1].lower()
            if globs and not any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(os.path.basename(rel), g) for g in globs):
                continue
            if not globs and ext not in TEXT_EXT:
                continue
            full = os.path.join(root, rel)
            try:
                if os.path.getsize(full) > 2_000_000:
                    continue
                with open(full, encoding="utf-8", errors="replace") as f:
                    for n, line in enumerate(f, 1):
                        if pat.search(line):
                            hits.append(f"{rel}:{n}: {line.strip()[:200]}")
                            if len(hits) >= MAX_MATCHES:
                                break
            except OSError:
                continue
            scanned += 1
            if len(hits) >= MAX_MATCHES or time.time() - started > 20:
                break
        if not hits:
            return _ok(f"No matches for “{text}” in {os.path.basename(root)} ({scanned} files searched).",
                       root=root, matches=[])
        more = " (the first ones -- search more precisely for the rest)" if len(hits) >= MAX_MATCHES else ""
        return _ok(f"{len(hits)} match{'es' if len(hits) != 1 else ''} in {os.path.basename(root)}{more}:\n" + "\n".join(hits),
                   root=root, matches=hits)

    # ---------------- run_project_check ----------------
    def _python(self, root: str) -> str:
        for venv in (".venv", "venv", "env"):
            exe = os.path.join(root, venv, "Scripts" if WIN else "bin", "python.exe" if WIN else "python")
            if os.path.isfile(exe):
                return exe
        return shutil.which("python3") or shutil.which("python") or ""

    def _command(self, root: str, kind: str) -> Tuple[Optional[List[str]], str]:
        """The project's own command for tests / lint / build, from its files only (never from the conversation)."""
        has = lambda f: os.path.exists(os.path.join(root, f))
        scripts = {}
        if has("package.json"):
            try:
                with open(os.path.join(root, "package.json"), encoding="utf-8") as f:
                    scripts = json.load(f).get("scripts") or {}
            except (OSError, ValueError):
                scripts = {}
        npm = shutil.which("npm")
        py = self._python(root) if (has("pyproject.toml") or has("setup.py") or has("requirements.txt")
                                    or any(f.endswith(".py") for f in os.listdir(root))) else ""
        if kind == "tests":
            if py and (has("tests") or has("test") or has("pytest.ini") or has("conftest.py")):
                return [py, "-m", "pytest", "-q", "-x", "--no-header"], "pytest"
            if npm and "test" in scripts and "no test specified" not in str(scripts["test"]):
                return [npm, "test", "--silent"], "npm test"
            if has("go.mod") and shutil.which("go"):
                return ["go", "test", "./..."], "go test"
            if has("Cargo.toml") and shutil.which("cargo"):
                return ["cargo", "test", "-q"], "cargo test"
            if has("gradlew") or has("gradlew.bat"):
                return [os.path.join(root, "gradlew.bat" if WIN else "gradlew"), "test", "-q"], "gradle test"
            if has("pom.xml") and shutil.which("mvn"):
                return ["mvn", "-q", "test"], "mvn test"
            if has("pubspec.yaml") and shutil.which("flutter"):
                return ["flutter", "test"], "flutter test"
            if has("Package.swift") and shutil.which("swift"):
                return ["swift", "test"], "swift test"
        if kind == "lint":
            if npm and "lint" in scripts and not has("pyproject.toml"):
                return [npm, "run", "lint", "--silent"], "npm run lint"
            if py and shutil.which("ruff"):
                return [shutil.which("ruff"), "check", "."], "ruff"
            if py:
                return [py, "-m", "compileall", "-q", "."], "python compile check"
            if npm and "lint" in scripts:
                return [npm, "run", "lint", "--silent"], "npm run lint"
            if has("go.mod") and shutil.which("go"):
                return ["go", "vet", "./..."], "go vet"
            if has("Cargo.toml") and shutil.which("cargo"):
                return ["cargo", "clippy", "-q"], "cargo clippy"
        if kind == "build":
            if npm and "build" in scripts:
                return [npm, "run", "build", "--silent"], "npm run build"
            if has("go.mod") and shutil.which("go"):
                return ["go", "build", "./..."], "go build"
            if has("Cargo.toml") and shutil.which("cargo"):
                return ["cargo", "build", "-q"], "cargo build"
            if has("gradlew") or has("gradlew.bat"):
                return [os.path.join(root, "gradlew.bat" if WIN else "gradlew"), "build", "-q"], "gradle build"
            if py:
                return [py, "-m", "compileall", "-q", "."], "python compile check"
        return None, ""

    def check(self, which: str = "", kind: str = "tests") -> dict:
        kind = str(kind or "tests").lower().strip()
        kind = {"test": "tests", "linter": "lint", "compile": "build"}.get(kind, kind)
        if kind not in ("tests", "lint", "build"):
            return _no("kind must be tests, lint or build.")
        root, why = self.root(which)
        if not root:
            return _no(why)
        cmd, label = self._command(root, kind)
        if not cmd:
            return _no(f"I couldn't find how to run the {kind} of {os.path.basename(root)} (no {kind} setup I recognise, "
                       "or its tool isn't installed).")
        started = time.time()
        import subprocess
        try:
            p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=CHECK_TIMEOUT,
                               env=dict(os.environ, CI="1", NO_COLOR="1", FORCE_COLOR="0", PYTHONDONTWRITEBYTECODE="1"),
                               **({"creationflags": 0x08000000} if WIN else {}))
            code, out = p.returncode, (p.stdout or "") + (p.stderr or "")
        except subprocess.TimeoutExpired:
            return _no(f"{label} took longer than {CHECK_TIMEOUT // 60} minutes, so I stopped it.")
        except OSError as exc:
            return _no(f"{label} couldn't start ({exc}).")
        out = re.sub(r"\x1b\[[0-9;]*m", "", out).strip()
        tail = out[-OUTPUT_TAIL:]
        secs = int(time.time() - started)
        if code == 0:
            return _ok(f"{label} passed in {os.path.basename(root)} ({secs} s).\n{tail[-1500:]}", root=root, command=label,
                       passed=True)
        return {"ok": True, "message": f"{label} FAILED in {os.path.basename(root)} (exit {code}, {secs} s). The end of "
                                       f"its output:\n{tail}", "root": root, "command": label, "passed": False}
