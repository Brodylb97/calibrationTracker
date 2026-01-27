# ui_main.py

from datetime import datetime, date
import os
import sys
from pathlib import Path
import tempfile
import csv
from PyQt5 import QtWidgets, QtCore, QtGui
from database import CalibrationRepository
from lan_notify import send_due_reminders_via_lan


def _app_icon_path():
    """Path to cal_tracker.ico for window/taskbar icon. Works when run as script or frozen exe."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    return base / "cal_tracker.ico"


class HighlightDelegate(QtWidgets.QStyledItemDelegate):
    """Custom delegate that highlights search terms in table cells."""
    def __init__(self, search_text="", parent=None):
        super().__init__(parent)
        self.search_text = search_text.lower()
    
    def set_search_text(self, text):
        """Update the search text to highlight."""
        self.search_text = (text or "").lower().strip()
    
    def paint(self, painter, option, index):
        """Paint the cell with highlighted search text."""
        if not self.search_text or not index.isValid():
            # Use default painting if no search text
            super().paint(painter, option, index)
            return
        
        # Get the cell text
        text = str(index.data(QtCore.Qt.DisplayRole) or "")
        if not text:
            super().paint(painter, option, index)
            return
        
        # Check if search text is in this cell
        text_lower = text.lower()
        if self.search_text not in text_lower:
            # No match, use default painting
            super().paint(painter, option, index)
            return
        
        # Highlight the matching text
        option_copy = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(option_copy, index)
        
        # Get the text rect
        text_rect = option_copy.rect
        text_rect.adjust(4, 0, -4, 0)  # Add some padding
        
        # Draw background (preserve existing background colors for overdue items)
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            bg_color = index.data(QtCore.Qt.BackgroundRole)
            if bg_color:
                painter.fillRect(option.rect, bg_color)
            else:
                painter.fillRect(option.rect, option.palette.base())
        
        # Draw text with highlighting
        painter.save()
        painter.setPen(option.palette.text().color())
        
        # Find all occurrences of search text
        search_len = len(self.search_text)
        start_pos = 0
        highlights = []
        
        while True:
            pos = text_lower.find(self.search_text, start_pos)
            if pos == -1:
                break
            highlights.append((pos, pos + search_len))
            start_pos = pos + 1
        
        # Draw text with highlights
        font_metrics = painter.fontMetrics()
        x = text_rect.left()
        # Center text vertically
        y = text_rect.top() + font_metrics.ascent() + (text_rect.height() - font_metrics.height()) // 2
        
        # Get text color (may be colored for overdue items)
        text_color = index.data(QtCore.Qt.ForegroundRole)
        if not text_color:
            text_color = option.palette.text().color()
        
        current_pos = 0
        for start, end in highlights:
            # Draw text before highlight
            if current_pos < start:
                before_text = text[current_pos:start]
                painter.setPen(text_color)
                painter.drawText(x, y, before_text)
                x += font_metrics.width(before_text)
            
            # Draw highlighted text
            highlight_text = text[start:end]
            highlight_width = font_metrics.width(highlight_text)
            highlight_rect = QtCore.QRect(
                x, 
                text_rect.top() + 1,
                highlight_width,
                text_rect.height() - 2
            )
            
            # Draw highlight background (yellow)
            painter.fillRect(highlight_rect, QtGui.QColor("#FFD93D"))
            
            # Draw highlighted text (black for visibility on yellow)
            painter.setPen(QtGui.QColor("#000000"))
            painter.drawText(x, y, highlight_text)
            x += highlight_width
            
            current_pos = end
        
        # Draw remaining text
        if current_pos < len(text):
            remaining_text = text[current_pos:]
            painter.setPen(text_color)
            painter.drawText(x, y, remaining_text)
        
        painter.restore()


class HelpDialog(QtWidgets.QDialog):
    """Reusable help dialog that displays formatted help text."""
    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Help - {title}")
        self.resize(600, 500)
        
        # Ensure dialog can be shown multiple times and is window-modal
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        if parent:
            self.setWindowModality(QtCore.Qt.WindowModal)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title_label = QtWidgets.QLabel(f"<h2>{title}</h2>")
        layout.addWidget(title_label)
        
        # Content (scrollable)
        content_text = QtWidgets.QTextEdit()
        content_text.setReadOnly(True)
        content_text.setHtml(content)
        # Set word wrap to only break at word boundaries
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WordWrap)
        content_text.document().setDefaultTextOption(option)
        layout.addWidget(content_text)
        
        # Close button
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)


def get_help_content(dialog_type: str) -> tuple[str, str]:
    """
    Returns (title, html_content) for help dialogs.
    dialog_type should match the dialog class name or a descriptive string.
    """
    help_contents = {
        "InstrumentDialog": (
            "Instrument Dialog",
            """
            <h3>Creating or Editing an Instrument</h3>
            <p>Use this dialog to add a new instrument or edit an existing one.</p>
            
            <h4>Required Fields:</h4>
            <ul>
                <li><b>ID*</b>: Unique identifier for the instrument (e.g., "WS-001", "TH-002")</li>
                <li><b>Next due date*</b>: When the instrument's next calibration is due</li>
            </ul>
            
            <h4>Optional Fields:</h4>
            <ul>
                <li><b>Current location</b>: Where the instrument is currently located</li>
                <li><b>Instrument type</b>: Category of instrument (e.g., "Thermometer", "Pressure Gauge")</li>
                <li><b>Cal type</b>: 
                    <ul>
                        <li><b>SEND_OUT</b>: Instrument is sent out for calibration</li>
                        <li><b>PULL_IN</b>: Calibration is performed in-house</li>
                    </ul>
                </li>
                <li><b>Destination</b>: Calibration service provider (for SEND_OUT type)</li>
                <li><b>Last cal date</b>: Date of last calibration (automatically sets next due date to 1 year later)</li>
                <li><b>Status</b>: 
                    <ul>
                        <li><b>ACTIVE</b>: Instrument is in active use</li>
                        <li><b>RETIRED</b>: Instrument is no longer in use</li>
                        <li><b>OUT_FOR_CAL</b>: Instrument is currently out for calibration</li>
                    </ul>
                </li>
                <li><b>Notes</b>: Any additional information about the instrument</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>When you set the "Last cal date", the "Next due date" automatically updates to one year later</li>
                <li>Use consistent ID formats for easier searching and organization</li>
                <li>Update the location field when instruments are moved</li>
            </ul>
            """
        ),
        "SettingsDialog": (
            "Settings Dialog",
            """
            <h3>Application Settings</h3>
            <p>Configure application-wide settings and manage instrument types.</p>
            
            <h4>Tabs:</h4>
            <ul>
                <li><b>General</b>: General application preferences</li>
                <li><b>Instrument Types</b>: Manage instrument type categories
                    <ul>
                        <li>Click <b>Add</b> to create a new instrument type</li>
                        <li>Select a type and click <b>Edit</b> to modify it</li>
                        <li>Select a type and click <b>Delete</b> to remove it (only if no instruments use it)</li>
                    </ul>
                </li>
                <li><b>Reminders</b>: Configure calibration reminder settings
                    <ul>
                        <li><b>Reminder window (days)</b>: How many days before due date to send reminders</li>
                        <li>Configure LAN broadcast settings for network reminders</li>
                    </ul>
                </li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Create instrument types before adding instruments for better organization</li>
                <li>Set up reminder windows based on your calibration workflow</li>
            </ul>
            """
        ),
        "AttachmentsDialog": (
            "Attachments Dialog",
            """
            <h3>Managing Attachments</h3>
            <p>View and manage files attached to an instrument.</p>
            
            <h4>Actions:</h4>
            <ul>
                <li><b>Add</b>: Attach a new file to the instrument (PDFs, images, documents, etc.)</li>
                <li><b>Open</b>: Open the selected attachment file</li>
                <li><b>Delete</b>: Remove the selected attachment</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Attach calibration certificates for external calibrations</li>
                <li>Supported file types include PDF, images, and documents</li>
                <li>Attachments are stored in the attachments directory</li>
            </ul>
            """
        ),
        "DestinationEditDialog": (
            "Destination Dialog",
            """
            <h3>Calibration Destination</h3>
            <p>Add or edit a calibration destination (service provider or internal department).</p>
            
            <h4>Fields:</h4>
            <ul>
                <li><b>Name*</b>: Name of the calibration destination (required)</li>
            </ul>
            
            <h4>Usage:</h4>
            <p>Destinations are used for instruments with calibration type "SEND_OUT" to track where instruments are sent for calibration.</p>
            """
        ),
        "DestinationsDialog": (
            "Destinations Management",
            """
            <h3>Managing Calibration Destinations</h3>
            <p>View and manage all calibration destinations.</p>
            
            <h4>Actions:</h4>
            <ul>
                <li><b>Add</b>: Create a new calibration destination</li>
                <li><b>Edit</b>: Modify the selected destination</li>
                <li><b>Delete</b>: Remove the selected destination (only if no instruments use it)</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Create destinations before adding instruments that use them</li>
                <li>Use descriptive names (e.g., "ABC Calibration Services", "Internal Lab")</li>
            </ul>
            """
        ),
        "TemplateEditDialog": (
            "Calibration Template",
            """
            <h3>Creating or Editing a Calibration Template</h3>
            <p>Templates define the structure and fields for calibration records.</p>
            
            <h4>Fields:</h4>
            <ul>
                <li><b>Name*</b>: Template name (e.g., "Weather Station Calibration")</li>
                <li><b>Version*</b>: Version number (e.g., 1, 2, 3)</li>
                <li><b>Active</b>: Check to make template available for use</li>
                <li><b>Notes</b>: Template-wide notes that appear on all calibration records using this template</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Use descriptive template names that clearly identify the calibration procedure</li>
                <li>Increment version numbers when making significant changes</li>
                <li>Only active templates appear when creating calibrations</li>
                <li>After creating a template, use the "Fields" button to add calibration fields</li>
            </ul>
            """
        ),
        "FieldEditDialog": (
            "Template Field",
            """
            <h3>Creating or Editing a Template Field</h3>
            <p>Define a field that will appear in calibration forms.</p>
            
            <h4>Required Fields:</h4>
            <ul>
                <li><b>Name*</b>: Internal field name (used for matching in autofill)</li>
                <li><b>Label*</b>: Display label shown on the calibration form</li>
            </ul>
            
            <h4>Field Configuration:</h4>
            <ul>
                <li><b>Type</b>: Data type (text, number, bool/checkbox, date)</li>
                <li><b>Unit</b>: Unit of measurement (e.g., "°C", "psi", "V")</li>
                <li><b>Required</b>: Check if field must be filled during calibration</li>
                <li><b>Sort order</b>: Order in which fields appear (lower numbers first)</li>
                <li><b>Group</b>: Group name (fields with same group appear together on separate pages)</li>
            </ul>
            
            <h4>Calculations (Optional):</h4>
            <ul>
                <li><b>Calculation</b>: For computed fields
                    <ul>
                        <li><b>ABS_DIFF</b>: Absolute difference between two fields</li>
                        <li><b>PCT_ERROR</b>: Percentage error calculation</li>
                    </ul>
                </li>
                <li><b>Value 1 field</b>: First field for calculation</li>
                <li><b>Value 2 field</b>: Second field for calculation</li>
                <li><b>Tolerance</b>: Tolerance value for ABS_DIFF calculations</li>
            </ul>
            
            <h4>Autofill Feature:</h4>
            <ul>
                <li><b>Autofill from previous group</b>: If checked, this field will automatically fill matching fields in the next group when you navigate forward</li>
                <li>Fields match by name or label</li>
                <li>Useful when calibrating multiple similar points</li>
            </ul>
            """
        ),
        "TemplateFieldsDialog": (
            "Template Fields Management",
            """
            <h3>Managing Template Fields</h3>
            <p>View and manage all fields for a calibration template.</p>
            
            <h4>Actions:</h4>
            <ul>
                <li><b>Add</b>: Create a new field for this template</li>
                <li><b>Edit</b>: Modify the selected field</li>
                <li><b>Delete</b>: Remove the selected field</li>
                <li><b>Duplicate group</b>: Copy all fields from one group to create a new group</li>
            </ul>
            
            <h4>Table Columns:</h4>
            <ul>
                <li><b>Name</b>: Internal field name</li>
                <li><b>Label</b>: Display label</li>
                <li><b>Type</b>: Data type</li>
                <li><b>Unit</b>: Unit of measurement</li>
                <li><b>Required</b>: Whether field is required</li>
                <li><b>Sort</b>: Sort order</li>
                <li><b>Group</b>: Group name</li>
                <li><b>Calc</b>: Calculation type</li>
                <li><b>Tolerance</b>: Tolerance value</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Organize related fields into groups</li>
                <li>Use consistent naming for fields that should autofill</li>
                <li>Set appropriate sort orders to control field display sequence</li>
            </ul>
            """
        ),
        "CalibrationHistoryDialog": (
            "Calibration History",
            """
            <h3>Viewing Calibration History</h3>
            <p>View all calibration records for an instrument.</p>
            
            <h4>Table View:</h4>
            <ul>
                <li>Shows all calibration records with date, template, performed by, and result</li>
                <li>Select a record to view detailed information below</li>
            </ul>
            
            <h4>Details Panel:</h4>
            <ul>
                <li>Shows difference values per calibration point</li>
                <li>Displays template notes (if applicable)</li>
                <li>Shows all field values from the calibration</li>
            </ul>
            
            <h4>Actions:</h4>
            <ul>
                <li><b>➕ New Calibration</b>: Create a new calibration record</li>
                <li><b>👁️ View/Edit</b>: View or edit the selected calibration</li>
                <li><b>📄 Export PDF</b>: Export the selected calibration to PDF</li>
                <li><b>📎 Open File</b>: Open attached calibration file (if any)</li>
                <li><b>🗑️ Delete</b>: Delete the selected calibration record</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Use the details panel to review calibration data</li>
                <li>Export important calibrations to PDF for archival</li>
                <li>Attached files can be opened directly from here</li>
            </ul>
            """
        ),
        "TemplatesDialog": (
            "Calibration Templates",
            """
            <h3>Managing Calibration Templates</h3>
            <p>View and manage all calibration templates.</p>
            
            <h4>Actions:</h4>
            <ul>
                <li><b>New</b>: Create a new calibration template</li>
                <li><b>Edit</b>: Modify the selected template</li>
                <li><b>Delete</b>: Remove the selected template (only if no calibrations use it)</li>
                <li><b>Fields</b>: Manage fields for the selected template</li>
            </ul>
            
            <h4>Table Columns:</h4>
            <ul>
                <li><b>Name</b>: Template name</li>
                <li><b>Version</b>: Version number</li>
                <li><b>Active</b>: Whether template is available for use</li>
                <li><b>Notes</b>: Template notes</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Create templates for common calibration procedures</li>
                <li>Only active templates appear when creating calibrations</li>
                <li>Use the Fields button to configure what data is collected</li>
            </ul>
            """
        ),
        "CalibrationFormDialog": (
            "Calibration Form",
            """
            <h3>Recording a Calibration</h3>
            <p>Fill out a calibration form based on the selected template.</p>
            
            <h4>Navigation:</h4>
            <ul>
                <li>Use <b>Previous group</b> and <b>Next group</b> buttons to navigate between field groups</li>
                <li>The current group name is displayed on the right</li>
                <li>Fields are organized by groups defined in the template</li>
            </ul>
            
            <h4>Filling Out Fields:</h4>
            <ul>
                <li><b>Text/Number fields</b>: Type values directly</li>
                <li><b>Checkboxes</b>: Click to check/uncheck</li>
                <li><b>Date fields</b>: Click the calendar icon to select a date</li>
                <li><b>Computed fields</b>: Automatically calculated (read-only, shown in gray)</li>
            </ul>
            
            <h4>Autofill Feature:</h4>
            <ul>
                <li>If a field has autofill enabled, when you click "Next group", matching fields in the next group will automatically fill with values from the previous group</li>
                <li>Fields match by name or label</li>
                <li>This allows you to quickly copy values forward as you progress through multiple groups</li>
            </ul>
            
            <h4>Calibration Metadata:</h4>
            <ul>
                <li><b>Calibration date</b>: Date the calibration was performed</li>
                <li><b>Performed by</b>: Name of person who performed calibration</li>
                <li><b>Result</b>: PASS, FAIL, or CONDITIONAL</li>
                <li><b>Template Notes</b>: Permanent notes from the template (displayed at bottom, read-only)</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Required fields are marked with *</li>
                <li>Fill out all required fields before saving</li>
                <li>Use autofill to save time when calibrating multiple similar points</li>
                <li>Template notes are permanent and appear on all calibrations using that template</li>
            </ul>
            """
        ),
        "CalDateDialog": (
            "Set Calibration Date",
            """
            <h3>Setting Calibration Date</h3>
            <p>Quickly set the last calibration date for an instrument.</p>
            
            <h4>Usage:</h4>
            <ul>
                <li>Select a date using the calendar picker</li>
                <li>Click <b>OK</b> to set the date</li>
                <li>The next due date will automatically update to one year later</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Use this for quick date updates without opening the full edit dialog</li>
                <li>The calendar popup makes date selection easy</li>
            </ul>
            """
        ),
        "InstrumentInfoDialog": (
            "Instrument Information",
            """
            <h3>Viewing Instrument Details</h3>
            <p>View comprehensive information about an instrument.</p>
            
            <h4>Information Displayed:</h4>
            <ul>
                <li>All instrument fields (ID, location, type, status, etc.)</li>
                <li>Calibration dates and days remaining</li>
                <li>Instrument notes</li>
                <li>Attachment count</li>
            </ul>
            
            <h4>Actions:</h4>
            <ul>
                <li><b>Change history</b>: View the audit log of all changes made to this instrument</li>
                <li><b>Close</b>: Close the dialog</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Use this dialog for a quick overview of instrument information</li>
                <li>Check the change history to see when and what was modified</li>
            </ul>
            """
        ),
        "AuditLogDialog": (
            "Change History",
            """
            <h3>Viewing Change History</h3>
            <p>View the audit log of all changes made to an instrument.</p>
            
            <h4>Information Displayed:</h4>
            <ul>
                <li>Date and time of each change</li>
                <li>User who made the change</li>
                <li>Field that was changed</li>
                <li>Old value and new value</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Use this to track all modifications to an instrument</li>
                <li>Helps with compliance and audit requirements</li>
                <li>Changes are automatically logged when you edit instruments</li>
            </ul>
            """
        ),
    }
    
    return help_contents.get(dialog_type, ("Help", "<p>Help content not available.</p>"))


class InstrumentTableModel(QtCore.QAbstractTableModel):
    # Displayed columns (DB primary key is kept internally)
    HEADERS = [
        "ID",              # tag_number
        "Location",        # current location
        "Type",            # calibration_type (SEND_OUT / PULL_IN)
        "Destination",
        "Last Cal",
        "Next Due",
        "Days Left",
        "Status",
        "Instrument type",  # was "Notes"
    ]

    
    def sort(self, column, order=QtCore.Qt.AscendingOrder):
        reverse = (order == QtCore.Qt.DescendingOrder)

        def sort_key(inst):
            if column == 0:      # ID
                return inst.get("tag_number") or ""
            elif column == 1:    # Location
                return inst.get("location") or ""
            elif column == 2:    # Type (calibration_type)
                return inst.get("calibration_type") or ""
            elif column == 3:    # Destination
                return inst.get("destination_name") or ""
            elif column == 4:    # Last Cal
                ...
            elif column == 5:    # Next Due
                ...
            elif column == 6:    # Days Left
                ...
            elif column == 7:    # Status
                return inst.get("status") or ""
            elif column == 8:    # Instrument type
                return inst.get("instrument_type_name") or ""
            return ""

        self.layoutAboutToBeChanged.emit()
        self.instruments.sort(key=sort_key, reverse=reverse)
        self.layoutChanged.emit()

    def __init__(self, instruments=None, parent=None):
        super().__init__(parent)
        self.instruments = instruments or []

    def rowCount(self, parent=None):
        return len(self.instruments)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        inst = self.instruments[row]

        # Color coding for overdue instruments
        if role == QtCore.Qt.BackgroundRole:
            days_left = None
            nd = inst.get("next_due_date")
            if nd:
                try:
                    d = datetime.strptime(nd, "%Y-%m-%d").date()
                    days_left = (d - date.today()).days
                except Exception:
                    pass
            
            if days_left is not None:
                if days_left < 0:
                    # Overdue - dark red background
                    return QtGui.QColor(80, 30, 30)
                elif days_left <= 7:
                    # Due soon - dark yellow/orange background
                    return QtGui.QColor(80, 70, 30)
                elif days_left <= 30:
                    # Due within month - subtle orange tint
                    return QtGui.QColor(60, 50, 40)
            return None
        
        if role == QtCore.Qt.ForegroundRole:
            days_left = None
            nd = inst.get("next_due_date")
            if nd:
                try:
                    d = datetime.strptime(nd, "%Y-%m-%d").date()
                    days_left = (d - date.today()).days
                except Exception:
                    pass
            
            if days_left is not None and days_left < 0:
                # Overdue - orange/red text for visibility
                return QtGui.QColor("#FF6B6B")
            elif days_left is not None and days_left <= 7:
                # Due soon - yellow text
                return QtGui.QColor("#FFD93D")
            return None

        if role == QtCore.Qt.DisplayRole:
            if col == 0:   # ID (user-facing)
                return inst["tag_number"]
            elif col == 1:  # Location
                return inst.get("location", "")
            elif col == 2:  # Type (calibration_type)
                return inst.get("calibration_type", "")
            elif col == 3:  # Destination
                return inst.get("destination_name", "")
            elif col == 4:  # Last Cal
                return inst.get("last_cal_date", "")
            elif col == 5:  # Next Due
                return inst.get("next_due_date", "")
            elif col == 6:  # Days Left
                nd = inst.get("next_due_date")
                if nd:
                    try:
                        d = datetime.strptime(nd, "%Y-%m-%d").date()
                        return (d - date.today()).days
                    except Exception:
                        return ""
                return ""
            elif col == 7:  # Status
                return inst.get("status", "")
            elif col == 8:  # Instrument type (name)
                return inst.get("instrument_type_name", "") or ""   

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            return self.HEADERS[section]
        return section + 1

    def set_instruments(self, instruments):
        self.beginResetModel()
        self.instruments = instruments
        self.endResetModel()

    def get_instrument_id(self, row):
        if 0 <= row < len(self.instruments):
            # DB primary key, not shown in table
            return self.instruments[row]["id"]
        return None


class InstrumentDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, instrument=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.instrument = instrument
        self.setWindowTitle("Instrument" + (" - Edit" if instrument else " - New"))

        form = QtWidgets.QFormLayout(self)
        self.resize(500, 500)


        # ID field
        self.id_edit = QtWidgets.QLineEdit()

        # Current location field
        self.location_edit = QtWidgets.QLineEdit()

        # Instrument type
        self.instrument_type_combo = QtWidgets.QComboBox()
        self.instrument_type_combo.addItem("", None)
        for t in self.repo.list_instrument_types():
            self.instrument_type_combo.addItem(t["name"], t["id"])

        # Calibration type (match DB CHECK constraint: 'SEND_OUT' / 'PULL_IN')
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["SEND_OUT", "PULL_IN"])

        # Destination
        self.dest_combo = QtWidgets.QComboBox()
        self.dest_combo.addItem("", None)
        for d in self.repo.list_destinations():
            self.dest_combo.addItem(d["name"], d["id"])

        # Last and next due dates
        self.last_cal_date = QtWidgets.QDateEdit(calendarPopup=True)
        self.last_cal_date.setDisplayFormat("yyyy-MM-dd")
        self.last_cal_date.setDate(QtCore.QDate.currentDate())

        self.next_due_date = QtWidgets.QDateEdit(calendarPopup=True)
        self.next_due_date.setDisplayFormat("yyyy-MM-dd")
        self.next_due_date.setDate(QtCore.QDate.currentDate())

        # Whenever last_cal_date changes, auto-set next_due_date = +1 year
        self.last_cal_date.dateChanged.connect(self._update_next_due_from_last)
        self._update_next_due_from_last()

        self.status_combo = QtWidgets.QComboBox()
        self.status_combo.addItems(["ACTIVE", "RETIRED", "OUT_FOR_CAL"])

        self.notes_edit = QtWidgets.QPlainTextEdit()
        # Set word wrap to only break at word boundaries
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WordWrap)
        self.notes_edit.document().setDefaultTextOption(option)

        form.addRow("ID*", self.id_edit)
        form.addRow("Current location", self.location_edit)
        form.addRow("Instrument type", self.instrument_type_combo)
        form.addRow("Cal type", self.type_combo)
        form.addRow("Destination", self.dest_combo)
        form.addRow("Last cal date", self.last_cal_date)
        form.addRow("Next due date*", self.next_due_date)
        form.addRow("Status", self.status_combo)
        form.addRow("Notes", self.notes_edit)

        # Add helpful hints
        hint_label = QtWidgets.QLabel(
            "<small><i>Tip: Last calibration date automatically sets next due date to 1 year later</i></small>"
        )
        hint_label.setWordWrap(True)
        form.addRow("", hint_label)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(lambda: self._show_help())
        form.addRow(btn_box)

        if instrument:
            self._load_instrument()
        else:
            # Set focus to first field for new instruments
            self.id_edit.setFocus()
    
    def _show_help(self):
        title, content = get_help_content("InstrumentDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def _update_next_due_from_last(self):
        """Set next_due_date to exactly 1 year after last_cal_date."""
        qd = self.last_cal_date.date()
        next_qd = qd.addYears(1)
        self.next_due_date.setDate(next_qd)

    def _load_instrument(self):
        inst = self.instrument
        self.id_edit.setText(inst.get("tag_number", ""))
        self.location_edit.setText(inst.get("location", ""))

        # Instrument type
        inst_type_id = inst.get("instrument_type_id")
        if inst_type_id is not None:
            for i in range(self.instrument_type_combo.count()):
                if self.instrument_type_combo.itemData(i) == inst_type_id:
                    self.instrument_type_combo.setCurrentIndex(i)
                    break

        # Calibration type
        t = inst.get("calibration_type") or "SEND_OUT"
        idx = self.type_combo.findText(t)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)

        # Destination
        dest_id = inst.get("destination_id")
        if dest_id is not None:
            for i in range(self.dest_combo.count()):
                if self.dest_combo.itemData(i) == dest_id:
                    self.dest_combo.setCurrentIndex(i)
                    break

        # Dates
        def set_date(widget, value):
            if value:
                try:
                    d = datetime.strptime(value, "%Y-%m-%d").date()
                    widget.setDate(QtCore.QDate(d.year, d.month, d.day))
                except Exception:
                    pass

        set_date(self.last_cal_date, inst.get("last_cal_date"))
        set_date(self.next_due_date, inst.get("next_due_date"))

        # Status
        st = inst.get("status", "ACTIVE")
        idx = self.status_combo.findText(st)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)

        # Notes
        self.notes_edit.setPlainText(inst.get("notes", ""))

    def get_data(self):
        instrument_id = self.id_edit.text().strip()
        if not instrument_id:
            QtWidgets.QMessageBox.warning(self, "Validation", "ID is required.")
            return None

        next_due_str = self.next_due_date.date().toString("yyyy-MM-dd")
        last_str = self.last_cal_date.date().toString("yyyy-MM-dd")

        data = {
            "tag_number": instrument_id,
            "serial_number": "",  # not used
            "description": "",    # not used
            "location": self.location_edit.text().strip(),
            "calibration_type": self.type_combo.currentText(),
            "destination_id": self.dest_combo.currentData(),
            "last_cal_date": last_str,
            "next_due_date": next_due_str,
            "frequency_months": 12,
            "status": self.status_combo.currentText(),
            "notes": self.notes_edit.toPlainText().strip(),
            "instrument_type_id": self.instrument_type_combo.currentData(),
        }
        return data


class SettingsDialog(QtWidgets.QDialog):
    """Settings dialog with improved layout and tooltips."""
    """
    Simple settings: reminder window only (LAN broadcast doesn't need SMTP)
    """
    def __init__(self, repo: CalibrationRepository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Settings")

        layout = QtWidgets.QVBoxLayout(self)

        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs)

        # Reminders tab
        rem_widget = QtWidgets.QWidget()
        rem_form = QtWidgets.QFormLayout(rem_widget)

        self.reminder_days_spin = QtWidgets.QSpinBox()
        self.reminder_days_spin.setRange(1, 365)
        self.reminder_days_spin.setValue(
            int(self.repo.get_setting("reminder_days", 14))
        )

        self.operator_edit = QtWidgets.QLineEdit(
            self.repo.get_setting("operator_name", "")
        )

        hint = QtWidgets.QLabel(
            "Number of days ahead to include in LAN reminder broadcasts."
        )
        hint.setWordWrap(True)

        rem_form.addRow("Reminder days", self.reminder_days_spin)
        rem_form.addRow("Operator name", self.operator_edit)
        rem_form.addRow(hint)

        tabs.addTab(rem_widget, "Reminders")

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        layout.addWidget(btn_box)

        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(lambda: self._show_help())
    
    def _show_help(self):
        title, content = get_help_content("SettingsDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def accept(self):
        self.repo.set_setting(
            "reminder_days", str(self.reminder_days_spin.value())
        )
        self.repo.set_setting(
            "operator_name", self.operator_edit.text().strip()
        )
        super().accept()

class AttachmentsDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, instrument_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.instrument_id = instrument_id
        self.setWindowTitle("Attachments")

        layout = QtWidgets.QVBoxLayout(self)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Filename", "Path", "Uploaded"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_open = QtWidgets.QPushButton("Open")
        self.btn_delete = QtWidgets.QPushButton("Delete")
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

        self.btn_add.clicked.connect(self._add_attachment)
        self.btn_open.clicked.connect(self._open_attachment)
        self.btn_delete.clicked.connect(self._delete_attachment)
        
        # Add Help button
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Help | QtWidgets.QDialogButtonBox.Close)
        btn_box.helpRequested.connect(lambda: self._show_help())
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)
        
        self._load_attachments()
    
    def _show_help(self):
        title, content = get_help_content("AttachmentsDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def _load_attachments(self):
        atts = self.repo.list_attachments(self.instrument_id)
        self.table.setRowCount(len(atts))
        for row, a in enumerate(atts):
            item_name = QtWidgets.QTableWidgetItem(a["filename"])
            item_path = QtWidgets.QTableWidgetItem(a["file_path"])
            item_upload = QtWidgets.QTableWidgetItem(a["uploaded_at"])
            item_name.setData(QtCore.Qt.UserRole, a["id"])
            self.table.setItem(row, 0, item_name)
            self.table.setItem(row, 1, item_path)
            self.table.setItem(row, 2, item_upload)

    def _add_attachment(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select file"
        )
        if not path:
            return
        try:
            self.repo.add_attachment(self.instrument_id, path)
            self._load_attachments()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error adding attachment", str(e)
            )

    def _open_attachment(self):
        row = self.table.currentRow()
        if row < 0:
            return

        # We stored the attachment id in the first column's UserRole
        item_name = self.table.item(row, 0)
        if not item_name:
            return

        att_id = item_name.data(QtCore.Qt.UserRole)
        if not att_id:
            return

        att = self.repo.get_attachment(att_id)
        if not att:
            return

        file_data = att.get("file_data")
        filename = att.get("filename") or "attachment.bin"
        stored_path = att.get("file_path")

        if file_data:
            # Write the blob to a temp file and open it
            temp_dir = Path(tempfile.gettempdir()) / "cal_tracker_attachments"
            temp_dir.mkdir(parents=True, exist_ok=True)

            temp_path = temp_dir / filename
            try:
                with temp_path.open("wb") as f:
                    f.write(file_data)

                QtGui = __import__("PyQt5.QtGui", fromlist=["QtGui"]).QtGui
                QtGui.QDesktopServices.openUrl(
                    QtCore.QUrl.fromLocalFile(str(temp_path))
                )
                return
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self, "Error opening attachment", str(e)
                )
                return

        # Fallback: if for some reason file_data is NULL but we still have a path
        if stored_path:
            QtGui = __import__("PyQt5.QtGui", fromlist=["QtGui"]).QtGui
            QtGui.QDesktopServices.openUrl(
                QtCore.QUrl.fromLocalFile(stored_path)
            )
        else:
            QtWidgets.QMessageBox.warning(
                self,
                "Attachment missing",
                "No stored file data or path available for this attachment.",
            )
    
    def _delete_attachment(self):
        row = self.table.currentRow()
        if row < 0:
            return

        item_name = self.table.item(row, 0)
        if not item_name:
            return

        att_id = item_name.data(QtCore.Qt.UserRole)
        if not att_id:
            return

        fname = item_name.text() or "this file"
        resp = QtWidgets.QMessageBox.question(
            self,
            "Delete attachment",
            f"Delete attachment '{fname}'?",
        )
        if resp != QtWidgets.QMessageBox.Yes:
            return

        try:
            self.repo.delete_attachment(att_id)
            self._load_attachments()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error deleting attachment", str(e)
            )


class DestinationEditDialog(QtWidgets.QDialog):
    def __init__(self, dest=None, parent=None):
        super().__init__(parent)
        self.dest = dest or {}
        self.setWindowTitle("Destination")

        form = QtWidgets.QFormLayout(self)

        self.name_edit = QtWidgets.QLineEdit(self.dest.get("name", ""))
        self.contact_edit = QtWidgets.QLineEdit(self.dest.get("contact", ""))
        self.email_edit = QtWidgets.QLineEdit(self.dest.get("email", ""))
        self.phone_edit = QtWidgets.QLineEdit(self.dest.get("phone", ""))
        self.addr_edit = QtWidgets.QPlainTextEdit(self.dest.get("address", ""))
        # Set word wrap to only break at word boundaries
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WordWrap)
        self.addr_edit.document().setDefaultTextOption(option)

        form.addRow("Name*", self.name_edit)
        form.addRow("Contact", self.contact_edit)
        form.addRow("Email", self.email_edit)
        form.addRow("Phone", self.phone_edit)
        form.addRow("Address", self.addr_edit)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(lambda: self._show_help())
        form.addRow(btn_box)
    
    def _show_help(self):
        title, content = get_help_content("DestinationEditDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def get_data(self):
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Validation", "Name is required.")
            return None
        data = {
            "name": name,
            "contact": self.contact_edit.text().strip(),
            "email": self.email_edit.text().strip(),
            "phone": self.phone_edit.text().strip(),
            "address": self.addr_edit.toPlainText().strip(),
        }
        return data


class DestinationsDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Destinations")

        layout = QtWidgets.QVBoxLayout(self)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Contact", "Email", "Phone", "Address"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        layout.addWidget(self.table)

        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_edit = QtWidgets.QPushButton("Edit")
        self.btn_delete = QtWidgets.QPushButton("Delete")
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

        self.btn_add.clicked.connect(self.on_add)
        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_delete.clicked.connect(self.on_delete)
        
        # Add Help button
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Help | QtWidgets.QDialogButtonBox.Close)
        btn_box.helpRequested.connect(lambda: self._show_help())
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

        self._load_destinations()
    
    def _show_help(self):
        title, content = get_help_content("DestinationsDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def _load_destinations(self):
        dests = self.repo.list_destinations_full()
        self.table.setRowCount(len(dests))
        for row, d in enumerate(dests):
            item_name = QtWidgets.QTableWidgetItem(d["name"])
            item_name.setData(QtCore.Qt.UserRole, d["id"])
            item_contact = QtWidgets.QTableWidgetItem(d.get("contact") or "")
            item_email = QtWidgets.QTableWidgetItem(d.get("email") or "")
            item_phone = QtWidgets.QTableWidgetItem(d.get("phone") or "")
            item_addr = QtWidgets.QTableWidgetItem(d.get("address") or "")

            self.table.setItem(row, 0, item_name)
            self.table.setItem(row, 1, item_contact)
            self.table.setItem(row, 2, item_email)
            self.table.setItem(row, 3, item_phone)
            self.table.setItem(row, 4, item_addr)

    def _selected_row(self):
        idx = self.table.currentRow()
        return idx if idx >= 0 else None

    def _selected_dest_id(self):
        row = self._selected_row()
        if row is None:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(QtCore.Qt.UserRole)

    def on_add(self):
        dlg = DestinationEditDialog(parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            data = dlg.get_data()
            if data:
                self.repo.add_destination(**data)
                self._load_destinations()

    def on_edit(self):
        row = self._selected_row()
        if row is None:
            return
        dest_id = self._selected_dest_id()
        if dest_id is None:
            return

        # Pull current values from the table
        dest = {
            "id": dest_id,
            "name": self.table.item(row, 0).text(),
            "contact": self.table.item(row, 1).text(),
            "email": self.table.item(row, 2).text(),
            "phone": self.table.item(row, 3).text(),
            "address": self.table.item(row, 4).text(),
        }

        dlg = DestinationEditDialog(dest=dest, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            data = dlg.get_data()
            if data:
                self.repo.update_destination(dest_id, data)
                self._load_destinations()

    def on_delete(self):
        dest_id = self._selected_dest_id()
        row = self._selected_row()
        if dest_id is None or row is None:
            return
        name = self.table.item(row, 0).text()
        resp = QtWidgets.QMessageBox.question(
            self,
            "Delete destination",
            f"Delete destination '{name}'?",
        )
        if resp == QtWidgets.QMessageBox.Yes:
            try:
                self.repo.delete_destination(dest_id)
                self._load_destinations()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))
                
class TemplateEditDialog(QtWidgets.QDialog):
    def __init__(self, template=None, parent=None):
        super().__init__(parent)
        # Store template - ensure it's a dict
        self.template = template if template and isinstance(template, dict) else {}
        is_edit_mode = bool(self.template and self.template.get("id"))
        self.setWindowTitle("Template" + (" - Edit" if is_edit_mode else " - New"))

        form = QtWidgets.QFormLayout(self)

        # Get template values with fallbacks
        template_name = str(self.template.get("name", "") or "")
        try:
            template_version = int(self.template.get("version") or 1)
        except (ValueError, TypeError):
            template_version = 1
        template_is_active = bool(int(self.template.get("is_active", 1)))
        template_notes = str(self.template.get("notes", "") or "")
        
        self.name_edit = QtWidgets.QLineEdit(template_name)
        self.version_spin = QtWidgets.QSpinBox()
        self.version_spin.setRange(1, 999)
        self.version_spin.setValue(template_version)
        self.active_check = QtWidgets.QCheckBox("Active")
        # default active=True for new template
        self.active_check.setChecked(template_is_active)
        
        # Create notes editor and set word wrap, then set text
        self.notes_edit = QtWidgets.QPlainTextEdit()
        # Set word wrap to only break at word boundaries
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WordWrap)
        self.notes_edit.document().setDefaultTextOption(option)
        # Set the text after configuring the document
        if template_notes:
            self.notes_edit.setPlainText(template_notes)

        form.addRow("Name*", self.name_edit)
        form.addRow("Version", self.version_spin)
        form.addRow("", self.active_check)
        form.addRow("Notes", self.notes_edit)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(lambda: self._show_help())
        form.addRow(btn_box)
        
        # Ensure dialog is properly sized and visible
        self.setMinimumSize(400, 300)
        self.resize(500, 400)
        
        # Explicitly ensure values are set (in case of any initialization issues)
        if self.template:
            self._load_template_data()
    
    def _load_template_data(self):
        """Explicitly load template data into widgets."""
        if not self.template:
            return
        
        # Set name - try multiple possible key names
        name = self.template.get("name") or self.template.get("Name") or ""
        if name:
            self.name_edit.setText(str(name))
            self.name_edit.repaint()
        
        # Set version - handle both int and string
        version = self.template.get("version") or self.template.get("Version") or 1
        try:
            if isinstance(version, str):
                version = int(version)
            else:
                version = int(version)
            self.version_spin.setValue(version)
            self.version_spin.repaint()
        except (ValueError, TypeError):
            self.version_spin.setValue(1)
        
        # Set active status - handle both int and bool
        is_active = self.template.get("is_active") or self.template.get("IsActive")
        if is_active is None:
            is_active = 1  # Default to active
        is_active = bool(int(is_active)) if isinstance(is_active, (int, str)) else bool(is_active)
        self.active_check.setChecked(is_active)
        self.active_check.repaint()
        
        # Set notes
        notes = self.template.get("notes") or self.template.get("Notes") or ""
        if notes:
            self.notes_edit.setPlainText(str(notes))
            self.notes_edit.repaint()
    
    def showEvent(self, event):
        """Override showEvent to ensure dialog is properly displayed."""
        super().showEvent(event)
        # Force layout update and ensure widgets are visible
        self.adjustSize()
        self.updateGeometry()
        # Ensure all widgets are shown
        for widget in self.findChildren(QtWidgets.QWidget):
            widget.show()
        # Reload template data after dialog is shown to ensure values are displayed
        if self.template:
            QtCore.QTimer.singleShot(0, self._load_template_data)
    
    def _show_help(self):
        title, content = get_help_content("TemplateEditDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def get_data(self):
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Validation", "Name is required.")
            return None
        return {
            "name": name,
            "version": self.version_spin.value(),
            "is_active": self.active_check.isChecked(),
            "notes": self.notes_edit.toPlainText().strip(),
        }

class FieldEditDialog(QtWidgets.QDialog):
    def __init__(self, field=None, existing_fields=None, parent=None):
        super().__init__(parent)
        self.field = field or {}
        self.existing_fields = existing_fields or []
        self.setWindowTitle("Field" + (" - Edit" if field else " - New"))

        form = QtWidgets.QFormLayout(self)

        self.name_edit = QtWidgets.QLineEdit(self.field.get("name", ""))
        self.label_edit = QtWidgets.QLineEdit(self.field.get("label", ""))

        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["text", "number", "bool", "date", "signature"])
        dt = self.field.get("data_type") or "text"
        idx = self.type_combo.findText(dt)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        
        # Signature selection dropdown (shown when type is signature)
        self.signature_combo = QtWidgets.QComboBox()
        self.signature_combo.addItem("", None)  # Empty option
        self._load_signatures()
        
        # Show/hide signature combo based on type selection
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self._on_type_changed(self.type_combo.currentText())
        
        # Set selected signature if editing
        if dt == "signature":
            sig_filename = self.field.get("default_value") or ""
            if sig_filename:
                idx = self.signature_combo.findData(sig_filename)
                if idx >= 0:
                    self.signature_combo.setCurrentIndex(idx)

        self.unit_edit = QtWidgets.QLineEdit(self.field.get("unit") or "")
        self.required_check = QtWidgets.QCheckBox("Required")
        self.required_check.setChecked(bool(self.field.get("required", 0)))

        self.sort_spin = QtWidgets.QSpinBox()
        self.sort_spin.setRange(0, 9999)
        self.sort_spin.setValue(int(self.field.get("sort_order", 0)))

        self.group_edit = QtWidgets.QLineEdit(self.field.get("group_name") or "")

        # Computation parameters
        self.calc_type_combo = QtWidgets.QComboBox()
        self.calc_type_combo.addItem("None", None)
        self.calc_type_combo.addItem("Abs difference between two fields", "ABS_DIFF")
        self.calc_type_combo.addItem(
            "Percent error (|V1 - V2| / |V2| * 100)", "PCT_ERROR"
        )

        self.ref1_combo = QtWidgets.QComboBox()
        self.ref2_combo = QtWidgets.QComboBox()
        for cb in (self.ref1_combo, self.ref2_combo):
            cb.addItem("", None)
            for f in self.existing_fields:
                cb.addItem(f["name"], f["name"])

        calc_type = self.field.get("calc_type")
        ref1 = self.field.get("calc_ref1_name")
        ref2 = self.field.get("calc_ref2_name")

        if calc_type:
            idx = self.calc_type_combo.findData(calc_type)
            if idx >= 0:
                self.calc_type_combo.setCurrentIndex(idx)

        def set_cb_from_name(cb, name):
            if not name:
                return
            for i in range(cb.count()):
                if cb.itemData(i) == name:
                    cb.setCurrentIndex(i)
                    break

        set_cb_from_name(self.ref1_combo, ref1)
        set_cb_from_name(self.ref2_combo, ref2)

        # Tolerance (used with ABS_DIFF)
        self.tol_spin = QtWidgets.QDoubleSpinBox()
        self.tol_spin.setDecimals(6)
        self.tol_spin.setRange(0.0, 1e9)
        tol_val = self.field.get("tolerance")
        if tol_val is not None:
            try:
                self.tol_spin.setValue(float(tol_val))
            except Exception:
                pass

        form.addRow("Name* (internal)", self.name_edit)
        form.addRow("Label* (shown)", self.label_edit)
        form.addRow("Type", self.type_combo)
        self.signature_label = QtWidgets.QLabel("Signature")
        form.addRow(self.signature_label, self.signature_combo)
        form.addRow("Unit", self.unit_edit)
        form.addRow("", self.required_check)
        form.addRow("Sort order", self.sort_spin)
        form.addRow("Group", self.group_edit)
        form.addRow("Calculation", self.calc_type_combo)
        form.addRow("Value 1 field", self.ref1_combo)
        form.addRow("Value 2 field", self.ref2_combo)
        form.addRow("Tolerance (for ABS diff)", self.tol_spin)
        
        # Autofill option
        self.autofill_check = QtWidgets.QCheckBox("Autofill from previous group")
        self.autofill_check.setChecked(bool(self.field.get("autofill_from_first_group", 0)))
        form.addRow("", self.autofill_check)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(lambda: self._show_help())
        form.addRow(btn_box)
    
    def _load_signatures(self):
        """Load available signatures from the Signatures folder."""
        import os
        from pathlib import Path
        
        signatures_dir = Path("Signatures")
        if not signatures_dir.exists():
            return
        
        # Get all image files (png, jpg, jpeg, gif, bmp)
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp'}
        for file_path in signatures_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                # Use filename (without extension) as display name
                name = file_path.stem
                # Store full filename as data
                self.signature_combo.addItem(name, file_path.name)
    
    def _on_type_changed(self, data_type: str):
        """Show/hide signature dropdown based on selected type."""
        is_signature = (data_type == "signature")
        if hasattr(self, 'signature_combo') and hasattr(self, 'signature_label'):
            self.signature_combo.setVisible(is_signature)
            self.signature_label.setVisible(is_signature)
    
    def _show_help(self):
        title, content = get_help_content("FieldEditDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def get_data(self):
        name = self.name_edit.text().strip()
        label = self.label_edit.text().strip()
        if not name or not label:
            QtWidgets.QMessageBox.warning(
                self, "Validation", "Name and label are required."
            )
            return None

        calc_type = self.calc_type_combo.currentData()
        ref1_name = self.ref1_combo.currentData()
        ref2_name = self.ref2_combo.currentData()

        if calc_type in ("ABS_DIFF", "PCT_ERROR"):
            if not ref1_name or not ref2_name or ref1_name == ref2_name:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Validation",
                    "For this calculation, select two different source fields.",
                )
                return None

        tol = None
        if calc_type in ("ABS_DIFF", "PCT_ERROR"):
            tval = self.tol_spin.value()
            if tval > 0:
                tol = tval

        data_type = self.type_combo.currentText()
        default_value = None
        if data_type == "signature":
            default_value = self.signature_combo.currentData()
        
        return {
            "name": name,
            "label": label,
            "data_type": data_type,
            "unit": self.unit_edit.text().strip() or None,
            "required": self.required_check.isChecked(),
            "sort_order": self.sort_spin.value(),
            "group_name": self.group_edit.text().strip() or None,
            "calc_type": calc_type,
            "calc_ref1_name": ref1_name,
            "calc_ref2_name": ref2_name,
            "tolerance": tol,
            "autofill_from_first_group": self.autofill_check.isChecked(),
            "default_value": default_value,  # Store signature filename for signature fields
        }

class TemplateFieldsDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, template_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.template_id = template_id

        tpl = self.repo.get_template(template_id)
        self.setWindowTitle(f"Fields - {tpl['name']} (v{tpl['version']})")
        self.resize(900, 500)

        layout = QtWidgets.QVBoxLayout(self)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Label", "Type", "Unit", "Required", "Sort", "Group", "Calc", "Tolerance"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.table)

        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_edit = QtWidgets.QPushButton("Edit")
        self.btn_delete = QtWidgets.QPushButton("Delete")
        self.btn_dup_group = QtWidgets.QPushButton("Duplicate group")
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_dup_group)
        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)

        # Connect button signals BEFORE adding to layout
        self.btn_add.clicked.connect(self.on_add)
        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_delete.clicked.connect(self.on_delete)
        self.btn_dup_group.clicked.connect(self.on_dup_group)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Help | QtWidgets.QDialogButtonBox.Close)
        btn_box.helpRequested.connect(lambda: self._show_help())
        btn_box.rejected.connect(self.reject)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)
        
        # Load fields immediately after setup
        self._load_fields()
    
    def showEvent(self, event):
        """Override showEvent to ensure table refreshes quickly when dialog opens."""
        super().showEvent(event)
        # Force immediate refresh of the table
        self.table.viewport().update()
        QtWidgets.QApplication.processEvents()
    
    def _show_help(self):
        title, content = get_help_content("TemplateFieldsDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

    def _load_fields(self):
        # Disable table updates while loading for better performance
        self.table.setUpdatesEnabled(False)
        try:
            fields = self.repo.list_template_fields(self.template_id)
            self._fields_cache = fields

            self.table.setRowCount(len(fields))
            
            # Helper function for creating table items
            def mk(text):
                return QtWidgets.QTableWidgetItem(text)
            
            for row, f in enumerate(fields):
                it_name = mk(f.get("name", ""))
                it_name.setData(QtCore.Qt.UserRole, f["id"])

                calc_desc = ""
                if f.get("calc_type") == "ABS_DIFF":
                    r1 = f.get("calc_ref1_name") or "?"
                    r2 = f.get("calc_ref2_name") or "?"
                    calc_desc = f"|{r1} - {r2}|"
                elif f.get("calc_type") == "PCT_ERROR":
                    r1 = f.get("calc_ref1_name") or "?"
                    r2 = f.get("calc_ref2_name") or "?"
                    calc_desc = f"|{r1} - {r2}| / |{r2}| * 100"

                tol = f.get("tolerance")
                tol_txt = "" if tol is None else str(tol)

                self.table.setItem(row, 0, it_name)
                self.table.setItem(row, 1, mk(f.get("label", "")))
                self.table.setItem(row, 2, mk(f.get("data_type", "")))
                self.table.setItem(row, 3, mk(f.get("unit") or ""))
                self.table.setItem(row, 4, mk("Yes" if f.get("required") else ""))
                self.table.setItem(row, 5, mk(str(f.get("sort_order", 0))))
                self.table.setItem(row, 6, mk(f.get("group_name") or ""))
                self.table.setItem(row, 7, mk(calc_desc))
                self.table.setItem(row, 8, mk(tol_txt))
        finally:
            # Re-enable updates and refresh the table
            self.table.setUpdatesEnabled(True)
            self.table.viewport().update()
            QtWidgets.QApplication.processEvents()

    def _selected_field_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(QtCore.Qt.UserRole)

    def on_add(self):
        fields = self.repo.list_template_fields(self.template_id)
        dlg = FieldEditDialog(existing_fields=fields, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        data = dlg.get_data()
        if not data:
            return
        self.repo.add_template_field(
            self.template_id,
            data["name"],
            data["label"],
            data["data_type"],
            data["unit"],
            data["required"],
            data["sort_order"],
            data["group_name"],
            data["calc_type"],
            data["calc_ref1_name"],
            data["calc_ref2_name"],
            data["tolerance"],
            data.get("autofill_from_first_group", False),
        )
        self._load_fields()

    def on_edit(self):
        field_id = self._selected_field_id()
        if not field_id:
            return
        fields = self.repo.list_template_fields(self.template_id)
        field = next((f for f in fields if f["id"] == field_id), None)
        if not field:
            return
        dlg = FieldEditDialog(field=field, existing_fields=fields, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        data = dlg.get_data()
        if not data:
            return
        data["id"] = field_id
        self.repo.update_template_field(field_id, data)
        self._load_fields()

    def on_delete(self):
        field_id = self._selected_field_id()
        if not field_id:
            return
        resp = QtWidgets.QMessageBox.question(
            self, "Delete field", "Delete this field?"
        )
        if resp != QtWidgets.QMessageBox.Yes:
            return
        self.repo.delete_template_field(field_id)
        self._load_fields()

    def on_dup_group(self):
        fields = self.repo.list_template_fields(self.template_id)
        if not fields:
            return

        # All existing group names
        groups = sorted({f.get("group_name") or "" for f in fields})
        groups = [g for g in groups if g]

        if not groups:
            QtWidgets.QMessageBox.information(
                self,
                "No groups",
                "There are no group names defined to duplicate.",
            )
            return

        # Choose source group
        src_group, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Source group",
            "Duplicate which group?",
            groups,
            0,
            False,
        )
        if not ok or not src_group:
            return

        # New group name
        new_group, ok = QtWidgets.QInputDialog.getText(
            self,
            "New group name",
            "New group name:",
            text=f"{src_group} copy",
        )
        if not ok or not new_group.strip():
            return
        new_group = new_group.strip()

        # Optional suffix replacement for internal names (e.g. '_1' -> '_2')
        old_suffix, ok = QtWidgets.QInputDialog.getText(
            self,
            "Internal name suffix (optional)",
            "Replace this text in internal names (e.g. _1):",
            text="",
        )
        if not ok:
            return
        new_suffix = ""
        if old_suffix:
            new_suffix, ok = QtWidgets.QInputDialog.getText(
                self,
                "New suffix",
                "With this text (e.g. _2):",
                text="",
            )
            if not ok:
                return

        # Source fields in that group
        source_fields = [f for f in fields if (f.get("group_name") == src_group)]
        if not source_fields:
            return

        # Base of the source group (e.g. 100)
        group_min = min((f.get("sort_order") or 0) for f in source_fields)
        block_size = 100
        new_block_start = ((group_min // block_size) + 1) * block_size

        for f in source_fields:
            old_sort = f.get("sort_order") or 0
            offset = old_sort - group_min
            new_sort = new_block_start + offset

            name = f["name"]
            label = f["label"]
            if old_suffix and new_suffix:
                name = name.replace(old_suffix, new_suffix)
                label = label.replace(old_suffix, new_suffix)

            calc_type = f.get("calc_type")
            ref1 = f.get("calc_ref1_name")
            ref2 = f.get("calc_ref2_name")
            tol = f.get("tolerance")

            if calc_type == "ABS_DIFF" and old_suffix and new_suffix:
                if ref1:
                    ref1 = ref1.replace(old_suffix, new_suffix)
                if ref2:
                    ref2 = ref2.replace(old_suffix, new_suffix)

            self.repo.add_template_field(
                self.template_id,
                name,
                label,
                f["data_type"],
                f.get("unit"),
                bool(f.get("required")),
                new_sort,
                new_group,
                calc_type,
                ref1,
                ref2,
                tol,
                bool(f.get("autofill_from_first_group", 0)),
            )

        self._load_fields()


class CalibrationHistoryDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, instrument_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.instrument_id = instrument_id

        inst = self.repo.get_instrument(instrument_id)
        tag = inst.get("tag_number", str(instrument_id)) if inst else str(instrument_id)
        self.setWindowTitle(f"Calibration History - {tag}")
        self.resize(900, 600)

        layout = QtWidgets.QVBoxLayout(self)

        # Instrument info label
        info = []
        if inst:
            info.append(f"ID: {inst.get('tag_number', '')}")
            if inst.get("location"):
                info.append(f"Location: {inst['location']}")
            if inst.get("last_cal_date"):
                info.append(f"Last cal: {inst['last_cal_date']}")
        info_label = QtWidgets.QLabel(" | ".join(info))
        layout.addWidget(info_label)

        # Table of records (no Result column)
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Template", "Performed by", "Result"]
        )
        
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.table)

        # Details area for differences
        layout.addWidget(QtWidgets.QLabel("Difference values (per point):"))
        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(170)
        # Set word wrap to only break at word boundaries
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WordWrap)
        self.details.document().setDefaultTextOption(option)
        layout.addWidget(self.details)

        # Buttons with better organization and tooltips
        btn_layout = QtWidgets.QHBoxLayout()
        
        # Primary actions
        self.btn_new = QtWidgets.QPushButton("➕ New Calibration")
        self.btn_new.setToolTip("Create a new calibration record")
        self.btn_view = QtWidgets.QPushButton("✏️ View/Edit")
        self.btn_view.setToolTip("View or edit the selected calibration")
        self.btn_export_pdf = QtWidgets.QPushButton("📄 Export PDF")
        self.btn_export_pdf.setToolTip("Export selected calibration to PDF")
        
        # Secondary actions
        self.btn_open_file = QtWidgets.QPushButton("📎 Open File")
        self.btn_open_file.setToolTip("Open attached calibration file")
        self.btn_delete_file = QtWidgets.QPushButton("🗑️ Delete")
        self.btn_delete_file.setToolTip("Delete the selected calibration record")
        
        # Close button
        self.btn_close = QtWidgets.QPushButton("Close")
        self.btn_close.setDefault(True)

        btn_layout.addWidget(self.btn_new)
        btn_layout.addWidget(self.btn_view)
        btn_layout.addWidget(self.btn_export_pdf)
        btn_layout.addSpacing(10)
        btn_layout.addWidget(self.btn_open_file)
        btn_layout.addWidget(self.btn_delete_file)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

        self.btn_new.clicked.connect(self.on_new_cal)
        self.btn_view.clicked.connect(self.on_view_edit)
        self.btn_export_pdf.clicked.connect(self.on_export_pdf)
        self.btn_open_file.clicked.connect(self.on_open_file)
        self.btn_delete_file.clicked.connect(self.on_delete_file)
        self.btn_close.clicked.connect(self.accept)

        self.table.itemSelectionChanged.connect(self._update_details)

        self._load_records()
    
    def on_open_file(self):
        atts = self._attachments_for_selected_record()
        if not atts:
            QtWidgets.QMessageBox.information(
                self,
                "No file",
                "No external calibration file is attached to this record.",
            )
            return

        # If multiple, just open the first; you can fancy it up later
        att = atts[0]
        path = att.get("file_path")
        if not path:
            QtWidgets.QMessageBox.warning(
                self,
                "Missing file",
                "This attachment has no stored file path.",
            )
            return

        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    def on_delete_file(self):
        """
        Now deletes the entire calibration record (including any attached files),
        not just the document.
        """
        rec_id = self._selected_record_id()
        if not rec_id:
            return

        # Get a bit of context for the confirmation dialog
        row = self.table.currentRow()
        cal_date = ""
        tpl_name = ""
        if row >= 0:
            item_date = self.table.item(row, 0)
            item_tpl = self.table.item(row, 1)
            if item_date:
                cal_date = item_date.text()
            if item_tpl:
                tpl_name = item_tpl.text()

        desc = cal_date or f"Record #{rec_id}"
        if tpl_name:
            desc += f" ({tpl_name})"

        resp = QtWidgets.QMessageBox.question(
            self,
            "Delete calibration entry",
            f"Delete calibration entry:\n\n{desc}\n\n"
            "This will also delete any attached external files.\n"
            "This cannot be undone.",
        )
        if resp != QtWidgets.QMessageBox.Yes:
            return

        try:
            self.repo.delete_calibration_record(rec_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error deleting calibration entry",
                str(e),
            )
            return

        # Refresh list & details
        self._load_records()
        self._update_details()

    def _attachments_for_selected_record(self):
        rec_id = self._selected_record_id()
        if not rec_id:
            return []
        return self.repo.list_attachments_for_record(rec_id)


    def _ensure_external_template(self, instrument_type_id: int) -> dict | None:
        """
        Ensure a simple 'External calibration (file only)' template exists
        for this instrument type. Return the template row as dict.
        """
        templates = self.repo.list_templates_for_type(instrument_type_id, active_only=False)
        for t in templates:
            if t["name"] == "External calibration (file only)":
                return t

        tpl_id = self.repo.create_template(
            instrument_type_id,
            "External calibration (file only)",
            version=1,
            is_active=True,
            notes="Template used for out-of-house calibrations with attached file only.",
        )
        return self.repo.get_template(tpl_id)

    def _load_records(self):
        recs = self.repo.list_calibration_records_for_instrument(self.instrument_id)
        self.table.setRowCount(len(recs))
        for row, r in enumerate(recs):
            item_date = QtWidgets.QTableWidgetItem(r.get("cal_date", ""))
            item_tpl = QtWidgets.QTableWidgetItem(r.get("template_name", ""))
            item_perf = QtWidgets.QTableWidgetItem(r.get("performed_by", "") or "")
            item_result = QtWidgets.QTableWidgetItem(r.get("result", "") or "")

            item_date.setData(QtCore.Qt.UserRole, r["id"])  # store record_id

            self.table.setItem(row, 0, item_date)
            self.table.setItem(row, 1, item_tpl)
            self.table.setItem(row, 2, item_perf)
            self.table.setItem(row, 3, item_result)

        if recs:
            self.table.selectRow(0)
        else:
            self.details.clear()

    def _selected_record_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(QtCore.Qt.UserRole)

    def _update_details(self):
        rec_id = self._selected_record_id()
        if not rec_id:
            self.details.clear()
            return

        vals = self.repo.get_calibration_values(rec_id)
        rec = self.repo.get_calibration_record_with_template(rec_id)

        lines = []
        last_group = None

        for v in vals:
            # Only show computed diff-like fields
            if v.get("calc_type") not in ("ABS_DIFF", "PCT_ERROR"):
                continue

            val_txt = v.get("value_text")
            if not val_txt:
                continue

            # Parse numeric diff (absolute value)
            diff = None
            try:
                diff = abs(float(str(val_txt).strip()))
            except Exception:
                diff = None

            # Parse tolerance
            tol_raw = v.get("tolerance")
            tol_f = None
            if tol_raw not in (None, ""):
                try:
                    tol_f = float(str(tol_raw))
                except Exception:
                    tol_f = None

            status = ""
            if tol_f is not None and diff is not None:
                # FAIL if outside tolerance
                status = "FAIL" if diff > tol_f else "PASS"

            group = v.get("group_name") or ""
            label = v.get("label") or v.get("field_name") or ""
            unit = v.get("unit") or ""

            # Add blank line between groups
            if last_group is not None and group != last_group:
                if lines and lines[-1] != "":
                    lines.append("")
            last_group = group

            prefix = f"{group}, " if group else ""
            unit_str = f" {unit}" if unit else ""

            line = f"{prefix}{label}: {val_txt}{unit_str}"
            if status:
                line += f" ({status})"

            lines.append(line)

        if not lines:
            self.details.setPlainText(
                "No difference values recorded for this calibration."
            )
        else:
            # Add two new lines after the last point difference
            lines.append("")
            lines.append("")
            
            # Append template notes if they exist
            if rec and rec.get("template_notes"):
                template_notes = rec.get("template_notes", "").strip()
                if template_notes:
                    lines.append(template_notes)
            
            self.details.setPlainText("\n".join(lines))

    def on_new_cal(self):
        inst = self.repo.get_instrument(self.instrument_id)
        if not inst:
            return

        # Ask: template-based or external-file calibration
        choice, ok = QtWidgets.QInputDialog.getItem(
            self,
            "New calibration",
            "Choose calibration type:",
            ["Use template", "External file (out-of-house)"],
            0,
            False,
        )
        if not ok:
            return

        # Normal internal calibration (existing behavior)
        if choice.startswith("Use"):
            dlg = CalibrationFormDialog(self.repo, inst, parent=self)
            if dlg.exec_() == QtWidgets.QDialog.Accepted:
                self._load_records()
                self._update_details()
            return

        # External file calibration
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select external calibration file",
            "",
            "All files (*.*)",
        )
        if not path:
            return

        inst_type_id = inst.get("instrument_type_id")
        if not inst_type_id:
            QtWidgets.QMessageBox.warning(
                self,
                "No instrument type",
                "This instrument does not have an instrument type selected, "
                "so an external calibration cannot be recorded.",
            )
            return

        # Ensure an 'External calibration file' template exists for this instrument type
        templates = self.repo.list_templates_for_type(inst_type_id, active_only=False)
        ext_tpl = None
        for t in templates:
            if t["name"] == "External calibration file":
                ext_tpl = t
                break

        if ext_tpl is None:
            tpl_id = self.repo.create_template(
                inst_type_id,
                name="External calibration file",
                version=1,
                is_active=True,
                notes="Placeholder template for external (file-only) calibrations.",
            )
        else:
            tpl_id = ext_tpl["id"]

        today_str = date.today().isoformat()
        performed_by = ""
        result = "PASS"  # can be changed later in edit if needed
        notes = "External calibration file attached."

        # Create a record with no fields
        rec_id = self.repo.create_calibration_record(
            inst["id"],
            tpl_id,
            today_str,
            performed_by,
            result,
            notes,
            field_values={},
        )

        # Attach file directly to this record
        try:
            self.repo.add_attachment(self.instrument_id, path, record_id=rec_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error adding attachment",
                f"Calibration record created, but attaching file failed:\n{e}",
            )

        self._load_records()
        self._update_details()

    def on_view_edit(self):
        rec_id = self._selected_record_id()
        if not rec_id:
            return
        inst = self.repo.get_instrument(self.instrument_id)
        dlg = CalibrationFormDialog(self.repo, inst, record_id=rec_id, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self._load_records()
            self._update_details()
    
    def on_export_pdf(self):
        rec_id = self._selected_record_id()
        if not rec_id:
            QtWidgets.QMessageBox.information(
                self,
                "No selection",
                "Please select a calibration record to export.",
            )
            return
        
        # Get default filename
        rec = self.repo.get_calibration_record_with_template(rec_id)
        inst = self.repo.get_instrument(rec["instrument_id"]) if rec else None
        tag = inst.get("tag_number", "calibration") if inst else "calibration"
        cal_date = rec.get("cal_date", "") if rec else ""
        default_name = f"{tag}_{cal_date}.pdf" if cal_date else f"{tag}.pdf"
        
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export calibration to PDF",
            default_name,
            "PDF files (*.pdf);;All files (*)",
        )
        if not path:
            return
        
        try:
            from pdf_export import export_calibration_to_pdf
            export_calibration_to_pdf(self.repo, rec_id, path)
            QtWidgets.QMessageBox.information(
                self,
                "Export complete",
                f"Calibration record exported to:\n{path}",
            )
        except PermissionError as e:
            # Handle permission errors with a user-friendly message
            QtWidgets.QMessageBox.warning(
                self,
                "Export failed - Permission denied",
                str(e),
            )
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"PDF Export Error:\n{error_details}")  # Print to console for debugging
            QtWidgets.QMessageBox.critical(
                self,
                "Export failed",
                f"Error exporting to PDF:\n{str(e)}\n\nSee console for details.",
            )
       
class TemplatesDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Calibration Templates")

        layout = QtWidgets.QVBoxLayout(self)

        # Instrument type selector
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(QtWidgets.QLabel("Instrument type:"))
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItem("", None)
        for t in self.repo.list_instrument_types():
            self.type_combo.addItem(t["name"], t["id"])
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        top_layout.addWidget(self.type_combo)
        top_layout.addStretch(1)
        layout.addLayout(top_layout)

        # Templates list
        self.list = QtWidgets.QListWidget()
        layout.addWidget(self.list)

        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_edit = QtWidgets.QPushButton("Edit")
        self.btn_delete = QtWidgets.QPushButton("Delete")
        self.btn_fields = QtWidgets.QPushButton("Fields...")
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.btn_fields)
        layout.addLayout(btn_layout)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn_box.rejected.connect(self.reject)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)

        self.btn_add.clicked.connect(self.on_add)
        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_delete.clicked.connect(self.on_delete)
        self.btn_fields.clicked.connect(self.on_fields)

        # auto-select first type if present
        if self.type_combo.count() > 1:
            self.type_combo.setCurrentIndex(1)

    def _current_type_id(self):
        return self.type_combo.currentData()

    def _on_type_changed(self, index):
        self._load_templates()

    def _load_templates(self):
        self.list.clear()
        type_id = self._current_type_id()
        if not type_id:
            return
        templates = self.repo.list_templates_for_type(type_id, active_only=False)
        for t in templates:
            text = f"{t['name']} (v{t['version']})"
            if not t["is_active"]:
                text += " [inactive]"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, t["id"])
            self.list.addItem(item)

    def _current_template_id(self):
        item = self.list.currentItem()
        if not item:
            return None
        return item.data(QtCore.Qt.UserRole)

    def on_add(self):
        type_id = self._current_type_id()
        if not type_id:
            QtWidgets.QMessageBox.warning(
                self, "Instrument type", "Select an instrument type first."
            )
            return
        dlg = TemplateEditDialog(parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        data = dlg.get_data()
        if not data:
            return
        self.repo.create_template(
            type_id,
            data["name"],
            data["version"],
            data["is_active"],
            data["notes"],
        )
        self._load_templates()

    def on_edit(self):
        tpl_id = self._current_template_id()
        if not tpl_id:
            return
        tpl = self.repo.get_template(tpl_id)
        if not tpl:
            return
        dlg = TemplateEditDialog(template=tpl, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        data = dlg.get_data()
        if not data:
            return
        self.repo.update_template(
            tpl_id,
            data["name"],
            data["version"],
            data["is_active"],
            data["notes"],
        )
        self._load_templates()

    def on_delete(self):
        tpl_id = self._current_template_id()
        if not tpl_id:
            return
        resp = QtWidgets.QMessageBox.question(
            self, "Delete template",
            "Delete this template?\n\nIt must not have calibration records."
        )
        if resp != QtWidgets.QMessageBox.Yes:
            return
        try:
            self.repo.delete_template(tpl_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error deleting template", str(e))
        self._load_templates()

    def on_fields(self):
        tpl_id = self._current_template_id()
        if not tpl_id:
            return
        dlg = TemplateFieldsDialog(self.repo, tpl_id, parent=self)
        dlg.exec_()


class CalibrationFormDialog(QtWidgets.QDialog):
    """
    Dynamic calibration form based on calibration_templates and fields.
    Supports both New and Edit (if record_id provided).
    """
    def __init__(self, repo: CalibrationRepository, instrument: dict,
                 record_id: int | None = None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.instrument = instrument
        self.record_id = record_id
        self.template = None
        self.fields = []
        self.field_widgets = {}  # field_id -> widget

        inst_tag = instrument.get("tag_number", str(instrument["id"]))
        self.setWindowTitle(f"Calibration - {inst_tag}")

        layout = QtWidgets.QVBoxLayout(self)

        # Top: basic info
        info_parts = [f"ID: {inst_tag}"]
        if instrument.get("location"):
            info_parts.append(f"Location: {instrument['location']}")
        layout.addWidget(QtWidgets.QLabel(" | ".join(info_parts)))

        # Stack of group pages
        self.stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.stack)

        # Group navigation
        nav_layout = QtWidgets.QHBoxLayout()
        self.prev_btn = QtWidgets.QPushButton("Previous group")
        self.next_btn = QtWidgets.QPushButton("Next group")
        self.group_label = QtWidgets.QLabel("")
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addStretch(1)
        nav_layout.addWidget(self.group_label)
        layout.addLayout(nav_layout)

        self.prev_btn.clicked.connect(self.on_prev_group)
        self.next_btn.clicked.connect(self.on_next_group)

        self.group_names = []
        self.current_group_index = 0


        # Bottom: general cal metadata
        meta_layout = QtWidgets.QFormLayout()

        self.date_edit = QtWidgets.QDateEdit(calendarPopup=True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QtCore.QDate.currentDate())

        self.performed_edit = QtWidgets.QLineEdit()
        try:
            op = self.repo.get_setting("operator_name", "")
        except Exception:
            op = ""
        if op:
            self.performed_edit.setText(op)
        self.result_combo = QtWidgets.QComboBox()
        self.result_combo.addItems(["PASS", "FAIL", "OUT_OF_TOL", "OTHER"])

        meta_layout.addRow("Cal date", self.date_edit)
        meta_layout.addRow("Performed by", self.performed_edit)
        meta_layout.addRow("Result", self.result_combo)

        layout.addLayout(meta_layout)
        
        # Template notes (read-only, displayed at bottom of every calibration from this template)
        self.template_notes_label = QtWidgets.QLabel("Template Notes:")
        self.template_notes_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.template_notes_label)
        
        self.template_notes_display = QtWidgets.QPlainTextEdit()
        self.template_notes_display.setReadOnly(True)
        self.template_notes_display.setMinimumHeight(80)
        # Set word wrap to only break at word boundaries
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WordWrap)
        self.template_notes_display.document().setDefaultTextOption(option)
        layout.addWidget(self.template_notes_display)

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(lambda: self._show_help())
        layout.addWidget(btn_box)
        
        # Set initial dialog size
        self.resize(950, 600)

        if self.record_id is None:
            self._init_new()
        else:
            self._init_edit()
    
    def _show_help(self):
        title, content = get_help_content("CalibrationFormDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()
    
    def showEvent(self, event):
        """Override showEvent to ensure dialog is properly displayed."""
        super().showEvent(event)
        # Force layout update and ensure stack widget is visible
        self.updateGeometry()
        if self.stack.count() > 0:
            self._update_group_nav()
            
    def _choose_template_for_instrument(self):
        inst_type_id = self.instrument.get("instrument_type_id")
        if not inst_type_id:
            QtWidgets.QMessageBox.warning(
                self,
                "No instrument type",
                "This instrument does not have an instrument type selected, so "
                "no calibration template can be chosen.",
            )
            return None

        templates = self.repo.list_templates_for_type(inst_type_id, active_only=True)
        if not templates:
            QtWidgets.QMessageBox.warning(
                self,
                "No templates",
                "No calibration templates defined for this instrument type.",
            )
            return None

        if len(templates) == 1:
            return templates[0]

        # Let user choose if multiple
        names = [f"{t['name']} (v{t['version']})" for t in templates]
        items = [names[i] for i in range(len(names))]
        item, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Select template",
            "Calibration template:",
            items,
            0,
            False,
        )
        if not ok:
            return None
        idx = items.index(item)
        return templates[idx]

    def _build_dynamic_form(self):
        # Clear old pages
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()

        self.field_widgets.clear()

        self.fields = self.repo.list_template_fields(self.template["id"])

        # Split into header vs grouped
        header_fields = [f for f in self.fields if not f.get("group_name")]
        grouped = {}
        for f in self.fields:
            g = f.get("group_name")
            if g:
                grouped.setdefault(g, []).append(f)
        
        # Sort group names by min sort_order
        ordered_groups = []
        for gname, flist in grouped.items():
            min_sort = min((f.get("sort_order") or 0) for f in flist)
            ordered_groups.append((gname, min_sort, flist))
        ordered_groups.sort(key=lambda t: t[1])

        # If there are no named groups, treat header as a single page
        if not ordered_groups and header_fields:
            page = QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(page)
            for f in sorted(header_fields, key=lambda f: f.get("sort_order") or 0):
                w = self._create_field_widget(f)
                self.field_widgets[f["id"]] = w
                label_text = f["label"]
                if f.get("unit"):
                    label_text += f" ({f['unit']})"
                form.addRow(label_text, w)
            self.stack.addWidget(page)
            self.group_names = [""]
        else:
            # Build one page per group; header fields go on first page
            first_page = True
            for gname, _, flist in ordered_groups:
                page = QtWidgets.QWidget()
                form = QtWidgets.QFormLayout(page)

                if first_page and header_fields:
                    for f in sorted(header_fields, key=lambda f: f.get("sort_order") or 0):
                        w = self._create_field_widget(f)
                        self.field_widgets[f["id"]] = w
                        label_text = f["label"]
                        if f.get("unit"):
                            label_text += f" ({f['unit']})"
                        form.addRow(label_text, w)
                    first_page = False

                for f in sorted(flist, key=lambda f: f.get("sort_order") or 0):
                    w = self._create_field_widget(f)
                    self.field_widgets[f["id"]] = w
                    label_text = f["label"]
                    if f.get("unit"):
                        label_text += f" ({f['unit']})"
                    form.addRow(label_text, w)

                self.stack.addWidget(page)

            self.group_names = [gname for (gname, _, _) in ordered_groups]

        self.current_group_index = 0
        self._update_group_nav()
        
        # Load and display template notes
        if self.template:
            template_notes = str(self.template.get("notes", "") or "")
            self.template_notes_display.setPlainText(template_notes)
            # Hide template notes section if there are no notes
            if not template_notes.strip():
                self.template_notes_label.hide()
                self.template_notes_display.hide()
            else:
                self.template_notes_label.show()
                self.template_notes_display.show()
    
    def _create_field_widget(self, f):
        data_type = f["data_type"]
        w = None

        if data_type == "number":
            w = QtWidgets.QLineEdit()
            w.setPlaceholderText("Number")
        elif data_type == "bool":
            w = QtWidgets.QCheckBox()
        elif data_type == "date":
            w = QtWidgets.QDateEdit(calendarPopup=True)
            w.setDisplayFormat("yyyy-MM-dd")
            w.setDate(QtCore.QDate.currentDate())
        elif data_type == "signature":
            w = QtWidgets.QComboBox()
            w.addItem("", None)  # Empty option
            # Load signatures from Signatures folder
            from pathlib import Path
            signatures_dir = Path("Signatures")
            if signatures_dir.exists():
                image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp'}
                for file_path in signatures_dir.iterdir():
                    if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                        name = file_path.stem
                        w.addItem(name, file_path.name)
            # Set default value if field has one
            default_sig = f.get("default_value")
            if default_sig:
                idx = w.findData(default_sig)
                if idx >= 0:
                    w.setCurrentIndex(idx)
        else:  # text / default
            w = QtWidgets.QLineEdit()

        # Computed fields are read-only
        if f.get("calc_type"):
            if isinstance(w, QtWidgets.QLineEdit):
                w.setReadOnly(True)
            elif isinstance(w, QtWidgets.QCheckBox):
                w.setEnabled(False)
            elif isinstance(w, QtWidgets.QDateEdit):
                w.setReadOnly(True)
        
        # Set up autofill connections for fields with autofill enabled
        return w
    
    def _apply_autofill_to_current_group(self):
        """Apply autofill values from the previous group to the currently visible group."""
        # Only apply autofill if we're not on the first group (need a previous group to autofill from)
        if self.current_group_index == 0:
            return
        
        # Get all fields in the previous group that have autofill enabled
        if not self.group_names or len(self.group_names) == 0:
            return
        
        # Find fields in the previous group (the one we just came from)
        prev_group_index = self.current_group_index - 1
        if prev_group_index < 0 or prev_group_index >= len(self.group_names):
            return
        
        prev_group_name = self.group_names[prev_group_index]
        prev_group_fields = [f for f in self.fields if (f.get("group_name") or "") == prev_group_name]
        
        # Get current group name
        current_group_name = ""
        if self.group_names and self.current_group_index < len(self.group_names):
            current_group_name = self.group_names[self.current_group_index]
        
        # Find fields in the current group
        current_group_fields = [f for f in self.fields if (f.get("group_name") or "") == current_group_name]
        
        # For each autofill-enabled field in the CURRENT group, get its value from matching fields in PREVIOUS group
        # This is more intuitive: enable autofill on the field you want to auto-fill
        for current_field in current_group_fields:
            # Check autofill flag - handle both int (0/1) and bool (False/True) and string ("0"/"1")
            autofill_flag = current_field.get("autofill_from_first_group")
            
            # Convert to boolean: 1, True, "1" = True; 0, False, "0", None = False
            try:
                is_autofill = bool(int(autofill_flag)) if autofill_flag is not None else False
            except (ValueError, TypeError):
                is_autofill = bool(autofill_flag) if autofill_flag else False
            
            if not is_autofill:
                continue
            
            current_field_id = current_field["id"]
            if current_field_id not in self.field_widgets:
                continue
            
            current_widget = self.field_widgets[current_field_id]
            current_data_type = current_field.get("data_type", "text")
            
            # Find matching field in the previous group by name or label
            # Try to match by label first (more user-friendly), then by base name (without numeric suffix)
            current_field_name_full = current_field.get("name") or ""
            current_field_label = current_field.get("label") or ""
            
            if not current_field_name_full and not current_field_label:
                continue
            
            # Extract base name by removing trailing numbers (e.g., "date_2" -> "date", "digital_sig_1" -> "digital_sig")
            import re
            current_base_name = re.sub(r'_\d+$', '', current_field_name_full) if current_field_name_full else ""
            
            matched = False
            for prev_field in prev_group_fields:
                prev_field_name = prev_field.get("name") or ""
                prev_field_label = prev_field.get("label") or ""
                prev_base_name = re.sub(r'_\d+$', '', prev_field_name) if prev_field_name else ""
                
                # Match by label first (exact match), then by base name (without suffix)
                match_by_label = prev_field_label and current_field_label and prev_field_label.strip().lower() == current_field_label.strip().lower()
                match_by_base_name = prev_base_name and current_base_name and prev_base_name.strip().lower() == current_base_name.strip().lower()
                
                if match_by_label or match_by_base_name:
                    matched = True
                    prev_field_id = prev_field["id"]
                    if prev_field_id not in self.field_widgets:
                        continue
                    
                    # Get the current value from the previous group's widget
                    prev_widget = self.field_widgets[prev_field_id]
                    
                    # Force widget to process any pending events to ensure value is committed
                    QtWidgets.QApplication.processEvents()
                    
                    value = None
                    
                    if isinstance(prev_widget, QtWidgets.QLineEdit):
                        value = prev_widget.text()
                    elif isinstance(prev_widget, QtWidgets.QCheckBox):
                        value = "1" if prev_widget.isChecked() else "0"
                    elif isinstance(prev_widget, QtWidgets.QDateEdit):
                        value = prev_widget.date().toString("yyyy-MM-dd")
                    elif isinstance(prev_widget, QtWidgets.QComboBox):
                        value = prev_widget.currentData() or ""
                        # Also try currentText if currentData is empty
                        if not value:
                            value = prev_widget.currentText()
                    
                    # Skip only if value is None (not if it's empty string, as empty might be valid)
                    if value is None:
                        continue
                    
                    # Apply the value, blocking signals to prevent recursive updates
                    if isinstance(current_widget, QtWidgets.QLineEdit):
                        current_widget.blockSignals(True)
                        current_widget.setText(value)
                        current_widget.blockSignals(False)
                        current_widget.update()
                        current_widget.repaint()
                    elif isinstance(current_widget, QtWidgets.QCheckBox):
                        current_widget.blockSignals(True)
                        current_widget.setChecked(value == "1" or value.lower() == "true")
                        current_widget.blockSignals(False)
                        current_widget.update()
                        current_widget.repaint()
                    elif isinstance(current_widget, QtWidgets.QDateEdit):
                        current_widget.blockSignals(True)
                        try:
                            date = QtCore.QDate.fromString(value, "yyyy-MM-dd")
                            if date.isValid():
                                current_widget.setDate(date)
                        except Exception:
                            pass
                        current_widget.blockSignals(False)
                        current_widget.update()
                        current_widget.repaint()
                    elif isinstance(current_widget, QtWidgets.QComboBox):
                        current_widget.blockSignals(True)
                        # For combo boxes, try to match by data first, then by text
                        if current_data_type == "signature":
                            idx = current_widget.findData(value)
                            if idx < 0:
                                idx = current_widget.findText(value)
                            if idx >= 0:
                                current_widget.setCurrentIndex(idx)
                        else:
                            # For other combo boxes, match by text
                            idx = current_widget.findText(value)
                            if idx >= 0:
                                current_widget.setCurrentIndex(idx)
                        current_widget.blockSignals(False)
                        current_widget.update()
                        current_widget.repaint()
                    break  # Found matching field, move to next current group field
        
        # Force UI update after all autofill operations
        QtWidgets.QApplication.processEvents()
        current_page = self.stack.currentWidget()
        if current_page:
            current_page.update()
            current_page.repaint()

    def _update_group_nav(self):
        count = self.stack.count()
        if count == 0:
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.group_label.setText("No groups")
            return

        if self.current_group_index < 0:
            self.current_group_index = 0
        if self.current_group_index > count - 1:
            self.current_group_index = count - 1

        self.stack.setCurrentIndex(self.current_group_index)
        # Force update and repaint to ensure the new page is visible
        current_widget = self.stack.currentWidget()
        if current_widget:
            current_widget.show()
            current_widget.update()
            current_widget.repaint()
        self.stack.update()
        self.stack.repaint()
        
        # Apply autofill values from previous group to current group
        # Use QTimer to ensure the new page is fully visible before applying autofill
        QtCore.QTimer.singleShot(10, self._apply_autofill_to_current_group)
        
        self.prev_btn.setEnabled(self.current_group_index > 0)
        self.next_btn.setEnabled(self.current_group_index < count - 1)

        name = ""
        if self.group_names and self.current_group_index < len(self.group_names):
            name = self.group_names[self.current_group_index]

        if name:
            text = f"{name} ({self.current_group_index + 1}/{count})"
        else:
            text = f"Group {self.current_group_index + 1} of {count}"
        self.group_label.setText(text)

    def on_prev_group(self):
        if self.current_group_index > 0:
            self.current_group_index -= 1
            self._update_group_nav()

    def on_next_group(self):
        if self.current_group_index < self.stack.count() - 1:
            self.current_group_index += 1
            self._update_group_nav()

    def _init_new(self):
        self.template = self._choose_template_for_instrument()
        if not self.template:
            # close dialog if no template
            QtCore.QTimer.singleShot(0, self.reject)
            return
        self._build_dynamic_form()
        # Load and display template notes
        template_notes = str(self.template.get("notes", "") or "")
        self.template_notes_display.setPlainText(template_notes)
        # Hide template notes section if there are no notes
        if not template_notes.strip():
            self.template_notes_label.hide()
            self.template_notes_display.hide()
        else:
            self.template_notes_label.show()
            self.template_notes_display.show()

    def _init_edit(self):
        rec = self.repo.get_calibration_record_with_template(self.record_id)
        if not rec:
            QtWidgets.QMessageBox.warning(
                self,
                "Not found",
                "Calibration record not found.",
            )
            QtCore.QTimer.singleShot(0, self.reject)
            return

        self.template = self.repo.get_template(rec["template_id"])
        self._build_dynamic_form()

        # Fill metadata
        try:
            d = datetime.strptime(rec["cal_date"], "%Y-%m-%d").date()
            self.date_edit.setDate(QtCore.QDate(d.year, d.month, d.day))
        except Exception:
            pass

        if rec.get("performed_by"):
            self.performed_edit.setText(rec["performed_by"])

        res = rec.get("result") or "PASS"
        idx = self.result_combo.findText(res)
        if idx < 0:
            idx = 0
        self.result_combo.setCurrentIndex(idx)

        # Load and display template notes (not per-instance notes)
        template_notes = str(self.template.get("notes", "") or "")
        self.template_notes_display.setPlainText(template_notes)
        # Hide template notes section if there are no notes
        if not template_notes.strip():
            self.template_notes_label.hide()
            self.template_notes_display.hide()
        else:
            self.template_notes_label.show()
            self.template_notes_display.show()

        # Fill field values
        vals = self.repo.get_calibration_values(self.record_id)
        by_field = {v["field_id"]: v for v in vals}
        for f in self.fields:
            fid = f["id"]
            w = self.field_widgets.get(fid)
            if not w:
                continue
            v = by_field.get(fid)
            if not v:
                continue
            val_text = v.get("value_text")
            dt = f["data_type"]
            if dt == "bool":
                w.setChecked(val_text == "1" or val_text.lower() in ("true", "yes"))
            elif dt == "date":
                try:
                    d = datetime.strptime(val_text, "%Y-%m-%d").date()
                    w.setDate(QtCore.QDate(d.year, d.month, d.day))
                except Exception:
                    pass
            elif dt == "signature":
                # For signature combobox, find by data (filename)
                if isinstance(w, QtWidgets.QComboBox):
                    idx = w.findData(val_text)
                    if idx >= 0:
                        w.setCurrentIndex(idx)
            else:
                w.setText(val_text or "")

    def accept(self):
        if not self.template:
            super().reject()
            return

        cal_date = self.date_edit.date().toString("yyyy-MM-dd")
        performed_by = self.performed_edit.text().strip()
        result = self.result_combo.currentText()
        # Notes are now permanent from template, not per-instance
        notes = ""

        field_values: dict[int, str] = {}

        # First pass: collect user-entered values
        for f in self.fields:
            fid = f["id"]
            dt = f["data_type"]
            w = self.field_widgets[fid]
            val = None

            if dt == "bool":
                val = "1" if w.isChecked() else "0"
            elif dt == "date":
                val = w.date().toString("yyyy-MM-dd")
            elif dt == "signature":
                # For signature combobox, get the filename (data)
                if isinstance(w, QtWidgets.QComboBox):
                    val = w.currentData() or ""
                else:
                    val = ""
            else:
                val = w.text().strip()

            is_computed = bool(f.get("calc_type"))
            is_required = bool(f.get("required"))

            # Don't enforce "required" for computed fields; they will be overwritten
            if is_required and not is_computed:
                if val is None or val == "" or (val == "0" and dt != "bool"):
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Validation",
                        f"Field '{f['label']}' is required.",
                    )
                    return

            field_values[fid] = val

        # Build name -> value map for calculations
        values_by_name = {}
        for f in self.fields:
            fid = f["id"]
            values_by_name[f["name"]] = field_values.get(fid)

        # Second pass: apply computations
        for f in self.fields:
            calc_type = f.get("calc_type")
            if not calc_type:
                continue

            fid = f["id"]

            if calc_type == "ABS_DIFF":
                ref1 = f.get("calc_ref1_name")
                ref2 = f.get("calc_ref2_name")
                v1 = values_by_name.get(ref1)
                v2 = values_by_name.get(ref2)
                result_val = ""
                try:
                    if v1 not in (None, "") and v2 not in (None, ""):
                        a = float(v1)
                        b = float(v2)
                        result_val = f"{abs(a - b):.3f}"
                except (TypeError, ValueError):
                    result_val = ""
                field_values[fid] = result_val

            elif calc_type == "PCT_ERROR":
                # Value 1 = measured, Value 2 = reference
                ref1 = f.get("calc_ref1_name")
                ref2 = f.get("calc_ref2_name")
                v1 = values_by_name.get(ref1)
                v2 = values_by_name.get(ref2)
                result_val = ""
                try:
                    if v1 not in (None, "") and v2 not in (None, ""):
                        a = float(v1)
                        b = float(v2)
                        if b != 0:
                            result_val = f"{(abs(a - b) / abs(b) * 100):.3f}"
                        else:
                            result_val = ""
                except (TypeError, ValueError):
                    result_val = ""
                field_values[fid] = result_val

        # If you ever add more calc types, handle them here.

        # Third pass: auto-FAIL if any ABS_DIFF exceeds tolerance
        any_out_of_tol = False
        for f in self.fields:
            if f.get("calc_type") != "ABS_DIFF":
                continue

            tol_raw = f.get("tolerance")
            if tol_raw in (None, ""):
                continue

            try:
                tol = float(str(tol_raw))
            except (TypeError, ValueError):
                continue

            fid = f["id"]
            val_txt = field_values.get(fid)
            if not val_txt:
                continue

            try:
                diff = abs(float(str(val_txt)))
            except (TypeError, ValueError):
                continue

            if diff > tol:
                any_out_of_tol = True
                break

        # If any point is out of tolerance, force overall result to FAIL
        if any_out_of_tol:
            result = "FAIL"
            idx = self.result_combo.findText("FAIL")
            if idx >= 0:
                self.result_combo.setCurrentIndex(idx)


        try:
            if self.record_id is None:
                self.repo.create_calibration_record(
                    self.instrument["id"],
                    self.template["id"],
                    cal_date,
                    performed_by,
                    result,
                    notes,
                    field_values,
                )
            else:
                self.repo.update_calibration_record(
                    self.record_id,
                    cal_date,
                    performed_by,
                    result,
                    notes,
                    field_values,
                )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error saving calibration",
                str(e),
            )
            return

        super().accept()


class CalDateDialog(QtWidgets.QDialog):
    """Dialog to choose a new 'last calibration date'."""

    def __init__(self, parent=None, initial_date=None):
        super().__init__(parent)
        self.setWindowTitle("Set last calibration date")

        layout = QtWidgets.QVBoxLayout(self)

        self.date_edit = QtWidgets.QDateEdit(calendarPopup=True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        if initial_date is None:
            self.date_edit.setDate(QtCore.QDate.currentDate())
        else:
            self.date_edit.setDate(initial_date)

        layout.addWidget(QtWidgets.QLabel("Select last calibration date:"))
        layout.addWidget(self.date_edit)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_date(self):
        """Return a Python date object."""
        qd = self.date_edit.date()
        return date(qd.year(), qd.month(), qd.day())

class InstrumentInfoDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, instrument_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.instrument_id = instrument_id

        inst = self.repo.get_instrument(instrument_id)
        if not inst:
            self.setWindowTitle("Instrument info")
            layout = QtWidgets.QVBoxLayout(self)
            layout.addWidget(QtWidgets.QLabel("Instrument not found."))
            return

        tag = inst.get("tag_number", "")
        self.setWindowTitle(f"Instrument info - {tag}")

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)
        self.resize(500, 400)

        # Core fields
        location = inst.get("location", "") or ""
        cal_type = inst.get("calibration_type", "") or ""
        if cal_type == "SEND_OUT":
            cal_type_pretty = "Send out"
        elif cal_type == "PULL_IN":
            cal_type_pretty = "Pull in"
        else:
            cal_type_pretty = cal_type

        dest_name = self.repo.get_destination_name(inst.get("destination_id"))

        # Instrument type name
        inst_type_name = ""
        type_id = inst.get("instrument_type_id")
        if type_id:
            t = self.repo.get_instrument_type(type_id)
            if t:
                inst_type_name = t["name"]

        last_cal = inst.get("last_cal_date") or ""
        next_due = inst.get("next_due_date") or ""
        status = inst.get("status") or ""
        notes = inst.get("notes") or ""

        days_left_str = ""
        if next_due:
            try:
                d = datetime.strptime(next_due, "%Y-%m-%d").date()
                days_left = (d - date.today()).days
                days_left_str = str(days_left)
            except Exception:
                pass

        form.addRow("ID:", QtWidgets.QLabel(tag))
        form.addRow("Location:", QtWidgets.QLabel(location))
        form.addRow("Calibration type:", QtWidgets.QLabel(cal_type_pretty))
        form.addRow("Destination:", QtWidgets.QLabel(dest_name or ""))
        form.addRow("Last cal:", QtWidgets.QLabel(last_cal))
        form.addRow("Next due:", QtWidgets.QLabel(next_due))
        form.addRow("Days left:", QtWidgets.QLabel(days_left_str))
        form.addRow("Status:", QtWidgets.QLabel(status))
        form.addRow("Instrument type:", QtWidgets.QLabel(inst_type_name or "(none)"))
        
        # Notes (read-only)
        if notes:
            layout.addWidget(QtWidgets.QLabel("Notes:"))
            notes_edit = QtWidgets.QPlainTextEdit()
            notes_edit.setPlainText(notes)
            notes_edit.setReadOnly(True)
            notes_edit.setMinimumHeight(80)
            # Set word wrap to only break at word boundaries
            option = QtGui.QTextOption()
            option.setWrapMode(QtGui.QTextOption.WordWrap)
            notes_edit.document().setDefaultTextOption(option)
            layout.addWidget(notes_edit)

        # Optional: attachments count
        try:
            atts = self.repo.list_attachments(instrument_id)
            layout.addWidget(QtWidgets.QLabel(f"Attachments: {len(atts)}"))
        except Exception:
            pass

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Help | QtWidgets.QDialogButtonBox.Close)
        btn_box.helpRequested.connect(lambda: self._show_help())
        btn_box.rejected.connect(self.reject)
        # Map Close to accept so hitting Enter works
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)
    
    def _show_help(self):
        title, content = get_help_content("InstrumentInfoDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

        self.btn_history.clicked.connect(self.on_history)
        self.btn_close.clicked.connect(self.accept)

        self.resize(500, 400)

    def on_history(self):
        dlg = AuditLogDialog(self.repo, self.instrument_id, parent=self)
        dlg.exec_()

class AuditLogDialog(QtWidgets.QDialog):
    def __init__(self, repo: CalibrationRepository, instrument_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.instrument_id = instrument_id

        self.setWindowTitle("Change history")
        self.resize(800, 400)

        layout = QtWidgets.QVBoxLayout(self)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Time", "Action", "Field", "Old value", "New value", "Actor"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Help | QtWidgets.QDialogButtonBox.Close)
        btn_box.helpRequested.connect(lambda: self._show_help())
        btn_box.rejected.connect(self.reject)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)
    
    def _show_help(self):
        title, content = get_help_content("AuditLogDialog")
        dlg = HelpDialog(title, content, self)
        dlg.open()
        dlg.raise_()
        dlg.activateWindow()

        self._load()

    def _load(self):
        rows = self.repo.get_audit_for_instrument(self.instrument_id)
        self.table.setRowCount(len(rows))
        for r_i, r in enumerate(rows):
            def mk(text):
                return QtWidgets.QTableWidgetItem(text or "")

            self.table.setItem(r_i, 0, mk(r.get("ts")))
            self.table.setItem(r_i, 1, mk(r.get("action")))
            self.table.setItem(r_i, 2, mk(r.get("field")))
            self.table.setItem(r_i, 3, mk(r.get("old_value")))
            self.table.setItem(r_i, 4, mk(r.get("new_value")))
            self.table.setItem(r_i, 5, mk(r.get("actor") or ""))

class InstrumentFilterProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text_filter = ""
        self.status_filter = ""
        self.type_filter = ""
        self.due_filter = "All"  # "All", "Overdue", "Due in 30 days"

    def set_text_filter(self, text: str):
        self.text_filter = (text or "").lower().strip()
        self.invalidateFilter()

    def set_status_filter(self, status: str):
        self.status_filter = status or ""
        self.invalidateFilter()

    def set_type_filter(self, tname: str):
        self.type_filter = tname or ""
        self.invalidateFilter()

    def set_due_filter(self, df: str):
        self.due_filter = df or "All"
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        if model is None:
            return True

        # Columns per InstrumentTableModel:
        # 0 ID, 1 Location, 2 Type (cal type), 3 Destination,
        # 4 Last Cal, 5 Next Due, 6 Days Left, 7 Status, 8 Instrument type name
        def data(col):
            idx = model.index(source_row, col, source_parent)
            val = model.data(idx, QtCore.Qt.DisplayRole)
            return "" if val is None else str(val)

        # Text filter on ID, location, destination, instrument type
        if self.text_filter:
            haystack = " ".join(
                [
                    data(0),  # ID
                    data(1),  # Location
                    data(3),  # Destination
                    data(8),  # Instrument type name
                ]
            ).lower()
            if self.text_filter not in haystack:
                return False

        # Status filter
        if self.status_filter:
            status = data(7)
            if status != self.status_filter:
                return False

        # Instrument type filter
        if self.type_filter:
            inst_type_name = data(8)
            if inst_type_name != self.type_filter:
                return False

        # Due filter
        if self.due_filter != "All":
            days_str = data(6)
            try:
                days = int(days_str)
            except Exception:
                days = 999999

            if self.due_filter == "Overdue":
                if days >= 0:
                    return False
            elif self.due_filter == "Due in 30 days":
                if days < 0 or days > 30:
                    return False

        return True

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, repo: CalibrationRepository):
        super().__init__()
        self.repo = repo
        self.setWindowTitle("Calibration Tracker")
        self.resize(1000, 600)
        icon_path = _app_icon_path()
        if icon_path.is_file():
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))

        self._init_ui()
        self.load_instruments()

    def _init_ui(self):
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)

        # ------------------------------------------------------------------
        # Toolbar - Streamlined with most common actions
        # ------------------------------------------------------------------
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)

        # Primary actions - most frequently used
        self.act_new = toolbar.addAction("New")
        self.act_new.setShortcut(QtGui.QKeySequence.New)
        self.act_new.setToolTip("Create a new instrument (Ctrl+N)")

        self.act_edit = toolbar.addAction("Edit")
        self.act_edit.setShortcut(QtGui.QKeySequence("Ctrl+E"))
        self.act_edit.setToolTip("Edit selected instrument (Ctrl+E)")

        toolbar.addSeparator()

        # Calibration actions
        self.act_cal = toolbar.addAction("Mark Calibrated")
        self.act_cal.setShortcut(QtGui.QKeySequence("Ctrl+M"))
        self.act_cal.setToolTip("Mark selected instrument as calibrated (Ctrl+M)")

        self.act_hist = toolbar.addAction("History")
        self.act_hist.setShortcut(QtGui.QKeySequence("Ctrl+H"))
        self.act_hist.setToolTip("View calibration history (Ctrl+H)")

        toolbar.addSeparator()

        # Settings (moved to end, less frequently used)
        self.act_settings = toolbar.addAction("Settings")
        self.act_settings.setShortcut(QtGui.QKeySequence.Preferences)
        self.act_settings.setToolTip("Open settings (Ctrl+,)")

        # Connect toolbar actions
        self.act_new.triggered.connect(self.on_new)
        self.act_edit.triggered.connect(self.on_edit)
        self.act_cal.triggered.connect(self.on_mark_calibrated)
        self.act_hist.triggered.connect(self.on_cal_history)
        self.act_settings.triggered.connect(self.on_settings)
        
        # Actions not in toolbar (available via menus/context menu)
        self.act_delete = QtWidgets.QAction("Delete", self)
        self.act_delete.setShortcut(QtGui.QKeySequence.Delete)
        self.act_delete.setToolTip("Delete selected instrument (Del)")
        self.act_delete.triggered.connect(self.on_delete)
        
        self.act_view_info = QtWidgets.QAction("View Details", self)
        self.act_view_info.setShortcut(QtGui.QKeySequence("Ctrl+I"))
        self.act_view_info.setToolTip("View detailed information (Ctrl+I)")
        self.act_view_info.triggered.connect(self.on_view_info)
        
        self.act_templates = QtWidgets.QAction("Templates", self)
        self.act_templates.setShortcut(QtGui.QKeySequence("Ctrl+T"))
        self.act_templates.setToolTip("Manage calibration templates (Ctrl+T)")
        self.act_templates.triggered.connect(self.on_templates)
        
        self.act_dest = QtWidgets.QAction("Destinations", self)
        self.act_dest.setToolTip("Manage calibration destinations")
        self.act_dest.triggered.connect(self.on_destinations)
        
        self.act_reminders = QtWidgets.QAction("Send Reminders", self)
        self.act_reminders.setToolTip("Send LAN reminders for due calibrations")
        self.act_reminders.triggered.connect(self.on_send_reminders)

        # ------------------------------------------------------------------
        # Menus
        # ------------------------------------------------------------------
        menubar = self.menuBar()

        # File menu - file operations and exports
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_edit)
        file_menu.addAction(self.act_delete)
        file_menu.addSeparator()
        
        export_menu = file_menu.addMenu("&Export")
        export_csv_action = export_menu.addAction("Current view to CSV...")
        export_csv_action.setShortcut(QtGui.QKeySequence("Ctrl+Shift+C"))
        export_csv_action.triggered.connect(self.on_export_csv)
        
        export_pdf_action = export_menu.addAction("All calibrations to PDF...")
        export_pdf_action.setShortcut(QtGui.QKeySequence("Ctrl+Shift+P"))
        export_pdf_action.triggered.connect(self.on_export_all_calibrations)

        file_menu.addSeparator()
        exit_action = file_menu.addAction("E&xit")
        exit_action.setShortcut(QtGui.QKeySequence.Quit)
        exit_action.triggered.connect(self.close)

        # Edit menu - editing and viewing
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self.act_edit)
        edit_menu.addAction(self.act_view_info)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_delete)

        # Calibrations menu - all calibration-related actions
        cal_menu = menubar.addMenu("&Calibrations")
        cal_menu.addAction(self.act_cal)
        cal_menu.addAction(self.act_hist)
        cal_menu.addSeparator()
        cal_menu.addAction(self.act_templates)

        # Tools menu - management and utilities
        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction(self.act_dest)
        tools_menu.addAction(self.act_reminders)
        tools_menu.addSeparator()
        tools_menu.addAction(self.act_settings)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        shortcuts_action = help_menu.addAction("Keyboard Shortcuts...")
        shortcuts_action.setShortcut(QtGui.QKeySequence("F1"))
        shortcuts_action.triggered.connect(self.on_show_shortcuts)
        help_menu.addSeparator()
        about_action = help_menu.addAction("About...")
        about_action.triggered.connect(self.on_show_about)

        # ------------------------------------------------------------------
        # Filters row with better layout
        # ------------------------------------------------------------------
        filters_container = QtWidgets.QWidget()
        filters_layout = QtWidgets.QHBoxLayout(filters_container)
        filters_layout.setContentsMargins(5, 5, 5, 5)
        filters_layout.setSpacing(10)

        # Search with icon-like styling
        search_label = QtWidgets.QLabel("🔍")
        search_label.setToolTip("Search instruments")
        filters_layout.addWidget(search_label)
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Search by ID, location, destination, or type...")
        self.search_edit.setToolTip("Type to search instruments. Press Ctrl+F to focus.")
        self.search_edit.setClearButtonEnabled(True)
        filters_layout.addWidget(self.search_edit, 3)

        # Add Ctrl+F shortcut for search
        search_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(lambda: self.search_edit.setFocus())
        
        # Update highlight delegate when search text changes
        self.search_edit.textChanged.connect(self._update_search_highlight)

        filters_layout.addSpacing(10)

        self.status_filter_combo = QtWidgets.QComboBox()
        self.status_filter_combo.addItem("All Statuses", "")
        self.status_filter_combo.addItem("ACTIVE", "ACTIVE")
        self.status_filter_combo.addItem("RETIRED", "RETIRED")
        self.status_filter_combo.addItem("OUT_FOR_CAL", "OUT_FOR_CAL")
        self.status_filter_combo.setToolTip("Filter by instrument status")
        filters_layout.addWidget(QtWidgets.QLabel("Status:"))
        filters_layout.addWidget(self.status_filter_combo)

        self.type_filter_combo = QtWidgets.QComboBox()
        self.type_filter_combo.addItem("All Types", "")
        for t in self.repo.list_instrument_types():
            self.type_filter_combo.addItem(t["name"], t["name"])
        self.type_filter_combo.setToolTip("Filter by instrument type")
        filters_layout.addWidget(QtWidgets.QLabel("Type:"))
        filters_layout.addWidget(self.type_filter_combo)

        self.due_filter_combo = QtWidgets.QComboBox()
        self.due_filter_combo.addItem("All")
        self.due_filter_combo.addItem("Overdue")
        self.due_filter_combo.addItem("Due in 30 days")
        self.due_filter_combo.setToolTip("Filter by calibration due date")
        filters_layout.addWidget(QtWidgets.QLabel("Due:"))
        filters_layout.addWidget(self.due_filter_combo)

        # Clear filters button
        clear_filters_btn = QtWidgets.QPushButton("Clear")
        clear_filters_btn.setToolTip("Clear all filters")
        clear_filters_btn.setMaximumWidth(60)
        clear_filters_btn.clicked.connect(self._clear_filters)
        filters_layout.addWidget(clear_filters_btn)

        layout.addWidget(filters_container)

        # ------------------------------------------------------------------
        # Table + models
        # ------------------------------------------------------------------
        self.table = QtWidgets.QTableView()
        self.model = InstrumentTableModel([])

        self.proxy = InstrumentFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)

        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.on_table_double_clicked)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        
        # Enable context menu
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        self.table.setWordWrap(False)
        
        # Better row height
        self.table.verticalHeader().setDefaultSectionSize(24)
        
        # Enable keyboard navigation
        self.table.setTabKeyNavigation(True)
        
        # Column width persistence (must be after header setup)
        self._restore_column_widths()
        header.sectionResized.connect(self._save_column_widths)
        
        # Search highlighting delegate
        self.highlight_delegate = HighlightDelegate("", self.table)
        self.table.setItemDelegate(self.highlight_delegate)

        layout.addWidget(self.table)
        
        # Statistics panel
        self.stats_widget = self._create_statistics_widget()
        layout.addWidget(self.stats_widget)
        
        self.setCentralWidget(central)

        # Filter signal wiring
        self.search_edit.textChanged.connect(self._on_filters_changed)
        self.status_filter_combo.currentIndexChanged.connect(self._on_filters_changed)
        self.type_filter_combo.currentIndexChanged.connect(self._on_filters_changed)
        self.due_filter_combo.currentIndexChanged.connect(self._on_filters_changed)
        
        # Update statistics when filters change
        self.proxy.rowsInserted.connect(lambda: self._update_statistics())
        self.proxy.rowsRemoved.connect(lambda: self._update_statistics())
        self.proxy.modelReset.connect(lambda: self._update_statistics())

        # Status bar with better info
        self.statusBar().showMessage("Ready - Select an instrument to get started")
        
        # Update status bar when selection changes
        self.table.selectionModel().selectionChanged.connect(self._update_status_bar)

    def load_instruments(self):
        instruments = self.repo.list_instruments()
        self.model.set_instruments(instruments)
        count = len(instruments)
        
        # Update window title with count
        filtered_count = self.proxy.rowCount()
        if filtered_count == count:
            self.setWindowTitle(f"Calibration Tracker - {count} instrument(s)")
        else:
            self.setWindowTitle(f"Calibration Tracker - {filtered_count} of {count} instrument(s)")
        
        self.statusBar().showMessage(f"Loaded {count} instrument(s)", 3000)
        self._update_statistics()
    
    def _clear_filters(self):
        """Clear all filters and reset search."""
        self.search_edit.clear()
        self.status_filter_combo.setCurrentIndex(0)
        self.type_filter_combo.setCurrentIndex(0)
        self.due_filter_combo.setCurrentIndex(0)
        self.statusBar().showMessage("Filters cleared", 2000)
    
    def _update_status_bar(self):
        """Update status bar with information about selected instrument."""
        inst_id = self._selected_instrument_id()
        if inst_id:
            inst = self.repo.get_instrument(inst_id)
            if inst:
                tag = inst.get("tag_number", "")
                location = inst.get("location", "")
                next_due = inst.get("next_due_date", "")
                status_msg = f"Selected: {tag}"
                if location:
                    status_msg += f" | Location: {location}"
                if next_due:
                    status_msg += f" | Next due: {next_due}"
                self.statusBar().showMessage(status_msg)
            else:
                self.statusBar().showMessage("Ready")
        else:
            self.statusBar().showMessage("Ready - Select an instrument to get started")
    
    def _show_table_context_menu(self, position):
        """Show context menu for table."""
        menu = QtWidgets.QMenu(self)
        
        inst_id = self._selected_instrument_id()
        if inst_id:
            menu.addAction(self.act_edit)
            menu.addAction(self.act_view_info)
            menu.addSeparator()
            menu.addAction(self.act_cal)
            menu.addAction(self.act_hist)
            menu.addSeparator()
            menu.addAction(self.act_delete)
        else:
            menu.addAction(self.act_new)
        
        menu.exec_(self.table.viewport().mapToGlobal(position))
    
    def on_view_info(self):
        """View detailed information about selected instrument."""
        inst_id = self._selected_instrument_id()
        if not inst_id:
            QtWidgets.QMessageBox.information(
                self,
                "No selection",
                "Please select an instrument to view details.",
            )
            return
        dlg = InstrumentInfoDialog(self.repo, inst_id, parent=self)
        dlg.exec_()

    def _selected_instrument_id(self):
        idx = self.table.currentIndex()
        if not idx.isValid():
            return None
        src_idx = self.proxy.mapToSource(idx)
        row = src_idx.row()
        return self.model.get_instrument_id(row)

    def on_table_double_clicked(self, index: QtCore.QModelIndex):
        if not index.isValid():
            return
        src_idx = self.proxy.mapToSource(index)
        row = src_idx.row()
        inst_id = self.model.get_instrument_id(row)
        if not inst_id:
            return
        dlg = InstrumentInfoDialog(self.repo, inst_id, parent=self)
        dlg.exec_()


    def on_new(self):
        dlg = InstrumentDialog(self.repo, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            data = dlg.get_data()
            if data:
                try:
                    inst_id = self.repo.add_instrument(data)
                    self.load_instruments()
                    self.statusBar().showMessage("New instrument created successfully", 3000)
                    # Select the newly created instrument if possible
                    # (would need to find it in the model, but this is a nice-to-have)
                except Exception as e:
                    QtWidgets.QMessageBox.critical(
                        self,
                        "Creation failed",
                        f"Failed to create instrument:\n{str(e)}",
                    )

    def on_edit(self):
        inst_id = self._selected_instrument_id()
        if not inst_id:
            QtWidgets.QMessageBox.information(
                self,
                "No selection",
                "Please select an instrument to edit.",
            )
            return
        inst = self.repo.get_instrument(inst_id)
        dlg = InstrumentDialog(self.repo, inst, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            data = dlg.get_data()
            if data:
                try:
                    self.repo.update_instrument(inst_id, data)
                    self.load_instruments()
                    self.statusBar().showMessage("Instrument updated successfully", 3000)
                except Exception as e:
                    QtWidgets.QMessageBox.critical(
                        self,
                        "Update failed",
                        f"Failed to update instrument:\n{str(e)}",
                    )

    def on_delete(self):
        inst_id = self._selected_instrument_id()
        if not inst_id:
            QtWidgets.QMessageBox.information(
                self,
                "No selection",
                "Please select an instrument to delete.",
            )
            return

        inst = self.repo.get_instrument(inst_id)
        tag = inst.get("tag_number", str(inst_id)) if inst else str(inst_id)
        location = inst.get("location", "") if inst else ""

        msg = f"Are you sure you want to delete instrument '{tag}'?"
        if location:
            msg += f"\nLocation: {location}"
        msg += "\n\n⚠️ This action cannot be undone."

        resp = QtWidgets.QMessageBox.warning(
            self,
            "Delete instrument",
            msg,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if resp != QtWidgets.QMessageBox.Yes:
            return

        try:
            self.repo.delete_instrument(inst_id)
            self.load_instruments()
            self.statusBar().showMessage(f"Deleted instrument '{tag}'", 3000)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Delete failed",
                f"Failed to delete instrument:\n{str(e)}\n\nPlease try again or contact support if the problem persists.",
            )

    def on_mark_calibrated(self):
        inst_id = self._selected_instrument_id()
        if not inst_id:
            QtWidgets.QMessageBox.information(
                self,
                "No selection",
                "Please select an instrument to mark as calibrated.",
            )
            return

        # Prefill dialog with existing last_cal_date if present
        inst = self.repo.get_instrument(inst_id)
        initial_qdate = None
        if inst and inst.get("last_cal_date"):
            try:
                d = datetime.strptime(inst["last_cal_date"], "%Y-%m-%d").date()
                initial_qdate = QtCore.QDate(d.year, d.month, d.day)
            except Exception:
                pass

        dlg = CalDateDialog(self, initial_date=initial_qdate)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return

        picked_date = dlg.get_date()
        try:
            # Update DB: last_cal_date = picked_date, next_due_date = picked_date + 1 year
            self.repo.mark_calibrated_on(inst_id, picked_date)
            self.load_instruments()
            tag = inst.get("tag_number", "instrument") if inst else "instrument"
            self.statusBar().showMessage(f"{tag} marked as calibrated on {picked_date.isoformat()}", 3000)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Update failed",
                f"Failed to mark instrument as calibrated:\n{str(e)}",
            )

    def on_destinations(self):
        dlg = DestinationsDialog(self.repo, parent=self)
        dlg.exec_()
        # Refresh instrument list so new/renamed destinations show up in table
        self.load_instruments()

    def on_cal_history(self):
        inst_id = self._selected_instrument_id()
        if not inst_id:
            QtWidgets.QMessageBox.information(
                self,
                "No selection",
                "Please select an instrument to view calibration history.",
            )
            return
        dlg = CalibrationHistoryDialog(self.repo, inst_id, parent=self)
        dlg.exec_()
        # Refresh in case calibrations were added/modified
        self.load_instruments()

    def on_templates(self):
        dlg = TemplatesDialog(self.repo, parent=self)
        dlg.exec_()

    def on_send_reminders(self):
        count = send_due_reminders_via_lan(self.repo)
        if count:
            QtWidgets.QMessageBox.information(
                self,
                "Reminders sent",
                f"LAN reminder broadcast sent for {count} instrument(s).",
            )
        else:
            QtWidgets.QMessageBox.information(
                self,
                "No reminders",
                "No instruments due within the reminder window.",
            )

    def on_settings(self):
        dlg = SettingsDialog(self.repo, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.statusBar().showMessage("Settings saved", 3000)

    def _on_filters_changed(self):
        self.proxy.set_text_filter(self.search_edit.text())
        self.proxy.set_status_filter(self.status_filter_combo.currentData() or "")
        self.proxy.set_type_filter(self.type_filter_combo.currentData() or "")
        self.proxy.set_due_filter(self.due_filter_combo.currentText())
        
        # Update window title with filtered count
        filtered_count = self.proxy.rowCount()
        total_count = self.model.rowCount()
        if filtered_count == total_count:
            self.setWindowTitle(f"Calibration Tracker - {total_count} instrument(s)")
        else:
            self.setWindowTitle(f"Calibration Tracker - {filtered_count} of {total_count} instrument(s)")
        
        self._update_statistics()

    def on_export_csv(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export current view to CSV",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)

                # headers
                headers = [
                    self.proxy.headerData(c, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
                    for c in range(self.proxy.columnCount())
                ]
                writer.writerow(headers)

                # rows (filtered/sorted view)
                for row in range(self.proxy.rowCount()):
                    row_vals = []
                    for col in range(self.proxy.columnCount()):
                        idx = self.proxy.index(row, col)
                        val = self.proxy.data(idx, QtCore.Qt.DisplayRole)
                        row_vals.append("" if val is None else str(val))
                    writer.writerow(row_vals)

            QtWidgets.QMessageBox.information(
                self,
                "Export complete",
                f"Exported {self.proxy.rowCount()} row(s) to:\n{path}",
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Export failed",
                str(e),
            )
    
    def on_export_all_calibrations(self):
        """Export all calibration records to PDF files organized by instrument type."""
        # Ask user to select base directory
        base_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select directory for calibration exports",
            "",
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks,
        )
        if not base_dir:
            return
        
        # Confirm with user
        reply = QtWidgets.QMessageBox.question(
            self,
            "Export all calibrations",
            f"This will export all calibration records to PDF files in:\n{base_dir}\n\n"
            f"Files will be organized by instrument type.\n\n"
            f"Continue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        # Show progress
        progress = QtWidgets.QProgressDialog(
            "Exporting calibrations...",
            "Cancel",
            0,
            0,
            self,
        )
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QtWidgets.QApplication.processEvents()
        
        try:
            from pdf_export import export_all_calibrations_to_directory
            result = export_all_calibrations_to_directory(self.repo, base_dir)
            
            progress.close()
            
            # Show results
            msg = (
                f"Export complete!\n\n"
                f"Successfully exported: {result['success_count']} calibration(s)\n"
                f"Attachments exported: {result.get('attachment_count', 0)}\n"
                f"Errors: {result['error_count']}"
            )
            
            if result['errors']:
                error_details = "\n".join(result['errors'][:10])  # Show first 10 errors
                if len(result['errors']) > 10:
                    error_details += f"\n... and {len(result['errors']) - 10} more errors"
                msg += f"\n\nErrors:\n{error_details}"
            
            if result['error_count'] > 0:
                QtWidgets.QMessageBox.warning(self, "Export complete with errors", msg)
            else:
                QtWidgets.QMessageBox.information(self, "Export complete", msg)
                
        except Exception as e:
            progress.close()
            QtWidgets.QMessageBox.critical(
                self,
                "Export failed",
                f"Error exporting calibrations:\n{str(e)}",
            )
    
    def _create_statistics_widget(self):
        """Create a statistics panel showing key metrics."""
        stats = QtWidgets.QWidget()
        stats_layout = QtWidgets.QHBoxLayout(stats)
        stats_layout.setContentsMargins(8, 4, 8, 4)
        stats_layout.setSpacing(15)
        
        self.total_label = QtWidgets.QLabel("Total: 0")
        self.active_label = QtWidgets.QLabel("Active: 0")
        self.overdue_label = QtWidgets.QLabel("Overdue: 0")
        self.due_soon_label = QtWidgets.QLabel("Due in 30 days: 0")
        
        # Style the labels
        for label in [self.total_label, self.active_label, self.overdue_label, self.due_soon_label]:
            label.setStyleSheet("padding: 4px 8px; border-radius: 3px;")
        
        # Color code the important ones
        self.overdue_label.setStyleSheet("padding: 4px 8px; border-radius: 3px; color: #FF6B6B; font-weight: bold;")
        self.due_soon_label.setStyleSheet("padding: 4px 8px; border-radius: 3px; color: #FFD93D;")
        
        stats_layout.addWidget(self.total_label)
        stats_layout.addWidget(self.active_label)
        stats_layout.addWidget(self.overdue_label)
        stats_layout.addWidget(self.due_soon_label)
        stats_layout.addStretch()
        
        return stats
    
    def _update_statistics(self):
        """Update statistics panel with current data."""
        instruments = self.repo.list_instruments()
        total = len(instruments)
        
        active = sum(1 for inst in instruments if inst.get("status") == "ACTIVE")
        
        overdue = 0
        due_soon = 0
        today = date.today()
        
        for inst in instruments:
            next_due = inst.get("next_due_date")
            if next_due:
                try:
                    due_date = datetime.strptime(next_due, "%Y-%m-%d").date()
                    days_left = (due_date - today).days
                    if days_left < 0:
                        overdue += 1
                    elif days_left <= 30:
                        due_soon += 1
                except Exception:
                    pass
        
        self.total_label.setText(f"Total: {total}")
        self.active_label.setText(f"Active: {active}")
        self.overdue_label.setText(f"Overdue: {overdue}")
        self.due_soon_label.setText(f"Due in 30 days: {due_soon}")
    
    def _update_search_highlight(self):
        """Update the search highlight delegate with current search text."""
        search_text = self.search_edit.text()
        self.highlight_delegate.set_search_text(search_text)
        # Trigger repaint of visible cells
        self.table.viewport().update()
    
    def _save_column_widths(self):
        """Save column widths to settings."""
        settings = QtCore.QSettings("CalibrationTracker", "ColumnWidths")
        header = self.table.horizontalHeader()
        for i in range(header.count()):
            width = header.sectionSize(i)
            settings.setValue(f"column_{i}", width)
    
    def _restore_column_widths(self):
        """Restore column widths from settings."""
        settings = QtCore.QSettings("CalibrationTracker", "ColumnWidths")
        header = self.table.horizontalHeader()
        for i in range(header.count()):
            width = settings.value(f"column_{i}", None)
            if width is not None:
                try:
                    header.resizeSection(i, int(width))
                except (ValueError, TypeError):
                    pass
    
    def on_show_shortcuts(self):
        """Show keyboard shortcuts dialog."""
        shortcuts = """
        <h2>Keyboard Shortcuts</h2>
        <table style="width: 100%; border-collapse: collapse;">
        <tr><td style="padding: 5px;"><b>Ctrl+N</b></td><td style="padding: 5px;">Create new instrument</td></tr>
        <tr><td style="padding: 5px;"><b>Ctrl+E</b></td><td style="padding: 5px;">Edit selected instrument</td></tr>
        <tr><td style="padding: 5px;"><b>Delete</b></td><td style="padding: 5px;">Delete selected instrument</td></tr>
        <tr><td style="padding: 5px;"><b>Ctrl+I</b></td><td style="padding: 5px;">View instrument details</td></tr>
        <tr><td style="padding: 5px;"><b>Ctrl+F</b></td><td style="padding: 5px;">Focus search box</td></tr>
        <tr><td style="padding: 5px;"><b>Ctrl+M</b></td><td style="padding: 5px;">Mark instrument as calibrated</td></tr>
        <tr><td style="padding: 5px;"><b>Ctrl+H</b></td><td style="padding: 5px;">View calibration history</td></tr>
        <tr><td style="padding: 5px;"><b>Ctrl+T</b></td><td style="padding: 5px;">Open templates dialog</td></tr>
        <tr><td style="padding: 5px;"><b>Ctrl+,</b></td><td style="padding: 5px;">Open settings</td></tr>
        <tr><td style="padding: 5px;"><b>Ctrl+Shift+C</b></td><td style="padding: 5px;">Export current view to CSV</td></tr>
        <tr><td style="padding: 5px;"><b>Ctrl+Shift+P</b></td><td style="padding: 5px;">Export all calibrations to PDF</td></tr>
        <tr><td style="padding: 5px;"><b>F1</b></td><td style="padding: 5px;">Show this help</td></tr>
        <tr><td style="padding: 5px;"><b>Ctrl+Q</b></td><td style="padding: 5px;">Exit application</td></tr>
        </table>
        <p><i>Tip: Double-click a row to view instrument details</i></p>
        """
        dlg = HelpDialog("Keyboard Shortcuts", shortcuts, self)
        dlg.exec_()
    
    def on_show_about(self):
        """Show about dialog."""
        about_text = """
        <h2>Calibration Tracker</h2>
        <p><b>Version:</b> 1.0</p>
        <p>A comprehensive application for managing instrument calibrations, tracking schedules, and maintaining compliance records.</p>
        
        <h3>Features</h3>
        <ul>
        <li>Instrument management and tracking</li>
        <li>Calibration record keeping</li>
        <li>Template-based calibration forms</li>
        <li>PDF and CSV export</li>
        <li>Visual indicators for due dates</li>
        <li>LAN reminder notifications</li>
        <li>Complete audit trail</li>
        </ul>
        
        <p><i>Built with PyQt5 and SQLite</i></p>
        <p style="margin-top: 20px;"><small>© 2024 Calibration Tracker</small></p>
        """
        dlg = HelpDialog("About Calibration Tracker", about_text, self)
        dlg.exec_()

def apply_global_style(app: QtWidgets.QApplication):
    """
    Apply modern, user-friendly styling to the application.
    Uses a dark theme with the specified color scheme.
    """
    # Color scheme constants
    WINDOW_COLOR = "#4F5875"
    BASE_COLOR = "#262C3D"
    ALT_BASE_COLOR = "#30374A"
    TEXT_COLOR = "#F5F5F5"
    DISABLED_TEXT = "#9299AE"
    BUTTON_COLOR = "#333A4F"
    BORDER_COLOR = "#1E3E62"
    ACCENT_ORANGE = "#DC6D18"
    TOOLTIP_BASE = "#121C2A"
    TOOLTIP_TEXT = "#F5F5F5"
    
    # Use Fusion style (modern & consistent across platforms)
    app.setStyle("Fusion")

    # Dark palette with specified colors
    palette = app.palette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(WINDOW_COLOR))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(TEXT_COLOR))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(BASE_COLOR))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(ALT_BASE_COLOR))
    palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(TOOLTIP_BASE))
    palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(TOOLTIP_TEXT))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(TEXT_COLOR))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(BUTTON_COLOR))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(TEXT_COLOR))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(ACCENT_ORANGE))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(TEXT_COLOR))
    palette.setColor(QtGui.QPalette.Link, QtGui.QColor(ACCENT_ORANGE))
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor(DISABLED_TEXT))
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(DISABLED_TEXT))
    app.setPalette(palette)

    # Modern font
    app.setFont(QtGui.QFont("Segoe UI", 9))

    # Qt Style Sheet with specified dark color scheme
    qss = f"""
    * {{
        font-family: "Segoe UI", Arial, sans-serif;
        font-size: 9pt;
    }}

    QMainWindow {{
        background-color: {WINDOW_COLOR};
    }}

    QDialog {{
        background-color: {WINDOW_COLOR};
    }}

    QToolBar {{
        background-color: {BASE_COLOR};
        border: none;
        border-bottom: 1px solid {BORDER_COLOR};
        padding: 4px;
        spacing: 4px;
    }}
    QToolBar QToolButton {{
        color: {TEXT_COLOR};
        padding: 6px 12px;
        border-radius: 4px;
        border: 1px solid transparent;
    }}
    QToolBar QToolButton:hover {{
        background-color: {ALT_BASE_COLOR};
        border: 1px solid {BORDER_COLOR};
    }}
    QToolBar QToolButton:pressed {{
        background-color: {BUTTON_COLOR};
    }}

    QStatusBar {{
        background-color: {BASE_COLOR};
        color: {TEXT_COLOR};
        border-top: 1px solid {BORDER_COLOR};
        padding: 2px;
    }}

    QPushButton {{
        background-color: {BUTTON_COLOR};
        color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
        border-radius: 4px;
        padding: 6px 14px;
        min-width: 80px;
    }}
    QPushButton:hover {{
        background-color: {ALT_BASE_COLOR};
        border-color: {ACCENT_ORANGE};
    }}
    QPushButton:pressed {{
        background-color: {BASE_COLOR};
    }}
    QPushButton:default {{
        background-color: {ACCENT_ORANGE};
        color: {TEXT_COLOR};
        border-color: {ACCENT_ORANGE};
    }}
    QPushButton:default:hover {{
        background-color: #E67D2A;
    }}
    QPushButton:disabled {{
        background-color: {BUTTON_COLOR};
        color: {DISABLED_TEXT};
        border-color: {BORDER_COLOR};
    }}

    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
        background-color: {BASE_COLOR};
        color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
        border-radius: 3px;
        padding: 4px 6px;
        selection-background-color: {ACCENT_ORANGE};
        selection-color: {TEXT_COLOR};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
        border: 2px solid {ACCENT_ORANGE};
        padding: 3px 5px;
    }}
    
    QComboBox, QDateEdit {{
        background-color: {BASE_COLOR};
        color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
        border-radius: 3px;
        padding: 3px 6px;
        min-height: 20px;
    }}
    QComboBox:focus, QDateEdit:focus {{
        border: 2px solid {ACCENT_ORANGE};
        padding: 2px 5px;
    }}
    QComboBox::drop-down, QDateEdit::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 20px;
        border-left: 1px solid {BORDER_COLOR};
        border-top-right-radius: 3px;
        border-bottom-right-radius: 3px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BASE_COLOR};
        selection-background-color: {ACCENT_ORANGE};
        selection-color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
    }}

    QLabel {{
        color: {TEXT_COLOR};
    }}
    
    QGroupBox {{
        border: 1px solid {BORDER_COLOR};
        border-radius: 4px;
        margin-top: 10px;
        padding-top: 10px;
        font-weight: bold;
        color: {TEXT_COLOR};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 8px;
        padding: 0px 4px;
        color: {TEXT_COLOR};
    }}

    QTableView {{
        background-color: {BASE_COLOR};
        alternate-background-color: {ALT_BASE_COLOR};
        gridline-color: {BORDER_COLOR};
        color: {TEXT_COLOR};
        selection-background-color: {ACCENT_ORANGE};
        selection-color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
    }}
    QTableView::item:hover {{
        background-color: {ALT_BASE_COLOR};
    }}
    QHeaderView::section {{
        background-color: {BUTTON_COLOR};
        color: {TEXT_COLOR};
        padding: 6px;
        border: none;
        border-right: 1px solid {BORDER_COLOR};
        border-bottom: 2px solid {BORDER_COLOR};
        font-weight: bold;
    }}
    QHeaderView::section:hover {{
        background-color: {ALT_BASE_COLOR};
    }}

    QScrollBar:vertical {{
        background-color: {BASE_COLOR};
        width: 12px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background-color: {BUTTON_COLOR};
        min-height: 30px;
        border-radius: 6px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {ALT_BASE_COLOR};
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background-color: {BASE_COLOR};
        height: 12px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {BUTTON_COLOR};
        min-width: 30px;
        border-radius: 6px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {ALT_BASE_COLOR};
    }}
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    
    QTabWidget::pane {{
        border: 1px solid {BORDER_COLOR};
        background-color: {WINDOW_COLOR};
    }}
    QTabBar::tab {{
        background-color: {BUTTON_COLOR};
        color: {TEXT_COLOR};
        padding: 8px 16px;
        border: 1px solid {BORDER_COLOR};
        border-bottom: none;
    }}
    QTabBar::tab:selected {{
        background-color: {WINDOW_COLOR};
        border-bottom: 2px solid {ACCENT_ORANGE};
    }}
    QTabBar::tab:hover {{
        background-color: {ALT_BASE_COLOR};
    }}
    
    QMenuBar {{
        background-color: {BASE_COLOR};
        color: {TEXT_COLOR};
        border-bottom: 1px solid {BORDER_COLOR};
    }}
    QMenuBar::item {{
        background-color: transparent;
        padding: 4px 8px;
    }}
    QMenuBar::item:selected {{
        background-color: {ALT_BASE_COLOR};
    }}
    QMenu {{
        background-color: {BASE_COLOR};
        color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
    }}
    QMenu::item:selected {{
        background-color: {ACCENT_ORANGE};
    }}
    
    QToolTip {{
        background-color: {TOOLTIP_BASE};
        color: {TOOLTIP_TEXT};
        border: 1px solid {BORDER_COLOR};
        padding: 4px;
    }}
    """
    app.setStyleSheet(qss)

def run_gui(repo: CalibrationRepository):
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
        install_update_check_into_main_window(win, check_on_startup=True)
    except Exception:
        pass
    win.showMaximized()
    app.exec_()
