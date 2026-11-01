"""tools/check_mac_min_os.py reads the minimum macOS from real Mach-O load commands."""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import check_mac_min_os as c


def macho(cpu, minos=None, old_style=False, big=False):
    """A minimal 64-bit Mach-O: header + one version load command."""
    e = ">" if big else "<"
    cmds = b""
    if minos:
        v = (minos[0] << 16) | (minos[1] << 8)
        cmds = (struct.pack(e + "4I", 0x24, 16, v, v) if old_style
                else struct.pack(e + "6I", 0x32, 24, 1, v, v, 0))
    hdr = struct.pack(e + "8I", 0xFEEDFACF, cpu, 3, 6, 1 if cmds else 0, len(cmds), 0, 0)
    return hdr + cmds


def fat(*thins):
    out = struct.pack(">2I", 0xCAFEBABE, len(thins))
    offset, body = 4096, b""
    for cpu, data in thins:
        out += struct.pack(">5I", cpu, 3, offset + len(body), len(data), 12)
        body += data + b"\0" * (4096 - len(data) % 4096)
    return out + b"\0" * (4096 - len(out)) + body


X86, ARM = 0x01000007, 0x0100000C


def app(tmp_path, files):
    root = tmp_path / "Gink.app" / "Contents"
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return str(tmp_path / "Gink.app")


def test_reads_build_version_and_old_style(tmp_path):
    p = tmp_path / "a"; p.write_bytes(macho(X86, (10, 13)))
    assert c.slices(str(p)) == [("x86_64", (10, 13, 0))]
    p.write_bytes(macho(X86, (10, 9), old_style=True))
    assert c.slices(str(p)) == [("x86_64", (10, 9, 0))]
    p.write_bytes(b"#!/bin/sh\necho hi\n")
    assert c.slices(str(p)) == []


def test_catalina_app_passes(tmp_path):
    a = app(tmp_path, {
        "MacOS/Gink": fat((X86, macho(X86, (10, 15))), (ARM, macho(ARM, (11, 0)))),   # arm part may need 11
        "Resources/app_packages/numpy/_core/x.so": macho(X86, (10, 9)),
        "Resources/app/ginkassistant/app.py": b"print('hi')"})
    problems, checked = c.check(a, (10, 15, 0))
    assert problems == [] and checked == 2
    assert c.main([a, "--max", "10.15"]) == 0


def test_too_new_and_wrong_arch_fail(tmp_path):
    a = app(tmp_path, {
        "Resources/app_packages/scipy/linalg.so": macho(X86, (12, 0)),
        "Resources/app_packages/thing/arm_only.so": macho(ARM, (11, 0)),
        "Frameworks/Python.framework/Python": fat((X86, macho(X86, (10, 15))))})
    problems = dict(c.check(a, (10, 15, 0))[0])
    assert problems == {"Contents/Resources/app_packages/scipy/linalg.so": "needs macOS 12.0",
                        "Contents/Resources/app_packages/thing/arm_only.so": "has no x86_64 part (arm64 only)"}
    assert c.main([a]) == 1


def test_java_class_files_are_not_fat_binaries(tmp_path):
    p = tmp_path / "A.class"; p.write_bytes(struct.pack(">2I", 0xCAFEBABE, 52) + b"\0" * 40)
    assert c.slices(str(p)) == []


def test_empty_app_fails(tmp_path):
    a = app(tmp_path, {"Resources/readme.txt": b"x"})
    assert c.main([a]) == 1                                         # nothing checked = something's wrong
