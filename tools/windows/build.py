"""Build the self-contained Windows x64 ZIP and optional per-user NSIS installer.

Run with Python 3.11+ and Go on Windows, Linux or macOS. The runtime and its
Windows wheels come exclusively from the versioned SHA-256 lock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import time
import urllib.request
from zipfile import ZIP_DEFLATED, ZipFile

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
QT_MODULES = {"QtCore", "QtGui", "QtWidgets", "QtNetwork"}
QT_PLUGINS = {"qwindows.dll", "qoffscreen.dll", "qminimal.dll", "qmodernwindowsstyle.dll",
              "qwindowsvistastyle.dll", "qico.dll", "qjpeg.dll", "qschannelbackend.dll",
              "qcertonlybackend.dll", "qnetworklistmanager.dll"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(item, cache):
    target = cache / item["name"]
    if target.name != item["name"]:
        raise ValueError(f"Unexpected archive name: {item['name']}")
    if target.is_file() and digest(target) == item["sha256"]:
        return target
    part = target.with_suffix(target.suffix + ".partial")
    print(f"Downloading {target.name}", flush=True)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(item["url"], timeout=90) as source, part.open("wb") as dest:
                shutil.copyfileobj(source, dest)
            if digest(part) != item["sha256"]:
                raise ValueError(f"SHA-256 mismatch: {target.name}")
            part.replace(target)
            return target
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def qt_file(parts):
    """Keep Qt Widgets, its native back ends, import support and notices."""
    if parts[0] != "PySide6":
        return True
    rest = parts[1:]
    if len(rest) == 1:
        name = rest[0]
        if name.endswith(".pyd"):
            return name[:-4] in QT_MODULES
        if name.startswith("Qt6") and name.endswith(".dll"):
            return "Qt" + name[3:-4] in QT_MODULES
        return name.startswith(("pyside6.abi3", "msvcp", "vcruntime", "concrt", "_")) or name.endswith(".json")
    if rest[0] == "plugins":
        return rest[-1].lower() in QT_PLUGINS
    return rest[0] == "support" or any("license" in p.lower() for p in rest)


def unpack(package, dest, *, wheel=False):
    with ZipFile(package) as z:
        for entry in z.infolist():
            if entry.is_dir():
                continue
            rel = PurePosixPath(entry.filename)
            if rel.is_absolute() or ".." in rel.parts or "\\" in entry.filename:
                raise ValueError(f"Unexpected archive member: {entry.filename}")
            parts = rel.parts
            if wheel:
                if parts[0].endswith(".data"):
                    if parts[1] not in {"purelib", "platlib"}:
                        continue
                    parts = parts[2:]
                if not qt_file(parts):
                    continue
            output = dest.joinpath(*parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            with z.open(entry) as src, output.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def verify(stage):
    runtime = stage / "runtime"
    lib = runtime / "Lib" / "site-packages"
    for file in [stage / "ResumeForge.exe", runtime / "python.exe", runtime / "pythonw.exe",
                 runtime / "python313.dll", lib / "PySide6/QtWidgets.pyd",
                 lib / "PySide6/Qt6Gui.dll", lib / "PySide6/QtNetwork.pyd", lib / "PySide6/Qt6Network.dll", lib / "PySide6/plugins/platforms/qwindows.dll",
                 lib / "pypdfium2_raw/pdfium.dll"]:
        with file.open("rb") as f:
            if f.read(2) != b"MZ":
                raise ValueError(f"Invalid PE file: {file}")
            f.seek(0x3c)
            offset = int.from_bytes(f.read(4), "little")
            f.seek(offset)
            if f.read(6) != b"PE\0\0\x64\x86":
                raise ValueError(f"Expected an x64 executable: {file}")
    for name in ("desktop.py", "desktop_window.py", "fonts/LiberationSans-Regular.ttf", "data/abu.profile.json"):
        if not (lib / "resumeforge" / name).is_file():
            raise ValueError(f"Missing application resource: {name}")


def make_zip(stage, outfile):
    temp = outfile.with_suffix(".partial.zip")
    with ZipFile(temp, "w", compression=ZIP_DEFLATED, compresslevel=6) as out:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                out.write(path, path.relative_to(stage.parent))
    with ZipFile(temp) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Corrupt archive member: {bad}")
    temp.replace(outfile)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--go", default=shutil.which("go"))
    ap.add_argument("--makensis", default=shutil.which("makensis"))
    args = ap.parse_args()
    if not args.go:
        ap.error("Install Go or pass --go with the path to its executable.")
    cache = args.work.resolve() / "downloads"
    cache.mkdir(exist_ok=True, parents=True)
    out = args.out.resolve()
    out.mkdir(exist_ok=True, parents=True)
    files = json.loads((HERE / "runtime-lock.json").read_text())["files"]
    with tempfile.TemporaryDirectory(prefix="desktop-stage-", dir=cache.parent) as folder:
        stage = Path(folder) / "ResumeForge"
        runtime = stage / "runtime"
        lib = runtime / "Lib/site-packages"
        for item in files:
            package = fetch(item, cache)
            wheel = package.suffix == ".whl"
            if not wheel and not package.name.endswith("-embed-amd64.zip"):
                raise ValueError(f"Unexpected download: {package}")
            unpack(package, lib if wheel else runtime, wheel=wheel)
        (runtime / "python313._pth").write_text("python313.zip\n.\nLib/site-packages\nimport site\n", encoding="ascii")
        shutil.copytree(PROJECT / "resumeforge", lib / "resumeforge",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        shutil.copytree(PROJECT / "licenses", runtime / "licenses")
        if (HERE / "licenses").is_dir():
            shutil.copytree(HERE / "licenses", runtime / "licenses", dirs_exist_ok=True)
        shutil.copyfile(HERE / "runtime-lock.json", runtime / "runtime-lock.json")
        subprocess.run([args.go, "build", "-trimpath", "-buildvcs=false", "-ldflags=-H=windowsgui -s -w -buildid=",
                        "-o", str(stage / "ResumeForge.exe"), str(HERE / "launcher.go")],
                       env={**os.environ, "CGO_ENABLED":"0", "GOOS":"windows", "GOARCH":"amd64"}, check=True)
        verify(stage)
        zip_path = out / "ResumeForge-Windows-x64.zip"
        make_zip(stage, zip_path)
        results = [zip_path]
        if args.makensis:
            setup = out / "ResumeForge-Setup-x64.exe"
            prefix = "/" if os.name == "nt" else "-"
            subprocess.run([args.makensis, prefix + "V2", f"{prefix}DSTAGE_DIR={stage}",
                            f"{prefix}DOUT_FILE={setup}", str(HERE / "installer.nsi")], check=True)
            results.append(setup)
        for file in results:
            print(f"{file.name}: {file.stat().st_size:,} bytes; SHA-256 {digest(file)}")


if __name__ == "__main__":
    main()
