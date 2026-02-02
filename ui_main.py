# ui_main.py - Thin entry point for the Calibration Tracker GUI
#
# The UI layer has been extracted into the ui/ package:
#   ui/theme.py      - Theme definitions, fonts, global styling
#   ui/help_content.py - Help dialog and content
#   ui/models.py     - InstrumentTableModel, InstrumentFilterProxyModel, HighlightDelegate
#   ui/dialogs/      - All dialog classes
#   ui/main_window.py - MainWindow
#   ui/run.py        - run_gui()
#
# This file preserves the original import path for main.py.

from ui.run import run_gui

__all__ = ["run_gui"]
