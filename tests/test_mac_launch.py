"""Mac Finder startup argument regressions, without importing Qt."""
import unittest
from unittest.mock import patch

from resumeforge.desktop import _launch_args


class FinderArgumentTests(unittest.TestCase):
    def test_strips_only_valid_finder_process_serial_number(self):
        values = ["-psn_0_12345", "--data-dir", "/tmp/resume workspace", "-psn_1_6789"]
        with patch("resumeforge.desktop.sys.platform", "darwin"):
            self.assertEqual(_launch_args(values), ["--data-dir", "/tmp/resume workspace"])
        self.assertEqual(len(values), 4)

    def test_unexpected_options_remain_visible_to_parser(self):
        with patch("resumeforge.desktop.sys.platform", "darwin"):
            self.assertEqual(_launch_args(["--incorrect-option", "-psn_invalid"]),
                             ["--incorrect-option", "-psn_invalid"])

    def test_windows_does_not_silently_drop_arguments(self):
        with patch("resumeforge.desktop.sys.platform", "win32"):
            self.assertEqual(_launch_args(["-psn_0_12345", "--data-dir", "."]),
                             ["-psn_0_12345", "--data-dir", "."])


if __name__ == "__main__":
    unittest.main()
