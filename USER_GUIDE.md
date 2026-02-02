# Calibration Tracker - User Guide

## Table of Contents
1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Main Interface Overview](#main-interface-overview)
4. [Managing Instruments](#managing-instruments)
5. [Calibration Management](#calibration-management)
6. [Calibration Templates](#calibration-templates)
7. [Filters and Search](#filters-and-search)
8. [Exporting Data](#exporting-data)
9. [Settings and Configuration](#settings-and-configuration)
10. [Checking for Updates](#checking-for-updates)
11. [Keyboard Shortcuts](#keyboard-shortcuts)
12. [Tips and Best Practices](#tips-and-best-practices)
13. [Troubleshooting](#troubleshooting)

---

## Introduction

The **Calibration Tracker** is a comprehensive application designed to help you manage instrument calibrations efficiently. It tracks calibration schedules, stores calibration records, generates reports, and helps ensure compliance with calibration requirements.

### Key Features

- **Instrument Management**: Track all your instruments with detailed information including locations, types, serial numbers, descriptions, and calibration schedules
- **Calibration Records**: Record and manage calibration data with support for templates and external calibration files
- **Visual Indicators**: Color-coded table rows show overdue instruments and upcoming due dates
- **Template System**: Create reusable calibration templates with custom fields and real-time autofill capabilities
- **Export Capabilities**: Export data to CSV or generate PDF reports with automatic formatting
- **LAN Reminders**: Send network reminders for instruments due for calibration
- **Search and Filter**: Quickly find instruments using multiple filter criteria with search term highlighting
- **History Tracking**: View complete calibration history for any instrument
- **Statistics Dashboard**: Real-time statistics showing total, active, overdue, and due instruments
- **Contextual Help**: Help dialogs available on all windows via the question mark button
- **Check for Updates**: Help → Check for Updates to see if a newer version is available
- **Themes**: Help → Theme — choose Fusion, Taylor's Theme, Tess's Theme, Retina Seering, or Vice; your choice is saved
- **Text Size**: Help → Text Size — Small, Medium, Large, or Extra Large; your choice is saved
- **Customizable Interface**: Column widths persist between sessions, window title shows version and filtered counts
- **Automatic Backups**: Daily database backups are kept in a `backups/` folder

---

## Getting Started

### Launching the Application

1. Run the application by executing `main.py` or the compiled executable
2. The application will automatically create a database file (`calibration.db`) if it doesn't exist
3. The main window will open showing all instruments in a table view

### First Steps

1. **Set Up Instrument Types** (Optional but recommended):
   - Go to **Tools → Settings**
   - Navigate to the **Instrument Types** tab
   - Add common instrument types you'll be tracking (e.g., "Thermometer", "Pressure Gauge", "Flow Meter")

2. **Set Up Destinations** (If using SEND_OUT calibrations):
   - Go to **Tools → Destinations**
   - Add calibration service providers or internal departments

3. **Create Your First Instrument**:
   - Click the **New** button in the toolbar (or press `Ctrl+N`)
   - Fill in the required fields (ID and Next due date)
   - Click **OK** to save

---

## Main Interface Overview

### Main Window Layout

The main window consists of several key areas:

#### 1. Menu Bar and Toolbar
- **Help → Theme**: Choose a color theme (Fusion, Taylor's Theme, Tess's Theme, Retina Seering, Vice). The selected theme is remembered for next time.
- **Help → Text Size**: Choose Small (8pt), Medium (9pt), Large (10pt), or Extra Large (11pt). The selected size is remembered for next time.
- **Help → Check for Updates**: Manually check for a newer version. If you're current, a message says so; if an update is available, you can choose to update now or later. The application also checks automatically on startup but only shows a window when an update is available or when the check fails.
- **Toolbar** (quick access): **New**, **Edit**, **Mark Calibrated**, **History**, **Settings**

#### 2. Filter Bar
Below the toolbar, allows you to filter instruments:
- **Search Box**: Search by ID, location, destination, or instrument type
- **Status Filter**: Filter by instrument status (ACTIVE, RETIRED, OUT_FOR_CAL)
- **Type Filter**: Filter by instrument type
- **Due Filter**: Filter by calibration due date (All, Overdue, Due in 30 days)
- **Clear Button**: Reset all filters

#### 3. Instrument Table
The main table displays all instruments with columns:
- **ID**: Instrument tag number or identifier
- **Location**: Current location of the instrument
- **Type**: Calibration type (SEND_OUT or PULL_IN)
- **Destination**: Calibration destination (for SEND_OUT)
- **Last Cal**: Last calibration date
- **Next Due**: Next calibration due date
- **Days Left**: Number of days until calibration is due (negative = overdue)
- **Status**: Current instrument status
- **Instrument Type**: Type of instrument (e.g., "Thermometer")

**Table Features**:
- **Resizable Columns**: Drag column borders to adjust widths
- **Persistent Widths**: Column widths are automatically saved and restored when you restart the application
- **Sortable**: Click any column header to sort; click again to reverse sort order

#### 4. Statistics Dashboard
Located above the table, displays real-time statistics:
- **Total Instruments**: Total number of instruments in the database
- **Active**: Number of active instruments
- **Overdue**: Number of instruments past their due date
- **Due in 30 Days**: Number of instruments due within the next 30 days

These statistics update automatically as you filter, add, or modify instruments.

#### 5. Status Bar
At the bottom, shows:
- Information about the selected instrument (tag, location, next due date)
- "Ready" message when no instrument is selected

#### 6. Window Title
The window title dynamically shows:
- Application version (from the VERSION file)
- Total number of instruments and number of filtered instruments (when filters are active)
- Example: "Calibration Tracker - 1.3.0 - 150 instruments (25 shown)"

### Visual Indicators

The table uses color coding to highlight important information:

- **Red background/text**: Instruments that are overdue (past due date)
- **Yellow background**: Instruments due within 7 days
- **Orange background**: Instruments due within 30 days
- **Normal**: Instruments with more than 30 days remaining

### Context Menu

Right-click on any instrument in the table to access:
- **Edit**: Edit the instrument
- **View Details**: View detailed instrument information
- **Mark Calibrated**: Record a new calibration
- **Cal History**: View calibration history
- **Delete**: Delete the instrument

### Column Customization

- **Resizable Columns**: Drag column borders to adjust widths
- **Persistent Widths**: Column widths are automatically saved and restored when you restart the application
- **Sortable Columns**: Click any column header to sort; click again to reverse sort order

---

## Managing Instruments

### Creating a New Instrument

1. Click the **New** button in the toolbar (or press `Ctrl+N`)
2. Fill in the instrument details:
   - **ID*** (Required): Unique identifier for the instrument
   - **Serial Number**: Manufacturer's serial number (optional)
   - **Description**: Detailed description of the instrument (optional)
   - **Current location**: Where the instrument is currently located
   - **Instrument type**: Select from predefined types
   - **Cal type**: Choose SEND_OUT (sent out for calibration) or PULL_IN (calibrated in-house)
   - **Destination**: Select calibration destination (for SEND_OUT)
   - **Last cal date**: Date of last calibration
   - **Next due date*** (Required): When calibration is next due
   - **Status**: ACTIVE, RETIRED, or OUT_FOR_CAL
   - **Notes**: Any additional notes about the instrument
3. Click **OK** to save

**Tip**: Click the **?** (question mark) button in any dialog to view contextual help for that window.

**Tip**: When you set the "Last cal date", the "Next due date" automatically updates to one year later.

### Editing an Instrument

1. Select an instrument in the table
2. Click **Edit** in the toolbar (or press `Ctrl+E`, or double-click the row)
3. Make your changes
4. Click **OK** to save

### Viewing Instrument Details

1. Select an instrument in the table
2. Click **View Details** from the context menu (or press `Ctrl+I`)
3. The dialog shows:
   - All instrument information
   - Complete calibration history
   - Change history (audit log)
   - Attachments

### Deleting an Instrument

1. Select an instrument in the table
2. Right-click and choose **Delete** (or press `Delete` key)
3. Confirm the deletion in the warning dialog

**Warning**: Deleting an instrument cannot be undone. All associated calibration records will also be deleted.

### Instrument Status

Instruments can have three statuses:

- **ACTIVE**: Instrument is in active use and requires regular calibration
- **RETIRED**: Instrument is no longer in use
- **OUT_FOR_CAL**: Instrument is currently out for calibration

---

## Calibration Management

### Recording a New Calibration

There are two ways to record a calibration:

#### Method 1: Using a Template (Recommended)

1. Select an instrument in the table
2. Click **Mark Calibrated** in the toolbar (or press `Ctrl+M`)
3. Choose **"Use template"** when prompted
4. Select the appropriate calibration template
5. Fill in the calibration form:
   - Navigate between groups using **Previous group** and **Next group** buttons
   - Fill in all required fields (marked with *)
   - The form supports:
     - **Text fields**: For text or number values
     - **Checkboxes**: For yes/no values
     - **Date fields**: For date values
     - **Signature fields**: Select a signature from the dropdown menu
     - **Computed fields**: Automatically calculated (read-only)
6. Enter calibration metadata:
   - **Calibration date**: Date the calibration was performed
   - **Performed by**: Name of person who performed calibration
   - **Result**: PASS, FAIL, or CONDITIONAL
   - **Notes**: Additional notes about the calibration
7. Click **OK** to save

**Autofill Feature**: If a template field has "Autofill from previous group" enabled, when you navigate to the next group, matching fields will automatically fill with values from the previous group. This allows you to quickly copy values forward as you progress through multiple groups.

**Tip**: Click the **?** (question mark) button in any dialog to view contextual help for that window.

#### Method 2: External File (Out-of-House Calibration)

1. Select an instrument in the table
2. Click **Mark Calibrated** in the toolbar
3. Choose **"External file (out-of-house)"** when prompted
4. Select the calibration certificate file (PDF, image, etc.)
5. Enter calibration metadata:
   - **Calibration date**: Date on the certificate
   - **Performed by**: Calibration service provider
   - **Result**: PASS, FAIL, or CONDITIONAL
   - **Notes**: Any additional information
6. Click **OK** to save

The file will be attached to the calibration record and can be viewed later.

### Viewing Calibration History

1. Select an instrument in the table
2. Click **History** in the toolbar (or press `Ctrl+H`, or right-click and choose **Cal History**)
3. The dialog shows:
   - List of all calibration records for the instrument
   - Details panel showing:
     - Calibration date and metadata
     - All field values and difference calculations
     - Template notes (if using a template)
     - Attached files (if any)
4. Actions available:
   - **New**: Create a new calibration record
   - **View/Edit**: View or edit the selected calibration
   - **Export PDF**: Export the selected calibration to PDF
   - **Open File**: Open attached calibration file
   - **Delete**: Delete the calibration record

### Editing a Calibration Record

1. Open the calibration history (see above)
2. Select a calibration record
3. Click **View/Edit**
4. Make your changes
5. Click **OK** to save

### Exporting a Calibration to PDF

1. Open the calibration history
2. Select a calibration record
3. Click **Export PDF**
4. Choose a location and filename
5. The PDF will include:
   - All calibration data organized by groups
   - Headers for each group
   - Difference values per point
   - Template notes (permanent notes from the template, always included)

---

## Calibration Templates

Templates allow you to create standardized calibration forms that can be reused for multiple instruments.

### Creating a Template

1. Go to **Calibrations → Templates** (or press `Ctrl+T`)
2. Click **New**
3. Enter template details:
   - **Name**: Template name (e.g., "Weather Station Calibration")
   - **Version**: Version number
   - **Active**: Check to make template available for use
   - **Notes**: Permanent notes that appear at the bottom of every calibration record created from this template (read-only in calibration forms)
4. Click **OK**

### Managing Template Fields

1. Open the Templates dialog
2. Select a template
3. Click **Fields**
4. The Fields dialog allows you to:
   - **Add Field**: Create a new field
   - **Edit Field**: Modify an existing field
   - **Delete Field**: Remove a field
   - **Duplicate Group**: Copy all fields from one group to create a new group

### Field Configuration

When creating or editing a field, you can configure:

- **Name** (Required): Internal field name (used for matching in autofill)
- **Label** (Required): Display label shown on the form
- **Type**: Data type (text, number, bool/checkbox, date, signature)
  - **text**: Text or number input
  - **number**: Numeric input
  - **bool**: Checkbox (yes/no)
  - **date**: Date picker
  - **signature**: Signature selection dropdown (see Signature Fields below)
- **Signature**: When type is "signature", select the default signature from the dropdown (optional)
- **Unit**: Unit of measurement (e.g., "°C", "psi", "V")
- **Required**: Whether the field must be filled
- **Sort order**: Order in which fields appear
- **Group**: Group name (fields with the same group appear together)
- **Calculation** (Optional): For computed fields:
  - **ABS_DIFF**: Absolute difference between two fields
  - **PCT_ERROR**: Percentage error calculation
- **Autofill from previous group**: If checked, this field will automatically fill matching fields in the next group when you click "Next group"

### Signature Fields

Signature fields allow you to add signature selections to calibration forms. When a signature field is added to a template:

1. **Setting Up Signatures**: 
   - Place signature image files (PNG, JPG, JPEG, GIF, or BMP) in the `Signatures` folder in the application directory
   - Each file should be named with the person's name (e.g., "John Smith.png")
   - The filename (without extension) will appear in the dropdown

2. **Creating a Signature Field**:
   - In the template field editor, select "signature" as the Type
   - A "Signature" dropdown will appear
   - Optionally select a default signature for this field
   - The signature dropdown will be available when filling out calibrations

3. **Using Signature Fields in Calibrations**:
   - When filling out a calibration form, signature fields display a dropdown
   - Select the appropriate person's signature from the dropdown
   - The selected signature will appear in the exported PDF

4. **PDF Export**:
   - Signature images are automatically embedded in PDF exports
   - Signatures appear in table cells where signature fields are used
   - If a signature file is missing, the filename will be displayed instead

### Autofill Feature

The autofill feature is useful when you have multiple groups with the same fields. For example, if you're calibrating multiple temperature points:

1. Enable "Autofill from previous group" for the "Temperature" field in any group
2. Create subsequent groups with a field named "Temperature" (same name or label)
3. When filling out a calibration:
   - Fill in the temperature in the first group
   - Navigate to the next group
   - The temperature field will already be filled with the same value
   - Changes in the first group update subsequent groups in real-time

**Note**: Autofill matches fields by name or label. Fields must have the same name or label to autofill.

### Duplicating Groups

To quickly create multiple similar groups:

1. Open the Fields dialog for a template
2. Click **Duplicate Group**
3. Enter the source group name and new group name
4. Optionally specify suffix replacements (e.g., replace "_1" with "_2" in field names)
5. Click **OK**

All fields from the source group will be copied to the new group.

---

## Filters and Search

### Search Functionality

The search box at the top allows you to quickly find instruments by:
- Instrument ID (tag number)
- Location
- Destination name
- Instrument type name

**Features**:
- **Real-time filtering**: Results update as you type
- **Search highlighting**: Matching text is highlighted in yellow within table cells
- **Case-insensitive**: Search is not case-sensitive
- **Clear button**: Click the X button to clear the search

**Tip**: Press `Ctrl+F` to quickly focus the search box.

### Status Filter

Filter instruments by their status:
- **All Statuses**: Show all instruments
- **ACTIVE**: Only active instruments
- **RETIRED**: Only retired instruments
- **OUT_FOR_CAL**: Instruments currently out for calibration

### Type Filter

Filter by instrument type. The list is populated from your instrument types.

### Due Date Filter

Filter by calibration due date:
- **All**: Show all instruments
- **Overdue**: Instruments past their due date
- **Due in 30 days**: Instruments due within the next 30 days

### Clearing Filters

Click the **Clear** button to reset all filters and show all instruments.

### Sorting

Click any column header to sort by that column. Click again to reverse the sort order.

---

## Exporting Data

### Export Current View to CSV

Export the currently filtered and sorted table to a CSV file:

1. Go to **File → Export → Current view to CSV...** (or press `Ctrl+Shift+C`)
2. Choose a location and filename
3. Click **Save**

The CSV file will contain all visible instruments with their current data.

### Export All Calibrations to PDF

Export all calibration records organized by instrument type:

1. Go to **File → Export → All calibrations to PDF...** (or press `Ctrl+Shift+P`)
2. Select a base directory
3. Confirm the export
4. The system will:
   - Create subdirectories for each instrument type
   - Generate a PDF for each calibration record (instrument info, template name, cal date, performed by, result, notes, and calibration values)

**Example structure**:
```
Calibrations/
  ├── Weather Stations/
  │   ├── WS-001_2024-01-15.pdf
  │   └── WS-001_2024-02-20.pdf
  └── Thermometers/
      ├── TH-001_2024-01-10.pdf
      └── TH-002_2024-01-12.pdf
```

A summary message shows how many PDFs were exported successfully and any errors.

### Export Individual Calibration to PDF

1. Open the calibration history for an instrument
2. Select a calibration record
3. Click **Export PDF**
4. Choose a location and filename
5. Click **Save**

**PDF Features**:
- **Logo**: In-house calibration PDFs can include the AHI logo (centered at top) when `AHI_logo.png` is present in the app folder
- **Instrument and record info**: Tag, serial, description, location, template, cal date, performed by, result, notes
- **Calibration values**: Template field labels and values in a table
- **Automatic formatting**: Content is laid out for clear printing

---

## Settings and Configuration

### Accessing Settings

Go to **Tools → Settings** (or press `Ctrl+,`)

### Settings Tabs

#### General Settings
- Configure general application preferences

#### Instrument Types
Manage instrument types:
- **Add**: Create a new instrument type
- **Edit**: Modify an existing type
- **Delete**: Remove a type (only if no instruments use it)

#### Reminders
Configure calibration reminders:
- **Reminder window (days)**: How many days before due date to send reminders
- **LAN broadcast settings**: Configure network reminder broadcasts

### Database Path Configuration

To use a different database location (e.g., for development or a different site):

1. **Config file**: Copy `config.example.json` to `config.json` in the same folder as the app, and set `db_path` to your database path. Use absolute paths (e.g., `Z:\Shared\Lab\calibration.db`) or paths relative to the config file.
2. **Alternative**: Add `db_path` to `update_config.json` if you already use it.
3. **Environment variable**: Set `CALIBRATION_TRACKER_DB_PATH` to override any config file.

If none are set, the app uses the built-in default path. The last-used database path is saved and reused after updates.

### Themes and Text Size

- **Help → Theme**: Choose a color theme. Options include Fusion (default dark), Taylor's Theme, Tess's Theme, Retina Seering (bright, minimal), and Vice (cyan/pink/mint on dark). Your choice is saved and used the next time you start the app.
- **Help → Text Size**: Choose Small (8pt), Medium (9pt), Large (10pt), or Extra Large (11pt). Your choice is saved and used the next time you start the app.

### Checking for Updates

1. Go to **Help → Check for Updates...**
2. The application contacts the update server and compares your installed version with the latest.
3. **If you're already on the latest version**: A message says "You're already on the latest version (x.y)."
4. **If an update is available**: You can choose **Update now** (the app will close and run the updater, then reopen with the new version) or **Later**.
5. **Automatic check on startup**: The app checks for updates when it starts. It only shows a window if an update is available or if the check fails—you will not see a "you're current" popup on startup.

**Note**: "Update now" requires Python to be on your system PATH when running the installed executable. The installer can add Python to your PATH if it finds an installation. Updates are delivered from a release package that includes the new executable, so you get new themes, PDF export, and other UI changes.

### Destinations

Manage calibration destinations (for SEND_OUT calibrations):

1. Go to **Tools → Destinations**
2. **Add**: Create a new destination
3. **Edit**: Modify an existing destination
4. **Delete**: Remove a destination (only if no instruments use it)

### Sending LAN Reminders

To send reminders for instruments due for calibration:

1. Go to **Tools → Send Reminders**
2. The system will broadcast reminders via LAN for all instruments due within the reminder window
3. A message will show how many reminders were sent

**Note**: This feature requires network configuration and may require administrator privileges.

---

## Keyboard Shortcuts

### General Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | Create new instrument |
| `Ctrl+E` | Edit selected instrument |
| `Delete` | Delete selected instrument |
| `Ctrl+I` | View instrument details |
| `Ctrl+F` | Focus search box |
| `Ctrl+M` | Mark instrument as calibrated |
| `Ctrl+H` | View calibration history |
| `Ctrl+T` | Open templates dialog |
| `Ctrl+,` | Open settings |
| `Ctrl+Shift+C` | Export current view to CSV |
| `Ctrl+Shift+P` | Export all calibrations to PDF |
| `Ctrl+Q` or `Alt+F4` | Exit application |

### Table Navigation

- **Arrow Keys**: Navigate between cells
- **Enter**: Edit selected instrument
- **Double-click**: View instrument details
- **Right-click**: Open context menu

---

## Tips and Best Practices

### Organizing Instruments

1. **Use consistent ID formats**: Establish a naming convention (e.g., "WS-001", "TH-002")
2. **Keep locations updated**: Update instrument locations when they move
3. **Use instrument types**: Create types for common instruments to enable better filtering
4. **Set appropriate statuses**: Mark instruments as RETIRED when no longer in use

### Calibration Workflow

1. **Use templates**: Create templates for common calibration procedures to ensure consistency
2. **Record calibrations promptly**: Enter calibration data as soon as it's available
3. **Attach certificates**: For external calibrations, always attach the certificate file
4. **Review history regularly**: Check calibration history to identify patterns or issues

### Template Design

1. **Plan your groups**: Organize related fields into logical groups
2. **Use autofill wisely**: Enable autofill for fields that should be the same across groups
3. **Name fields consistently**: Use the same name/label for fields that should autofill
4. **Test templates**: Create a test instrument and calibration to verify template behavior

### Data Management

1. **Automatic backups**: The app creates daily backups in the `backups/` folder; keep these or copy them off as needed
2. **Export important data**: Periodically export calibration records to PDF for archival
3. **Review overdue items**: Use the "Overdue" filter regularly to stay on top of due dates
4. **Keep notes updated**: Add notes to instruments and calibrations for important information

### Performance Tips

1. **Use filters**: Filter the table to show only relevant instruments
2. **Sort efficiently**: Sort by the column you're most interested in
3. **Close dialogs**: Close dialogs when not in use to free resources

---

## Troubleshooting

### Common Issues

#### Database Errors

**Problem**: "Unable to open database file" or "Cannot open database"

**Solution**:
- Ensure the database path is correct. You can configure it via `config.json` (copy from `config.example.json`) or the `CALIBRATION_TRACKER_DB_PATH` environment variable.
- If using a network path (e.g., `Z:\`), ensure the drive is connected and the path is accessible.
- Check that the folder exists and you have read and write permissions.

**Problem**: "Database locked" or similar errors

**Solution**:
- Close other instances of the application
- Check if another program is accessing the database file
- Ensure you have write permissions to the database directory

#### Missing Instruments

**Problem**: Instruments not showing in the table

**Solution**:
- Check if filters are active (click "Clear" to reset)
- Verify the instrument status (retired instruments may be filtered out)
- Check if the instrument was accidentally deleted

#### Template Not Appearing

**Problem**: Template doesn't show when creating a calibration

**Solution**:
- Ensure the template is marked as "Active" in the Templates dialog
- Check that the template has at least one field defined
- Verify the instrument has an instrument type assigned (some templates may require this)

#### Autofill Not Working

**Problem**: Fields don't autofill in subsequent groups

**Solution**:
- Ensure "Autofill from previous group" is checked for the field
- Verify that fields in subsequent groups have the same name or label
- Check that you're filling the field in the first group (autofill only works from the first group)

#### PDF Export Fails

**Problem**: "No module named 'reportlab'" error

**Solution**:
- Install the reportlab library: `py -m pip install reportlab` (or `pip install reportlab` if you use pip directly)
- Restart the application

#### Search Not Finding Instruments

**Problem**: Search doesn't return expected results

**Solution**:
- Search is case-insensitive but requires exact substring matches
- Try searching by partial ID, location, or type name
- Clear other filters that might be hiding results

### Getting Help

**Contextual Help**: Every dialog window includes a **?** (question mark) button next to the close button. Click it to view detailed, context-specific help for that window. The help dialog can be opened multiple times and provides information about:
- How to use the current dialog
- Field descriptions and requirements
- Tips and best practices specific to that feature
- Keyboard shortcuts relevant to the dialog

**Additional Resources**:
1. Check the application logs in the `logs/` directory
2. Review error messages carefully
3. Ensure all required Python packages are installed
4. Verify database file integrity

### Data Recovery

If you need to recover data:

1. Check for backup files of `calibration.db`
2. Look in the `attachments/` directory for calibration files
3. Check exported CSV or PDF files for historical data

---

## Appendix

### File Structure

The application creates and uses the following files and directories:

- `calibration.db`: SQLite database containing all data
- `attachments/`: Directory containing attached calibration files
- `Signatures/`: Directory containing signature image files (PNG, JPG, JPEG, GIF, or BMP)
- `backups/`: Directory for automatic daily database backups (created by the app)
- `logs/`: Directory containing application logs
- `calibration_crash.log`: Crash log file

### Data Backup

**Automatic backups**: The application performs a daily database backup on startup. Backups are stored in the `backups/` folder (e.g. `calibration_backup_YYYYMMDD_HHMMSS.db`). Old backups are removed after 30 days.

**Manual backup**:

1. Close the application
2. Copy the `calibration.db` file to a safe location
3. Optionally copy the `attachments/` and `Signatures/` directories

To restore:

1. Close the application
2. Replace `calibration.db` with your backup
3. Restore the `attachments/` directory if needed

### System Requirements

- Python 3.7 or higher
- Required Python packages:
  - PyQt5
  - reportlab (for PDF export)
- Windows, macOS, or Linux operating system

---

## Conclusion

This user guide covers the essential features and workflows of the Calibration Tracker application. For additional assistance or feature requests, please refer to your system administrator or development team.

**Remember**: Regular use of the application and proper data entry will help ensure accurate tracking of your calibration requirements and compliance with quality standards.

---

---

## Recent Updates and Enhancements

### Version Updates

The following features have been added in recent versions:

#### Interface Improvements
- **Column Width Persistence**: Column widths are automatically saved and restored between application sessions
- **Search Highlighting**: Search terms are highlighted in yellow within table cells for easy identification
- **Statistics Dashboard**: Real-time statistics panel showing total, active, overdue, and due-in-30-days instrument counts
- **Dynamic Window Title**: Window title shows total and filtered instrument counts (e.g., "150 instruments (25 shown)")
- **Contextual Help System**: Question mark button on all dialogs provides context-specific help

#### Instrument Management
- **Serial Number Field**: Added serial number field to instrument records
- **Description Field**: Added description field for detailed instrument information

#### Template System
- **Real-time Autofill**: Autofill updates happen in real-time as you type, not just on navigation
- **Improved Visibility**: Template dialogs now properly display all data immediately upon opening
- **Better Refresh**: Template builder window refreshes quickly for better performance

#### PDF Export Enhancements
- **Smart Word Wrapping**: Headers wrap at word boundaries, never breaking words in the middle
- **One-Page Formatting**: In-house (PULL_IN) calibration PDFs automatically format to fit on a single page
- **Attachment Export**: Export all calibrations now includes and organizes attached external files
- **Optimized Layout**: Reduced margins, spacing, and font sizes for in-house templates while maintaining readability
- **Improved Table Wrapping**: Tables automatically adjust to fit page width with proper column sizing
- **Black and White Formatting**: All PDF tables use black and white only for better printing

#### Signature Fields
- **Signature Field Type**: New "signature" field type for template fields
- **Signature Selection**: Dropdown menus in calibration forms to select whose signature appears on documents
- **Signature Images**: Signature images are automatically embedded in PDF exports
- **Signature Management**: Place signature image files in the "Signatures" folder (PNG, JPG, JPEG, GIF, or BMP formats supported)

#### Search and Filter
- **Visual Search Feedback**: Search terms are highlighted in matching table cells
- **Clear Button**: Easy-to-access clear button for search box

#### Themes and Text Size
- **Help → Theme**: Multiple color themes (Fusion, Taylor's Theme, Tess's Theme, Retina Seering, Vice); selection is saved
- **Help → Text Size**: Small, Medium, Large, Extra Large; selection is saved

#### Updates and Backups
- **Help → Check for Updates**: Manual check shows "You're already on the latest version" or offers an update; startup check only prompts when an update is available or when the check fails. Updates deliver the new executable so you get new UI and features.
- **Automatic daily backups**: Database backups are stored in `backups/` and cleaned up after 30 days

#### PDF Export
- **Single and batch PDF export**: Export one calibration or all calibrations to PDF; instrument info, template, and calibration values; AHI logo on in-house exports when `AHI_logo.png` is present

---

*Last Updated: January 2025*
*See the application Help menu or VERSION file for the current release version.*
