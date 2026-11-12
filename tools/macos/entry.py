"""Launch the frozen macOS app with persistent startup diagnostics.

The normal Finder launch and the CI probe both call resumeforge.desktop.main.
Logs only contain startup diagnostics and tracebacks, not resume content.
"""
from __future__ import annotations

from datetime import datetime, timezone
import faulthandler
from pathlib import Path
import sys
import traceback


_LOG = None
_LOG_PATH = Path.home() / "Library" / "Logs" / "ResumeForge" / "startup.log"


def _diagnostics() -> None:
    global _LOG
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOG = _LOG_PATH.open("a", encoding="utf-8", buffering=1)
        if sys.stderr is None:
            sys.stderr = _LOG
        if sys.stdout is None:
            sys.stdout = _LOG
        faulthandler.enable(_LOG, all_threads=True)
        _record("Launching the Intel macOS desktop application")
    except OSError:
        _LOG = None


def _record(message: str) -> None:
    if _LOG is not None:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        print(f"[{timestamp}] {message}", file=_LOG, flush=True)


def _smoke_test() -> int:
    """Exercise bundled resources and UI without entering the regular main loop."""
    import tempfile
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
    _record("Packaged UI smoke test passed")
    print("ResumeForge packaged desktop smoke test passed", flush=True)
    return 0


def _normal_launch() -> int:
    """Run the same startup path used when the user double-clicks the .app."""
    probe = "--full-launch-smoke-test" in sys.argv
    if probe:
        sys.argv.remove("--full-launch-smoke-test")
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer

        app = QApplication.instance() or QApplication([sys.argv[0]])
        observed = []

        def check_window() -> None:
            observed.append(any(w.isVisible() and w.windowTitle() == "ResumeForge"
                                for w in app.topLevelWidgets()))
            app.quit()

        QTimer.singleShot(1000, check_window)

    _record("Beginning regular desktop startup")
    from resumeforge.desktop import main
    code = main()
    if probe:
        if code != 0 or observed != [True]:
            raise RuntimeError("Regular app launch did not keep a visible ResumeForge window")
        _record("Regular launch probe passed")
        print("ResumeForge regular launch probe passed", flush=True)
    else:
        _record(f"Application event loop exited with code {code}")
    return code


def main() -> int:
    _diagnostics()
    try:
        if "--package-smoke-test" in sys.argv:
            return _smoke_test()
        return _normal_launch()
    except BaseException:
        _record("STARTUP ERROR: " + traceback.format_exc())
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(None, "ResumeForge could not start",
                                     "A startup error occurred. Diagnostic details are saved to:\n"
                                     + str(_LOG_PATH))
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
