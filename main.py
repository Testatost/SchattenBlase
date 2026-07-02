from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from config import DEFAULT_LANGUAGE
from i18n import I18n
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    i18n = I18n(DEFAULT_LANGUAGE)
    window = MainWindow(i18n)
    window.resize(1400, 850)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())