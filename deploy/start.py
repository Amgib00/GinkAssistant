"""Starts the Gink server (deploy/Dockerfile) as the unprivileged "gink" user, never as root.

Render (like most hosts) mounts the data disk at /var/data owned by root, so a container that starts as
"gink" straight away couldn't write the accounts database there. This starts as root only long enough
to hand the disk (and the database's folder) to "gink", then drops root for good -- groups, group and
user -- before the server runs. Started as any other user (docker run --user ...), it just runs.
"""
import os
import sys


def _own(folder: str, uid: int, gid: int) -> None:
    """Gives a folder and everything in it to the server's user (once: skipped when it's already theirs)."""
    if not folder or not os.path.isdir(folder) or os.stat(folder).st_uid == uid:
        return
    for root, dirs, files in os.walk(folder):
        for name in [root] + [os.path.join(root, n) for n in dirs + files]:
            try:
                os.chown(name, uid, gid, follow_symlinks=False)
            except OSError as exc:
                print(f"[Gink] couldn't hand {name} to the server's user ({type(exc).__name__})", flush=True)


def main() -> None:
    port = os.environ.get("PORT", "8000")
    args = ["uvicorn", "backend_server:app", "--host", "0.0.0.0", "--port", port]
    if os.name == "posix" and os.getuid() == 0:
        import pwd
        try:
            user = pwd.getpwnam("gink")
        except KeyError:
            sys.exit("[Gink] the image has no 'gink' user: rebuild it from deploy/Dockerfile")
        db = os.environ.get("GINK_DB_PATH", "").strip()
        for folder in {"/var/data", os.path.dirname(db) if db else "", os.environ.get("GINK_BLOB_DIR", "")}:
            _own(folder, user.pw_uid, user.pw_gid)
        os.setgroups([])
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)                     # from here on root is gone, and can't come back
        os.environ["HOME"] = user.pw_dir
    os.execvp(args[0], args)


if __name__ == "__main__":
    main()
