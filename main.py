import sys
import os

from PyQt5.QtWidgets import QApplication, QSplashScreen, QMessageBox
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QFont, QPalette, QColor

from font_manager import FontManager
from project_manager import ProjectManager
from ui_main import MainWindow


def check_dependencies():
    missing = []
    try:
        import PyQt5
    except ImportError:
        missing.append("PyQt5")
    try:
        import cv2
    except ImportError:
        missing.append("opencv-python-headless")
    try:
        import numpy
    except ImportError:
        missing.append("numpy")
    try:
        import reportlab
    except ImportError:
        missing.append("reportlab")
    try:
        import skimage
    except ImportError:
        missing.append("scikit-image")
    try:
        import PIL
    except ImportError:
        missing.append("Pillow")
    return missing


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("LectureSnapPDF")
    app.setOrganizationName("LectureSnapPDF")
    app.setApplicationVersion("1.0")

    splash = QSplashScreen()
    splash.showMessage("LectureSnapPDF — Starting...",
                       Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    splash.show()
    app.processEvents()

    missing = check_dependencies()
    if missing:
        splash.close()
        QMessageBox.critical(
            None, "Missing Dependencies",
            f"Required packages not installed:\n{', '.join(missing)}\n\n"
            f"Run: pip install -r requirements.txt"
        )
        sys.exit(1)

    splash.showMessage("Checking fonts...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    app.processEvents()

    font_mgr = FontManager()

    def font_progress(current, total, message):
        splash.showMessage(
            f"Fonts: {message} ({current}/{total})",
            Qt.AlignBottom | Qt.AlignCenter,
            Qt.white
        )
        app.processEvents()

    font_mgr.download_fonts(progress_callback=font_progress)

    splash.showMessage("Checking for recovery...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    app.processEvents()

    proj_mgr = ProjectManager()
    recovery_data = proj_mgr.check_recovery()

    splash.showMessage("Loading application...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    app.processEvents()

    window = MainWindow(font_manager=font_mgr, project_manager=proj_mgr,
                        recovery_data=recovery_data)
    window.show()

    proj_mgr.enable_autosave()

    splash.finish(window)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
