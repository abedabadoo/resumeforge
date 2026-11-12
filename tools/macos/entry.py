"""Frozen native macOS launch point. No web server is involved."""
from __future__ import annotations

import sys


def _smoke_test() -> int:
    """Exercise the bundled UI and packaged resources without an event loop."""
    import tempfile
    from pathlib import Path
    from PySide6.QtWidgets import QApplication
    from resumeforge.desktop_window import MainWindow

    app = QApplication.instance() or QApplication(["ResumeForge packaged smoke test"])
    with tempfile.TemporaryDirectory(prefix="resumeforge-mac-smoke-") as folder:
        window = MainWindow(Path(folder))
        window.show()
        app.processEvents()
        if not window.isVisible() or window.windowTitle() != "ResumeForge":
            raise RuntimeError("The packaged desktop window did not become visible")
        window.close()
        app.processEvents()
    print("ResumeForge packaged desktop smoke test passed", flush=True)
    return 0


if __name__ == "__main__":
    if "--package-smoke-test" in sys.argv:
        raise SystemExit(_smoke_test())
    from resumeforge.desktop import main
    raise SystemExit(main())
