"""Windows updates accept only newer, verified official installers."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from resumeforge.windows_updates import INSTALLER_NAME, Update, check_for_update, prepare_update, select_update


def release(version, *, url=None, digest=None, size=1234, draft=False, prerelease=False):
    tag = f"v{version}"
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "assets": [{
            "name": INSTALLER_NAME,
            "size": size,
            "digest": digest or ("sha256:" + "a" * 64),
            "browser_download_url": url or (
                f"https://github.com/abedabadoo/resumeforge/releases/download/"
                f"{tag}/{INSTALLER_NAME}"),
        }],
    }


class WindowsUpdaterTests(unittest.TestCase):
    def test_checks_the_latest_stable_release(self):
        response = io.BytesIO(json.dumps(release("0.4.5")).encode("utf-8"))
        with patch("resumeforge.windows_updates.urllib.request.urlopen", return_value=response):
            self.assertEqual(check_for_update().tag, "v0.4.5")

    def test_selects_newest_published_windows_release_above_installed_version(self):
        releases = [release("0.4.2"), release("0.4.10"), release("0.4.3")]
        self.assertEqual(select_update(releases, "0.4.2").tag, "v0.4.10")
        self.assertIsNone(select_update(releases, "0.4.10"))

    def test_rejects_untrusted_or_unverifiable_assets(self):
        invalid = [
            release("0.4.4", url="https://example.org/ResumeForge-Setup-x64.exe"),
            release("0.4.4", url="http://github.com/abedabadoo/resumeforge/releases/download/v0.4.4/ResumeForge-Setup-x64.exe"),
            release("0.4.4", digest="sha256:invalid"),
            release("0.4.4", size=0),
            release("0.4.4", draft=True),
            release("0.4.4", prerelease=True),
            release("mac-intel-aabbccdd"),
        ]
        self.assertIsNone(select_update(invalid, "0.4.3"))

    def test_download_verifies_digest_and_removes_bad_payload(self):
        payload = b"test installer bytes"
        update = Update(
            tag="v0.4.4",
            url="https://github.com/abedabadoo/resumeforge/releases/download/v0.4.4/ResumeForge-Setup-x64.exe",
            sha256=hashlib.sha256(payload).hexdigest(),
            size=len(payload),
        )
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as cache:
            with patch("resumeforge.windows_updates.urllib.request.urlopen", return_value=io.BytesIO(payload)):
                prepared = prepare_update(update, cache_dir=Path(cache))
            self.assertEqual(prepared.installer.read_bytes(), payload)
            shutil.rmtree(prepared.temp_dir)

            corrupt = Update(update.tag, update.url, "0" * 64, update.size)
            with patch("resumeforge.windows_updates.urllib.request.urlopen", return_value=io.BytesIO(payload)):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    prepare_update(corrupt, cache_dir=Path(cache))


if __name__ == "__main__":
    unittest.main()
