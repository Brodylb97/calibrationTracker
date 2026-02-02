# ui/table_models.py - Table models and delegates for the instrument list

from datetime import datetime, date, timedelta

from PyQt5 import QtWidgets, QtCore, QtGui


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
            super().paint(painter, option, index)
            return

        text = str(index.data(QtCore.Qt.DisplayRole) or "")
        if not text:
            super().paint(painter, option, index)
            return

        text_lower = text.lower()
        if self.search_text not in text_lower:
            super().paint(painter, option, index)
            return

        option_copy = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(option_copy, index)

        text_rect = option_copy.rect
        text_rect.adjust(4, 0, -4, 0)

        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            bg_color = index.data(QtCore.Qt.BackgroundRole)
            if bg_color:
                painter.fillRect(option.rect, bg_color)
            else:
                painter.fillRect(option.rect, option.palette.base())

        painter.save()
        painter.setPen(option.palette.text().color())

        search_len = len(self.search_text)
        start_pos = 0
        highlights = []

        while True:
            pos = text_lower.find(self.search_text, start_pos)
            if pos == -1:
                break
            highlights.append((pos, pos + search_len))
            start_pos = pos + 1

        font_metrics = painter.fontMetrics()
        x = text_rect.left()
        y = text_rect.top() + font_metrics.ascent() + (text_rect.height() - font_metrics.height()) // 2

        text_color = index.data(QtCore.Qt.ForegroundRole)
        if not text_color:
            text_color = option.palette.text().color()

        current_pos = 0
        for start, end in highlights:
            if current_pos < start:
                before_text = text[current_pos:start]
                painter.setPen(text_color)
                painter.drawText(x, y, before_text)
                x += font_metrics.width(before_text)

            highlight_text = text[start:end]
            highlight_width = font_metrics.width(highlight_text)
            highlight_rect = QtCore.QRect(
                x,
                text_rect.top() + 1,
                highlight_width,
                text_rect.height() - 2,
            )

            painter.fillRect(highlight_rect, QtGui.QColor("#FFD93D"))
            painter.setPen(QtGui.QColor("#000000"))
            painter.drawText(x, y, highlight_text)
            x += highlight_width

            current_pos = end

        if current_pos < len(text):
            remaining_text = text[current_pos:]
            painter.setPen(text_color)
            painter.drawText(x, y, remaining_text)

        painter.restore()


class InstrumentTableModel(QtCore.QAbstractTableModel):
    """Table model for the instrument list."""

    HEADERS = [
        "ID",
        "Location",
        "Type",
        "Destination",
        "Last Cal",
        "Next Due",
        "Days Left",
        "Status",
        "Instrument type",
    ]

    def _days_left(self, inst):
        nd = inst.get("next_due_date")
        if not nd:
            return None
        try:
            d = datetime.strptime(nd, "%Y-%m-%d").date()
            return (d - date.today()).days
        except Exception:
            return None

    def sort(self, column, order=QtCore.Qt.AscendingOrder):
        reverse = order == QtCore.Qt.DescendingOrder

        def sort_key(inst):
            if column == 0:
                return inst.get("tag_number") or ""
            elif column == 1:
                return inst.get("location") or ""
            elif column == 2:
                return inst.get("calibration_type") or ""
            elif column == 3:
                return inst.get("destination_name") or ""
            elif column == 4:
                return inst.get("last_cal_date") or ""
            elif column == 5:
                return inst.get("next_due_date") or ""
            elif column == 6:
                days = self._days_left(inst)
                return days if days is not None else 999999
            elif column == 7:
                return inst.get("status") or ""
            elif column == 8:
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

        if role == QtCore.Qt.BackgroundRole:
            days_left = self._days_left(inst)
            if days_left is not None:
                if days_left < 0:
                    return QtGui.QColor(80, 30, 30)
                elif days_left <= 7:
                    return QtGui.QColor(80, 70, 30)
                elif days_left <= 30:
                    return QtGui.QColor(60, 50, 40)
            return None

        if role == QtCore.Qt.ForegroundRole:
            days_left = self._days_left(inst)
            if days_left is not None and days_left < 0:
                return QtGui.QColor("#FF6B6B")
            elif days_left is not None and days_left <= 7:
                return QtGui.QColor("#FFD93D")
            return None

        if role == QtCore.Qt.DisplayRole:
            if col == 0:
                return inst["tag_number"]
            elif col == 1:
                return inst.get("location", "")
            elif col == 2:
                return inst.get("calibration_type", "")
            elif col == 3:
                return inst.get("destination_name", "")
            elif col == 4:
                return inst.get("last_cal_date", "")
            elif col == 5:
                return inst.get("next_due_date", "")
            elif col == 6:
                days = self._days_left(inst)
                return days if days is not None else ""
            elif col == 7:
                return inst.get("status", "")
            elif col == 8:
                return inst.get("instrument_type_name", "") or ""
        return None

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
            return self.instruments[row]["id"]
        return None

    def get_instrument_at_row(self, row):
        """Return the full instrument dict for a source row (for proxy filtering)."""
        if 0 <= row < len(self.instruments):
            return self.instruments[row]
        return None


class InstrumentFilterProxyModel(QtCore.QSortFilterProxyModel):
    """Proxy model for filtering and sorting instruments."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text_filter = ""
        self.status_filter = ""
        self.type_filter = ""
        self.due_filter = "All"
        self.recently_modified_days = 0

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

    def set_recently_modified_days(self, days: int):
        self.recently_modified_days = max(0, int(days))
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        if model is None:
            return True

        def data(col):
            idx = model.index(source_row, col, source_parent)
            val = model.data(idx, QtCore.Qt.DisplayRole)
            return "" if val is None else str(val)

        if self.text_filter:
            haystack_parts = [data(0), data(1), data(3), data(8)]
            src = self.sourceModel()
            if hasattr(src, "get_instrument_at_row"):
                inst = src.get_instrument_at_row(source_row)
                if inst and inst.get("serial_number"):
                    haystack_parts.append(str(inst["serial_number"]))
            haystack = " ".join(haystack_parts).lower()
            query = self.text_filter
            if query in haystack:
                pass
            else:
                import difflib
                words = [w for w in query.split() if len(w) > 0]
                if words and all(w in haystack for w in words):
                    pass
                else:
                    ratio = difflib.SequenceMatcher(None, query, haystack).ratio()
                    if ratio < 0.45:
                        return False

        if self.status_filter:
            if data(7) != self.status_filter:
                return False

        if self.type_filter:
            if data(8) != self.type_filter:
                return False

        if self.due_filter != "All":
            try:
                days = int(data(6))
            except Exception:
                days = 999999

            if self.due_filter == "Overdue":
                if days >= 0:
                    return False
            elif self.due_filter == "Due in 30 days":
                if days < 0 or days > 30:
                    return False

        if self.recently_modified_days > 0:
            src = self.sourceModel()
            if hasattr(src, "get_instrument_at_row"):
                inst = src.get_instrument_at_row(source_row)
                if inst and inst.get("updated_at"):
                    try:
                        raw = inst["updated_at"]
                        if len(raw) >= 19:
                            updated = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
                        elif len(raw) >= 10:
                            updated = datetime.strptime(raw[:10], "%Y-%m-%d")
                        else:
                            return False
                        if updated.replace(tzinfo=None) < datetime.now() - timedelta(days=self.recently_modified_days):
                            return False
                    except Exception:
                        return False
                else:
                    return False

        return True
