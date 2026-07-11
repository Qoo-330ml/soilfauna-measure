"""Application entry point."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from soilfauna_measure import __app_name__, __version__
from soilfauna_measure.crash_handler import (
    install_crash_handler,
    set_emergency_save,
    write_session_note,
)
from soilfauna_measure.logging_config import setup_logging
from soilfauna_measure.resources import load_app_icon
from soilfauna_measure.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Start the Qt application. Returns process exit code."""
    setup_logging()
    log_dir = install_crash_handler()
    write_session_note(f"start {__app_name__} v{__version__}")
    argv = list(sys.argv if argv is None else argv)

    app = QApplication(argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("SoilFaunaMeasure")

    from soilfauna_measure.ui.theme import apply_theme

    apply_theme(app)

    app_icon = load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    window = MainWindow()
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    set_emergency_save(window.emergency_save)
    window.show()

    if len(argv) > 1:
        from pathlib import Path

        candidate = Path(argv[1]).expanduser()
        if candidate.is_dir():
            logger.info("Opening workspace from CLI: %s", candidate)
            window.load_workspace(candidate)
        else:
            logger.warning("CLI path is not a directory: %s", candidate)

    logger.info("%s started (logs: %s)", __app_name__, log_dir)
    code = app.exec()
    write_session_note(f"exit code={code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
