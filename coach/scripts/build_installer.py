#!/usr/bin/env python3
"""Build dist/PromptCoachSetup.exe: the one file people download and double-click.

    python coach/scripts/build_installer.py            (needs:  pip install pyinstaller)

What it makes, in a work folder outside the repo (default ~/.prompt-coach-build):

    runtime/   coach.exe (hooks, chat helper, commands), coachw.exe (same, no console window),
               _internal/ (Python itself), library/, plugin-template/
    payload.zip                 the runtime, zipped
    PromptCoachSetup.exe        setup_app.py + payload.zip, as a single file -> copied to dist/

The installed coach needs nothing else on the computer: no Python, no Git.
Windows only (the setup program is a Windows program).
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(PLUGIN_ROOT)
sys.path.insert(0, HERE)

import installer  # noqa: E402
from pcoach import __version__  # noqa: E402

TEMPLATE_SKIP_DIRS = {"scripts", "tests", "evals", "library", "__pycache__", "dist"}

RUNTIME_SPEC = r'''# -*- mode: python ; coding: utf-8 -*-
a = Analysis([r"{scripts}\coach_app.py"], pathex=[r"{scripts}"],
             datas=[(r"{scripts}\pcoach\dashboard_page.html", "pcoach")],
             hiddenimports=["coach", "coach_mcp", "installer", "setup_desktop"],
             excludes=["tkinter", "setup_app", "unittest", "pydoc", "doctest", "test"], noarchive=False)
pyz = PYZ(a.pure)
console = EXE(pyz, a.scripts, [], exclude_binaries=True, name="coach", console=True, upx=False,
              version=r"{version_file}")
windowed = EXE(pyz, a.scripts, [], exclude_binaries=True, name="coachw", console=False, upx=False,
               version=r"{version_file}")
coll = COLLECT(console, windowed, a.binaries, a.datas, upx=False, name="runtime")
'''

SETUP_SPEC = r'''# -*- mode: python ; coding: utf-8 -*-
a = Analysis([r"{scripts}\setup_app.py"], pathex=[r"{scripts}"],
             datas=[(r"{payload}", ".")],
             hiddenimports=["installer", "setup_desktop"],
             excludes=["unittest", "pydoc", "doctest", "test"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="PromptCoachSetup", console=False, upx=False,
          version=r"{version_file}")
'''

VERSION_FILE = '''VSVersionInfo(
  ffi=FixedFileInfo(filevers=({v}, 0), prodvers=({v}, 0), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Amanda Rogers'),
      StringStruct('FileDescription', 'Prompt Coach'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'PromptCoach'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('ProductName', 'Prompt Coach'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
'''


def write_template(dest):
    """The plugin as the installer ships it: no Python scripts, commands name the program."""
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    count = 0
    for root, dirs, files in os.walk(PLUGIN_ROOT):
        rel = os.path.relpath(root, PLUGIN_ROOT)
        if rel == ".":
            dirs[:] = [d for d in dirs if d not in TEMPLATE_SKIP_DIRS]
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith((".pyc", ".pyo")) or (rel == "." and name == "README.md"):
                continue                      # (the README is for developers: it talks about Python and git)
            src = os.path.join(root, name)
            out = os.path.join(dest, rel, name)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            if name.endswith((".md", ".json")):
                with open(src, encoding="utf-8") as f:
                    text = installer.template_text(f.read())
                with open(out, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            else:
                shutil.copy2(src, out)
            count += 1
    leftovers = []
    for root, _dirs, files in os.walk(dest):
        for name in files:
            if name.endswith((".md", ".json")):
                with open(os.path.join(root, name), encoding="utf-8") as f:
                    if "run.sh" in f.read():
                        leftovers.append(os.path.relpath(os.path.join(root, name), dest))
    if leftovers:
        raise SystemExit("These plugin files still call run.sh (Python): %s" % ", ".join(leftovers))
    return count


def pyinstaller(spec, work, dist):
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
           "--workpath", work, "--distpath", dist, spec]
    subprocess.run(cmd, check=True, cwd=os.path.dirname(spec))


def zip_folder(folder, out):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                full = os.path.join(root, name)
                z.write(full, os.path.relpath(full, folder).replace(os.sep, "/"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build PromptCoachSetup.exe")
    ap.add_argument("--work", default=os.path.join(os.path.expanduser("~"), ".prompt-coach-build"))
    ap.add_argument("--out", default=os.path.join(REPO, "dist"))
    args = ap.parse_args(argv)
    if sys.platform != "win32":
        raise SystemExit("The setup program is a Windows program; build it on Windows.")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit("PyInstaller is missing. Run:  python -m pip install pyinstaller")

    work = os.path.abspath(args.work)
    os.makedirs(work, exist_ok=True)
    version_file = os.path.join(work, "version.txt")
    parts = (__version__.split(".") + ["0", "0"])[:3]
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(VERSION_FILE.format(v=", ".join(parts), version=__version__))

    fill = {"scripts": HERE, "version_file": version_file, "payload": os.path.join(work, "payload.zip")}
    runtime_spec = os.path.join(work, "runtime.spec")
    with open(runtime_spec, "w", encoding="utf-8") as f:
        f.write(RUNTIME_SPEC.format(**fill))
    dist = os.path.join(work, "dist")
    if os.path.isdir(dist):
        shutil.rmtree(dist)
    print("1/3 Building the coach (coach.exe)...")
    pyinstaller(runtime_spec, os.path.join(work, "build-runtime"), dist)
    runtime = os.path.join(dist, "runtime")
    os.makedirs(os.path.join(runtime, "library"), exist_ok=True)
    shutil.copy2(os.path.join(PLUGIN_ROOT, "library", "recommendations.md"), os.path.join(runtime, "library"))
    n = write_template(os.path.join(runtime, "plugin-template"))
    print("    plugin template: %d files" % n)

    print("2/3 Packing...")
    zip_folder(runtime, fill["payload"])

    print("3/3 Building the setup program...")
    setup_spec = os.path.join(work, "setup.spec")
    with open(setup_spec, "w", encoding="utf-8") as f:
        f.write(SETUP_SPEC.format(**fill))
    pyinstaller(setup_spec, os.path.join(work, "build-setup"), dist)

    os.makedirs(args.out, exist_ok=True)
    final = os.path.join(args.out, "PromptCoachSetup.exe")
    shutil.copy2(os.path.join(dist, "PromptCoachSetup.exe"), final)
    print("Wrote %s (%.1f MB), version %s" % (final, os.path.getsize(final) / 1e6, __version__))
    print("Runtime folder (for tests): %s" % runtime)
    return 0


if __name__ == "__main__":
    sys.exit(main())
