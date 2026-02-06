# ui/dialogs/all_dialogs.py - All dialog classes (extracted from ui_main)
# Some dialogs split into separate modules; re-exported here for backward compatibility.

# Re-export from split modules
from ui.dialogs.audit_log import AuditLogDialog
from ui.dialogs.destination_edit_dialog import DestinationEditDialog
from ui.dialogs.destinations_dialog import DestinationsDialog
from ui.dialogs.personnel_edit_dialog import PersonnelEditDialog
from ui.dialogs.personnel_dialog import PersonnelDialog
from ui.dialogs.instrument_info import InstrumentInfoDialog
from ui.dialogs.batch import BatchUpdateDialog, BatchAssignInstrumentTypeDialog, CalDateDialog
from ui.dialogs.instrument_dialog import InstrumentDialog
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.attachments_dialog import AttachmentsDialog
from ui.dialogs.template_edit_dialog import TemplateEditDialog
from ui.dialogs.field_edit_dialog import FieldEditDialog
from ui.dialogs.explain_tolerance_dialog import ExplainToleranceDialog
from ui.dialogs.template_fields_dialog import TemplateFieldsDialog
from ui.dialogs.calibration_history_dialog import CalibrationHistoryDialog
from ui.dialogs.templates_dialog import TemplatesDialog
from ui.dialogs.calibration_form_dialog import CalibrationFormDialog
