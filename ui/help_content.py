# ui/help_content.py - Help dialog content and dialog


from PyQt5 import QtWidgets, QtCore, QtGui


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
                <li><b>Type</b>: Data type — text, number, bool, date, signature, reference, tolerance, convert, stat, plot, field header</li>
                <li><b>Appear in calibrations table?</b>: For number fields only. When checked, this field's value is shown in the Variables column alongside reference values for each calibration point in the calibration history.</li>
                <li><b>Unit</b>: Unit of measurement (number, convert, tolerance, reference, stat)</li>
                <li><b>Reference value</b>: Shown when Type is reference; the reference/nominal value for this point</li>
                <li><b>Required</b>: Check if field must be filled (not used for tolerance, convert, or stat)</li>
                <li><b>Sort order</b>: Order in which fields appear (lower numbers first)</li>
                <li><b>Group</b>: Group name (fields with same group appear together). For tolerance/convert equations, val1–val12 field choices can be filtered by this group.</li>
                <li><b>Numbers after decimal</b>: 0–4 decimal places for displayed values (number, convert, tolerance, reference, stat)</li>
            </ul>
            
            <h4>Field types:</h4>
            <ul>
                <li><b>Tolerance</b>: Read-only field that shows a pass/fail result from an equation (must contain &lt;, &gt;, &lt;=, &gt;=, or ==)</li>
                <li><b>Convert</b>: Read-only field that shows a computed value from an expression (e.g. unit conversion)</li>
                <li><b>Stat</b>: Read-only field that shows a statistical result. Stat has access to <b>all template fields</b> for val1–val12; no group filter.</li>
                <li><b>Plot</b>: Scatter chart in PDF export. Use <code>PLOT([x1, x2, ...], [y1, y2, ...])</code>. Each point is (x1,y1), (x2,y2), etc. When X and Y are <b>side by side</b> in the table (e.g. Certified Weight then Balance Response), set ref1=X1, ref2=Y1, ref3=X2, ref4=Y2, … and use <code>PLOT([val1, val3, val5, ...], [val2, val4, val6, ...])</code>.</li>
                <li><b>Field Header</b>: Display-only. Shows the field's label as a header for the group it is assigned to (in the calibration form and in PDF export). No value is stored.</li>
            </ul>
            
            <h4>Tolerance type (for number/bool with tolerance):</h4>
            <ul>
                <li><b>None</b>: No pass/fail tolerance</li>
                <li><b>Equation</b>: Pass/fail from a formula (must contain a comparison). Use val1–val12 to reference other fields.</li>
                <li><b>Boolean</b>: Pass when the value is True or False (for checkbox fields)</li>
            </ul>
            
            <h4>Equation variables (val1–val12):</h4>
            <p>For <b>Tolerance type = Equation</b>, <b>Convert</b>, and <b>Stat</b>:</p>
            <ul>
                <li><b>Operators</b>: + − * / ^ (power), <code>&lt;</code> <code>&gt;</code> <code>&lt;=</code> <code>&gt;=</code> <code>==</code></li>
                <li><b>Functions</b>: <code>ABS()</code>, <code>MIN()</code>, <code>MAX()</code>, <code>ROUND()</code>, <code>AVERAGE()</code>, <code>LINEST(ys, xs)</code> (slope), <code>INTERCEPT(ys, xs)</code>, <code>RSQ(ys, xs)</code> (R²), <code>CORREL(ys, xs)</code>, <code>STDEV([vals])</code>, <code>STDEVP([vals])</code>, <code>MEDIAN([vals])</code></li>
                <li><b>nominal</b>: Expected value (from reference or context)</li>
                <li><b>reading</b>: Measured or computed value for this point</li>
                <li><b>val1 … val12</b>: Values from the fields you assign to val1–val12. Use the dropdowns to pick which field each val refers to. For <b>stat</b> type, all template fields are available; for tolerance/convert, options can be limited by Group.</li>
            </ul>
            <p>Examples: <code>reading &lt;= 0.02 * nominal</code>; <code>val1 &lt; val2 + 0.5</code>; <code>LINEST([val1, val2, val3], [1, 2, 3])</code>; <code>STDEV([val1, val2, val3])</code>; <code>MEDIAN([val1, val2, val3, val4])</code>. Use <b>+ Add value</b> to show val6–val12 rows.</p>
            
            <h4>Autofill Feature:</h4>
            <ul>
                <li><b>Autofill from previous group</b>: If checked, this field will automatically fill matching fields in the next group when you navigate forward. Fields match by name or label.</li>
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
                <li><b>Delete</b>: Remove the selected field (select one or more rows for batch delete)</li>
                <li><b>Duplicate group</b>: Copy all fields from one group to create a new group</li>
                <li><b>Batch change equation</b>: Set the same tolerance equation for all selected fields</li>
                <li><b>Batch apply unit</b>: Set unit for selected fields</li>
                <li><b>Batch set decimal</b>: Set numbers after decimal (0–4) for selected number, convert, reference, tolerance, and stat fields</li>
                <li><b>Batch set group</b>: Set group name for selected fields</li>
                <li><b>Explain tolerance</b>: Open help that explains how the selected field's tolerance is evaluated</li>
            </ul>
            
            <h4>Table Columns (click headers to sort):</h4>
            <ul>
                <li><b>Name</b>, <b>Label</b>, <b>Type</b>, <b>Unit</b>, <b>Required</b>, <b>Sort</b>, <b>Group</b>, <b>Tolerance</b></li>
            </ul>
            
            <h4>Field types and equations:</h4>
            <p><b>Tolerance</b>, <b>Convert</b>, and <b>Stat</b> types use equations with variables nominal, reading, and val1–val12. Stat type has access to <b>all template fields</b> for value selection. See Field Edit Help for equation syntax and LINEST, STDEV, MEDIAN, etc.</p>
            
            <h4>Tips:</h4>
            <ul>
                <li>Organize related fields into groups</li>
                <li>Use consistent naming for fields that should autofill</li>
                <li>Use Batch set group, unit, or decimal to update many fields at once</li>
            </ul>
            """
        ),
        "CalibrationHistoryDialog": (
            "Calibration History",
            """
            <h3>Viewing Calibration History</h3>
            <p>View all calibration records for an instrument. The dialog opens at approximately 80% of the screen size.</p>
            
            <h4>Records Table:</h4>
            <ul>
                <li>Shows all calibration records with date, template, performed by, and result</li>
                <li>Select a record to view tolerance details below</li>
                <li><b>Show archived</b>: Include archived (soft-deleted) records in the list</li>
            </ul>
            
            <h4>Tolerance Values Table:</h4>
            <p>When a record is selected, the details area shows a table of tolerance (pass/fail) results:</p>
            <ul>
                <li><b>Variables</b>: Reference values (ref_label: value) and number fields with "Appear in calibrations table" checked</li>
                <li><b>Tolerance</b>: Field label and measured/computed value (label: value)</li>
                <li><b>Result</b>: PASS or FAIL for that point</li>
                <li><b>Group highlighting</b>: Rows are colored by group — green if all points in the group pass, red if any point fails</li>
                <li>Template notes appear below the table when present</li>
            </ul>
            
            <h4>Records Table Columns:</h4>
            <ul>
                <li><b>Date</b>: Calibration date</li>
                <li><b>Template</b>: Template used for the calibration</li>
                <li><b>Performed by</b>: Person who performed the calibration</li>
                <li><b>Result</b>: Overall result (PASS, FAIL, CONDITIONAL)</li>
                <li><b>State</b>: Record state (Draft, Approved, Archived)</li>
            </ul>
            
            <h4>Actions:</h4>
            <ul>
                <li><b>➕ New Calibration</b>: Create a new calibration record</li>
                <li><b>✏️ View/Edit</b>: View or edit the selected calibration</li>
                <li><b>📄 Export PDF</b>: Export the selected calibration to PDF</li>
                <li><b>📎 Open File</b>: Open attached calibration file (if any)</li>
                <li><b>🗑️ Delete</b>: Archive or permanently delete the selected calibration record</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Use the tolerance table to quickly spot failing groups (red rows)</li>
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
                <li><b>Add</b>: Create a new calibration template</li>
                <li><b>Edit</b>: Modify the selected template</li>
                <li><b>Clone</b>: Copy a template to create a new one</li>
                <li><b>Delete</b>: Remove the selected template (only if no calibrations use it)</li>
                <li><b>Fields...</b>: Manage fields for the selected template</li>
            </ul>
            
            <h4>Tips:</h4>
            <ul>
                <li>Create templates for common calibration procedures</li>
                <li>Only active templates appear when creating calibrations</li>
                <li>Use the Fields button to configure what data is collected</li>
                <li>Use Clone to quickly create a template based on an existing one</li>
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
                <li><b>Checkboxes</b>: Click to check/uncheck (Pass/Fail for bool tolerance)</li>
                <li><b>Date fields</b>: Click the calendar icon to select a date</li>
                <li><b>Signature fields</b>: Select a signature from the dropdown</li>
                <li><b>Computed fields</b>: Tolerance, convert, and stat fields are automatically calculated (read-only)</li>
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


class HelpDialog(QtWidgets.QDialog):
    """Reusable help dialog that displays formatted help text."""

    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Help - {title}")
        self.resize(600, 500)

        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        if parent:
            self.setWindowModality(QtCore.Qt.WindowModal)

        layout = QtWidgets.QVBoxLayout(self)

        title_label = QtWidgets.QLabel(f"<h2>{title}</h2>")
        layout.addWidget(title_label)

        content_text = QtWidgets.QTextEdit()
        content_text.setReadOnly(True)
        content_text.setHtml(content)
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WordWrap)
        content_text.document().setDefaultTextOption(option)
        layout.addWidget(content_text)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)
