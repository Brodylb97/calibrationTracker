# ui/run.py - Application entry point and run_gui

from PyQt5 import QtWidgets, QtGui

from database import CalibrationRepository, get_effective_db_path
from ui.main_window import MainWindow
from ui.theme import _app_icon_path, apply_global_style


def run_gui(repo: CalibrationRepository) -> None:
    """Create and run the main application window."""
    app = QtWidgets.QApplication([])
    app.setOrganizationName("CalibrationTracker")
    app.setApplicationName("CalibrationTracker")
    icon_path = _app_icon_path()
    if icon_path.is_file():
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))
    apply_global_style(app)
    win = MainWindow(repo)
    try:
        from update_checker import install_update_check_into_main_window
        install_update_check_into_main_window(
            win,
            check_on_startup=True,
            get_db_path_for_restart=lambda: str(get_effective_db_path()),
        )
    except Exception:
        pass
    win.showMaximized()
    app.exec_()
