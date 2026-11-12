"""Build a standalone Intel macOS ResumeForge.app, ZIP, and DMG on an Intel Mac.

Requires Python 3.13, pip install -e '.[desktop]' pyinstaller.
The deliverables include the application runtime, not an LLM or Ollama.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEMO_PROFILE = ROOT / "tools/windows/demo.profile.json"


def execute(*args):
    print("+", " ".join(str(value) for value in args), flush=True)
    return subprocess.run([str(value) for value in args], check=True, text=True, capture_output=True).stdout.strip()


def build(out: Path, work: Path) -> tuple[Path, Path, Path]:
    if sys.platform != "darwin" or platform.machine() != "x86_64":
        raise RuntimeError("Build the Intel Mac package on a native x86_64 macOS runner.")
    if not DEMO_PROFILE.is_file():
        raise FileNotFoundError(DEMO_PROFILE)

    out = out.resolve()
    work = work.resolve()
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    sample = work / "resources" / "resumeforge" / "data" / "abu.profile.json"
    sample.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(DEMO_PROFILE, sample)

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "ResumeForge",
        "--target-arch", "x86_64",
        "--osx-bundle-identifier", "com.resumeforge.desktop",
        "--distpath", str(out),
        "--workpath", str(work / "pyinstaller"),
        "--specpath", str(work),
        # Collect only distributable assets: never bundle the developer's
        # resumeforge/data/abu.profile.json or other personal profiles.
        "--add-data", f"{sample}:resumeforge/data",
        "--add-data", f"{ROOT / 'resumeforge/data/risk-guard.json'}:resumeforge/data",
        "--add-data", f"{ROOT / 'resumeforge/fonts'}:resumeforge/fonts",
        "--add-data", f"{ROOT / 'resumeforge/static'}:resumeforge/static",
        "--add-data", f"{ROOT / 'licenses'}:licenses",
        # pdfium's native dylib is loaded through importlib rather than a
        # conventional Python import and must ship in the .app.
        "--collect-all", "pypdfium2_raw",
        str(HERE / "entry.py"),
    ]
    execute(*command)

    app = out / "ResumeForge.app"
    binary = app / "Contents" / "MacOS" / "ResumeForge"
    if not binary.is_file():
        raise FileNotFoundError(f"Missing packaged executable: {binary}")

    # PyInstaller can resolve an older libssl from setup-python's framework,
    # while cryptography's _rust wheel requires newer OpenSSL 3 symbols.
    # Bundle a matched, up-to-date OpenSSL pair from the Intel Homebrew formula
    # instead of relying on whatever is present on the target Mac.
    openssl = Path(execute("brew", "--prefix", "openssl@3")) / "lib"
    frameworks = app / "Contents" / "Frameworks"
    for name in ("libcrypto.3.dylib", "libssl.3.dylib"):
        source, dest = openssl / name, frameworks / name
        if not source.is_file() or not dest.is_file():
            raise FileNotFoundError(f"OpenSSL bundling prerequisite missing: {source} or {dest}")
        shutil.copy2(source, dest)
        execute("install_name_tool", "-id", f"@rpath/{name}", dest)
    ssl_symbols = execute("nm", "-gU", frameworks / "libssl.3.dylib")
    if "_SSL_get0_group_name" not in ssl_symbols:
        raise RuntimeError("Bundled OpenSSL is too old for the installed cryptography wheel")
    # Re-sign the modified frameworks and outer app with an ad-hoc signature.
    # This is NOT Apple Developer ID signing or notarization.
    execute("codesign", "--force", "--deep", "--sign", "-", app)
    execute("codesign", "--verify", "--deep", "--strict", app)
    architectures = execute("lipo", "-archs", binary).split()
    if architectures != ["x86_64"]:
        raise RuntimeError(f"Expected Intel-only executable, found {architectures}")

    matches = list(app.rglob("abu.profile.json"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one packaged sample profile, found {matches}")
    demo_digest = hashlib.sha256(DEMO_PROFILE.read_bytes()).digest()
    if hashlib.sha256(matches[0].read_bytes()).digest() != demo_digest:
        raise RuntimeError("Bundle contains an unexpected (possibly personal) starter profile")
    if not list(app.rglob("LiberationSans-Regular.ttf")):
        raise RuntimeError("PDF fonts are missing from the application")
    if not list(app.rglob("libpdfium.dylib")):
        raise RuntimeError("PDFium's macOS native library is missing")

    zip_path = out / "ResumeForge-macOS-Intel.zip"
    dmg_path = out / "ResumeForge-macOS-Intel.dmg"
    zip_path.unlink(missing_ok=True)
    dmg_path.unlink(missing_ok=True)
    # ditto preserves the symlinks and metadata in framework-based macOS apps.
    execute("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, zip_path)
    execute("hdiutil", "create", "-ov", "-format", "UDZO",
            "-volname", "ResumeForge Intel", "-srcfolder", app, dmg_path)

    with zipfile.ZipFile(zip_path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("The macOS ZIP did not pass integrity checking")
        if not any(path.startswith("ResumeForge.app/") for path in archive.namelist()):
            raise RuntimeError("The download is missing ResumeForge.app")
    for path in (zip_path, dmg_path):
        print(f"{path.name}: {path.stat().st_size:,} bytes; sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")
    return app, zip_path, dmg_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    build(args.out, args.work)
