"""A Mac updater must never trust unchecked assets or unsafe extracted paths."""
import hashlib
from pathlib import Path
import plistlib
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from resumeforge.mac_updates import ZIP_NAME, _bundle_check, _check_archive, _intel_macho, select_update


def release(tag, published, *, url=None, digest=None):
    asset = (f"https://github.com/abedabadoo/resumeforge/releases/download/"
             f"{tag}/{ZIP_NAME}") if url is None else url
    return {"tag_name": tag, "published_at": published, "draft": False,
            "assets": [{"name": ZIP_NAME, "size": 1234, "browser_download_url": asset,
                        "digest": digest or ("sha256:" + "a" * 64)}]}


class MacUpdaterTests(unittest.TestCase):
    def test_official_newer_release_selected_by_published_date(self):
        old = release("mac-intel-aabbccdd", "2026-11-01T00:00:00Z")
        new = release("mac-intel-11223344", "2026-11-12T00:00:00Z")
        self.assertEqual(select_update([old, new], old["tag_name"]).tag, new["tag_name"])
        self.assertIsNone(select_update([old, new], new["tag_name"]))

    def test_must_be_official_github_asset_with_verified_digest(self):
        current = "mac-intel-aabbccdd"
        harmful = [
            release("mac-intel-11223344", "2026-11-12T00:00:00Z",
                    url="https://example.org/ResumeForge-macOS-Intel.zip"),
            release("mac-intel-11223344", "2026-11-12T00:00:00Z",
                    digest="sha256:NOT-A-DIGEST"),
            release("mac-intel-11223344", "2026-11-12T00:00:00Z",
                    url="http://github.com/abedabadoo/resumeforge/releases/download/mac-intel-11223344/ResumeForge-macOS-Intel.zip"),
        ]
        self.assertIsNone(select_update(harmful, current))

    def test_archive_rejects_zip_slip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "unsafe.zip"
            with ZipFile(path, "w") as zipfile:
                zipfile.writestr("ResumeForge.app/../../malware", b"no")
            with self.assertRaises(ValueError):
                _check_archive(path)

    def test_archive_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "unsafe.zip"
            info = ZipInfo("ResumeForge.app/Contents/escape")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with ZipFile(path, "w") as zipfile:
                zipfile.writestr(info, "../../outside")
            with self.assertRaises(ValueError):
                _check_archive(path)

    def test_safe_bundle_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "safe.zip"
            with ZipFile(path, "w") as zipfile:
                zipfile.writestr("ResumeForge.app/Contents/Info.plist", b"plist")
                zipfile.writestr("ResumeForge.app/Contents/MacOS/ResumeForge", b"binary")
            _check_archive(path)

    def test_mach_o_cpu_detection_needs_no_apple_developer_tools(self):
        # CPU_ARCH_ABI64 | CPU_TYPE_X86, the same header as a thin Intel build.
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / "ResumeForge"
            binary.write_bytes(struct.pack("<II", 0xfeedfacf, 0x01000007)
                               + b"\0" * 24)
            self.assertTrue(_intel_macho(binary))
            # A valid ARM64 executable is not a suitable Intel update.
            binary.write_bytes(struct.pack("<II", 0xfeedfacf, 0x0100000C)
                               + b"\0" * 24)
            self.assertFalse(_intel_macho(binary))
            binary.write_bytes(b"not a Mach-O binary")
            with self.assertRaises(ValueError):
                _intel_macho(binary)

    def test_bundle_validation_never_calls_lipo_or_xcrun(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder) / "ResumeForge.app"
            binary = app / "Contents" / "MacOS" / "ResumeForge"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(struct.pack("<II", 0xfeedfacf, 0x01000007)
                               + b"\0" * 24)
            (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleIdentifier": "com.resumeforge.desktop",
                "CFBundleExecutable": "ResumeForge",
            }))
            with patch("resumeforge.mac_updates.subprocess.run") as runner:
                _bundle_check(app)
            args = [call.args[0] for call in runner.call_args_list]
            self.assertEqual(len(args), 1)
            self.assertEqual(args[0][0], "/usr/bin/codesign")
            self.assertFalse(any("lipo" in str(arg) or "xcrun" in str(arg)
                                 for arguments in args for arg in arguments))




if __name__ == "__main__":
    unittest.main()
