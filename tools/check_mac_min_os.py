"""
Will this Mac app open on an older macOS? Reads every program and library inside a .app (the
Mach-O files) and reports any whose Intel part needs a newer macOS than you ask for.

    python tools/check_mac_min_os.py build/ginkassistant/macos/app/Gink.app --max 10.15

Exit code 1 if anything needs more than --max, or has no part for --arch at all (it couldn't load).
Pure Python: works on any computer (the Catalina CI job runs it on GitHub's Mac; the tests run it
on Linux with made-up files). Reads LC_BUILD_VERSION / LC_VERSION_MIN_MACOSX, which is what macOS
itself checks before loading a file.
"""
import argparse
import os
import struct
import sys

FAT_MAGIC, FAT_MAGIC_64 = 0xCAFEBABE, 0xCAFEBABF
MH_MAGIC, MH_MAGIC_64 = 0xFEEDFACE, 0xFEEDFACF
LC_VERSION_MIN_MACOSX, LC_BUILD_VERSION = 0x24, 0x32
PLATFORM_MACOS = 1
CPU = {7: "i386", 0x01000007: "x86_64", 12: "arm", 0x0100000C: "arm64"}


def _version(v: int) -> tuple:
    return (v >> 16, (v >> 8) & 0xFF, v & 0xFF)


def _thin_min_os(data: bytes, off: int):
    """(arch, (major, minor, patch) or None) for one Mach-O image starting at off."""
    magic_le = struct.unpack_from("<I", data, off)[0]
    if magic_le in (MH_MAGIC, MH_MAGIC_64):
        e = "<"
    elif struct.unpack_from(">I", data, off)[0] in (MH_MAGIC, MH_MAGIC_64):
        e = ">"
    else:
        return None
    magic, cputype, _sub, _ftype, ncmds, _size, _flags = struct.unpack_from(e + "7I", data, off)
    p = off + (32 if magic == MH_MAGIC_64 else 28)
    found = None
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from(e + "2I", data, p)
        if cmd == LC_BUILD_VERSION:
            platform, minos = struct.unpack_from(e + "2I", data, p + 8)
            if platform == PLATFORM_MACOS:
                found = _version(minos)
        elif cmd == LC_VERSION_MIN_MACOSX:
            found = _version(struct.unpack_from(e + "I", data, p + 8)[0])
        if cmdsize < 8:
            break
        p += cmdsize
    return CPU.get(cputype, hex(cputype)), found


def slices(path: str):
    """[(arch, min_os or None)] for a Mach-O file; [] if it isn't one."""
    with open(path, "rb") as f:
        head = f.read(8)
        if len(head) < 8:
            return []
        magic = struct.unpack(">I", head[:4])[0]
        if magic in (FAT_MAGIC, FAT_MAGIC_64):
            n = struct.unpack(">I", head[4:])[0]
            if n > 30:                                  # Java .class files share 0xCAFEBABE
                return []
            f.seek(0)
            data = f.read()
            out = []
            for i in range(n):
                if magic == FAT_MAGIC:
                    _ct, _st, offset, _sz, _al = struct.unpack_from(">5I", data, 8 + i * 20)
                else:
                    _ct, _st, offset, _sz, _al, _r = struct.unpack_from(">2I2QII", data, 8 + i * 32)
                one = _thin_min_os(data, offset)
                if one:
                    out.append(one)
            return out
        if struct.unpack("<I", head[:4])[0] in (MH_MAGIC, MH_MAGIC_64) or magic in (MH_MAGIC, MH_MAGIC_64):
            f.seek(0)
            one = _thin_min_os(f.read(), 0)
            return [one] if one else []
    return []


def check(app: str, max_os: tuple, arch: str = "x86_64"):
    """-> (problems, checked): problems = [(relative path, reason)]."""
    problems, checked = [], 0
    for root, _dirs, files in os.walk(app):
        for name in files:
            path = os.path.join(root, name)
            if os.path.islink(path):
                continue
            try:
                parts = slices(path)
            except (OSError, struct.error):
                continue
            if not parts:
                continue
            checked += 1
            rel = os.path.relpath(path, app)
            mine = [m for a, m in parts if a == arch]
            if not mine:
                problems.append((rel, f"has no {arch} part ({', '.join(a for a, _ in parts)} only)"))
            elif mine[0] and mine[0] > max_os:
                problems.append((rel, f"needs macOS {'.'.join(map(str, mine[0][:2]))}"))
    return problems, checked


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("app")
    ap.add_argument("--max", default="10.15", help="oldest macOS it must open on (default 10.15)")
    ap.add_argument("--arch", default="x86_64")
    a = ap.parse_args(argv)
    want = tuple(int(x) for x in a.max.split(".")) + (0,) * (3 - len(a.max.split(".")))
    problems, checked = check(a.app, want, a.arch)
    for rel, why in sorted(problems):
        print(f"  TOO NEW  {rel}: {why}")
    print(f"Checked {checked} programs and libraries: "
          + ("all open on macOS " + a.max if not problems else f"{len(problems)} won't open on macOS {a.max}"))
    return 1 if problems or not checked else 0


if __name__ == "__main__":
    sys.exit(main())
