"""Preview-first Studio desktop UI. All image I/O runs outside the UI thread."""
from __future__ import annotations

import io
import json
import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QAbstractTableModel, QItemSelectionModel, QModelIndex, QRectF, QSettings, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTableView, QVBoxLayout, QWidget,
)

from .core import Photo, SheetSettings, ExportCancelled, collect_paths, inspect_photo, render_page, export_sheets
from .themes import apply_theme
from .widgets import FileProgressBar

DONATE_URL = "https://ko-fi.com/steadystatestudio"


def visible_text(text: str) -> str:
    """Keep filenames as plain single-line labels, including bidi controls."""
    return "".join(ch if ch.isprintable() and ch not in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069" else "�" for ch in text)


class Task(QThread):
    result = Signal(object)
    failed = Signal(object)
    progress = Signal(int, int)

    def __init__(self, work: Callable, parent=None):
        super().__init__(parent)
        self.work = work
        self.cancel = threading.Event()

    def run(self):
        try:
            self.result.emit(self.work(self.cancel, self.progress.emit))
        except Exception as exc:
            self.failed.emit(exc)


class PhotoModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.photos: list[Photo] = []
        self.icons: list[QIcon] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.photos)

    def columnCount(self, parent=QModelIndex()):
        return 3

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return ("#", "Photo", "Pixels")[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.photos):
            return None
        photo = self.photos[index.row()]
        if role == Qt.DisplayRole:
            return (str(index.row() + 1), visible_text(photo.path.name), f"{photo.width} × {photo.height}")[index.column()]
        if role == Qt.DecorationRole and index.column() == 1:
            return self.icons[index.row()]
        if role == Qt.ToolTipRole:
            return visible_text(str(photo.path))
        if role == Qt.AccessibleDescriptionRole:
            return str(photo.path)
        if role == Qt.TextAlignmentRole and index.column() != 1:
            return int(Qt.AlignCenter)
        return None

    def reset(self, photos):
        self.beginResetModel()
        self.photos = list(photos)
        self.icons = []
        for photo in self.photos:
            pixmap = QPixmap()
            pixmap.loadFromData(photo.thumbnail)
            self.icons.append(QIcon(pixmap))
        self.endResetModel()


class PagePreview(QWidget):
    """Fit the page to the available area; the full uncropped page stays visible."""
    def __init__(self):
        super().__init__()
        self.pixmap = QPixmap()
        self.message = "Add photos or a folder\nto build your contact sheet"
        self.setMinimumSize(260, 230)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName("Contact sheet page preview")

    def show_page(self, data):
        self.pixmap.loadFromData(data)
        self.message = ""
        self.update()

    def show_message(self, message):
        self.pixmap = QPixmap()
        self.message = message
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(self.palette().mid().color())
        painter.setBrush(self.palette().base())
        painter.drawRoundedRect(rect, 10, 10)
        inner = self.rect().adjusted(18, 18, -18, -18)
        if self.pixmap.isNull():
            painter.setPen(self.palette().text().color())
            painter.drawText(inner, Qt.AlignCenter | Qt.TextWordWrap, self.message)
            return
        size = self.pixmap.size().scaled(inner.size(), Qt.KeepAspectRatio)
        x = inner.x() + (inner.width() - size.width()) // 2
        y = inner.y() + (inner.height() - size.height()) // 2
        painter.fillRect(x + 3, y + 4, size.width(), size.height(), QColor(0, 0, 0, 45))
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(x, y, size.width(), size.height(), self.pixmap)


class SettingsDialog(QDialog):
    def __init__(self, current, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Contact Sheet Maker · Settings")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.theme = QComboBox()
        self.theme.addItems(["System", "Dark", "Light"])
        self.theme.setCurrentText(current.title())
        form.addRow("Appearance", self.theme)
        layout.addLayout(form)
        note = QLabel("Layout and export choices are saved on this computer.\nPhotos are never uploaded, copied into a library, or altered.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None):
        super().__init__()
        self.settings = settings or QSettings("Steady State Studio", "Contact Sheet Maker")
        self.setWindowTitle("Contact Sheet Maker · Steady State Studio")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "assets/icon.svg")))
        self.setAcceptDrops(True)
        self.busy = False
        self.task: Task | None = None
        self.preview_task: Task | None = None
        self.preview_pending = False
        self.preview_ready = False
        self.status_locked = False
        self.preview_revision = 0
        self.page_index = 0
        self.closing = False
        self.last_outputs = []
        self._restoring = True
        apply_theme(QApplication.instance(), self.settings.value("theme", "system", type=str))
        self._build_ui()
        self._restore_settings()
        self._restoring = False
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(180)
        self.debounce.timeout.connect(self._launch_preview)
        self._connect_controls()
        self._refresh()
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._system_theme_changed)

    def _button(self, text, callback, tooltip=""):
        button = QPushButton(text)
        button.clicked.connect(callback)
        button.setToolTip(tooltip)
        return button

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        toolbar = QHBoxLayout()
        self.add_files = self._button("Add Photos", self._browse_files, "Choose JPEG or PNG photos · Ctrl+O")
        self.add_folder = self._button("Add Folder", self._browse_folder, "Add JPEG and PNG files in one folder; no subfolders")
        self.clear_button = self._button("Clear", self.clear_photos, "Remove photos from this list; originals stay untouched")
        for widget in (self.add_files, self.add_folder, self.clear_button):
            toolbar.addWidget(widget)
        toolbar.addStretch()
        self.help_button = self._button("Help", self._help)
        self.donate_button = self._button("Donate", self._open_donate, "Optional support on Ko-fi; every feature is free")
        self.settings_button = self._button("Settings", self._settings_dialog)
        for widget in (self.help_button, self.donate_button, self.settings_button):
            toolbar.addWidget(widget)
        layout.addLayout(toolbar)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(12)
        files = QWidget()
        file_layout = QVBoxLayout(files)
        file_layout.setContentsMargins(0, 0, 0, 0)
        actions = QHBoxLayout()
        self.count_label = QLabel("0 photos")
        self.count_label.setObjectName("muted")
        actions.addWidget(self.count_label)
        actions.addStretch()
        self.up_button = self._button("↑", lambda: self.move_selected(-1), "Move selected photos up · Alt+Up")
        self.up_button.setAccessibleName("Move selected photos up")
        self.down_button = self._button("↓", lambda: self.move_selected(1), "Move selected photos down · Alt+Down")
        self.down_button.setAccessibleName("Move selected photos down")
        self.remove_button = self._button("Remove", self.remove_selected, "Remove selected photos · Delete")
        for button in (self.up_button, self.down_button, self.remove_button):
            actions.addWidget(button)
        file_layout.addLayout(actions)
        self.model = PhotoModel(self)
        self.table = QTableView()
        self.table.setObjectName("fileTable")
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setIconSize(QSize(48, 44))
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(60)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setColumnWidth(0, 34)
        self.table.setColumnWidth(2, 108)
        self.table.setMinimumWidth(335)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        file_layout.addWidget(self.table, 1)
        order_note = QLabel("Sheet order follows this list. Select rows to move or remove.")
        order_note.setObjectName("muted")
        order_note.setWordWrap(True)
        file_layout.addWidget(order_note)
        self.splitter.addWidget(files)
        preview_area = QWidget()
        preview_layout = QVBoxLayout(preview_area)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_header = QHBoxLayout()
        preview_heading = QLabel("Sheet preview")
        preview_heading.setObjectName("sectionHeading")
        preview_header.addWidget(preview_heading)
        preview_header.addStretch()
        self.zoom_button = self._button("Zoom", self._zoom_preview, "View this page at full preview resolution")
        preview_header.addWidget(self.zoom_button)
        self.previous_button = self._button("‹", lambda: self.change_page(-1), "Previous sheet")
        self.previous_button.setAccessibleName("Previous sheet")
        self.page_label = QLabel("Page 0 of 0")
        self.page_label.setMinimumWidth(110)
        self.page_label.setAlignment(Qt.AlignCenter)
        self.next_button = self._button("›", lambda: self.change_page(1), "Next sheet")
        self.next_button.setAccessibleName("Next sheet")
        preview_header.addWidget(self.previous_button)
        preview_header.addWidget(self.page_label)
        preview_header.addWidget(self.next_button)
        preview_layout.addLayout(preview_header)
        self.preview = PagePreview()
        preview_layout.addWidget(self.preview, 1)
        self.preview_note = QLabel("90 dpi preview · Export uses the selected resolution. Photos fit without cropping.")
        self.preview_note.setObjectName("muted")
        self.preview_note.setWordWrap(True)
        preview_layout.addWidget(self.preview_note)
        self.splitter.addWidget(preview_area)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([430, 610])
        layout.addWidget(self.splitter, 1)

        self.controls = QFrame()
        self.controls.setObjectName("panel")
        grid = QGridLayout(self.controls)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.preset = QComboBox()
        self.preset.addItems(["Standard · 12 photos", "Compact · 20 photos", "Large · 6 photos", "Custom"])
        self.page_size = QComboBox()
        self.page_size.addItems(["A4", "Letter"])
        self.orientation = QComboBox()
        self.orientation.addItems(["Portrait", "Landscape"])
        self.rows = QSpinBox(); self.rows.setRange(1, 12); self.rows.setValue(4)
        self.columns = QSpinBox(); self.columns.setRange(1, 12); self.columns.setValue(3)
        self.margin = QDoubleSpinBox(); self.margin.setRange(0, 50); self.margin.setValue(10); self.margin.setSuffix(" mm"); self.margin.setDecimals(1)
        self.gap = QDoubleSpinBox(); self.gap.setRange(0, 30); self.gap.setValue(4); self.gap.setSuffix(" mm"); self.gap.setDecimals(1)
        self.captions = QCheckBox("Filename captions"); self.captions.setChecked(True)
        self.title_input = QLineEdit(); self.title_input.setPlaceholderText("Optional sheet title"); self.title_input.setMaxLength(200)
        self.title_input.setAccessibleName("Sheet title")
        def field(label, widget, row, column):
            lab = QLabel(label); lab.setObjectName("muted"); lab.setBuddy(widget)
            grid.addWidget(lab, row, column)
            grid.addWidget(widget, row, column + 1)
        field("Preset", self.preset, 0, 0)
        field("Page", self.page_size, 0, 2)
        field("Orientation", self.orientation, 0, 4)
        field("Rows", self.rows, 1, 0)
        field("Columns", self.columns, 1, 2)
        field("Margin", self.margin, 1, 4)
        field("Gap", self.gap, 2, 0)
        grid.addWidget(self.captions, 2, 2, 1, 2)
        field("Title", self.title_input, 2, 4)
        grid.setColumnStretch(1, 2); grid.setColumnStretch(3, 1); grid.setColumnStretch(5, 2)
        layout.addWidget(self.controls)

        self.output_controls = QWidget()
        out = QGridLayout(self.output_controls)
        out.setContentsMargins(0, 0, 0, 0)
        self.format_combo = QComboBox(); self.format_combo.addItems(["PDF", "JPEG"]); self.format_combo.setAccessibleName("Export format")
        self.dpi_combo = QComboBox(); self.dpi_combo.addItems(["150 dpi", "200 dpi", "300 dpi"]); self.dpi_combo.setCurrentIndex(1); self.dpi_combo.setAccessibleName("Export resolution")
        self.stem_input = QLineEdit("contact-sheet"); self.stem_input.setAccessibleName("Output filename stem"); self.stem_input.setPlaceholderText("Output filename")
        output_left = QWidget(); output_left_row = QHBoxLayout(output_left); output_left_row.setContentsMargins(0, 0, 0, 0)
        format_label = QLabel("Format"); format_label.setObjectName("muted"); format_label.setBuddy(self.format_combo)
        dpi_label = QLabel("DPI"); dpi_label.setObjectName("muted"); dpi_label.setBuddy(self.dpi_combo)
        self.format_combo.setToolTip("PDF: one multipage document. JPEG: one numbered image per page.")
        self.dpi_combo.setToolTip("Print resolution. 200 dpi balances sharpness and file size; 300 dpi gives finer detail.")
        output_left_row.addWidget(format_label); output_left_row.addWidget(self.format_combo); output_left_row.addWidget(dpi_label); output_left_row.addWidget(self.dpi_combo); output_left_row.addStretch()
        out.addWidget(output_left, 0, 0)
        output_right = QWidget(); output_right_row = QHBoxLayout(output_right); output_right_row.setContentsMargins(0, 0, 0, 0)
        name_label = QLabel("Filename"); name_label.setObjectName("muted"); name_label.setBuddy(self.stem_input)
        output_right_row.addWidget(name_label); output_right_row.addWidget(self.stem_input)
        out.addWidget(output_right, 0, 2)
        out.setColumnStretch(0, 1); out.setColumnStretch(2, 1)
        self.export_button = self._button("Export Sheets…", self._choose_export, "Choose a destination and export every page")
        self.export_button.setObjectName("primary")
        self.export_button.setMinimumWidth(190)
        out.addWidget(self.export_button, 0, 1, Qt.AlignCenter)
        layout.addWidget(self.output_controls)
        status_row = QHBoxLayout()
        self.status = FileProgressBar()
        self.status.setAccessibleName("Contact sheet status and progress")
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.status.setMinimumHeight(42)
        self.status.preview(0, "Add photos to get started.")
        self.progress = self.status
        self.cancel_button = self._button("Cancel", self.cancel_operation)
        self.cancel_button.hide()
        self.open_folder_button = self._button("Open Folder", self._open_output_folder)
        self.open_folder_button.hide()
        status_row.addWidget(self.status, 1)
        status_row.addWidget(self.cancel_button); status_row.addWidget(self.open_folder_button)
        layout.addLayout(status_row)
        self.setMinimumSize(890, 700)
        self.resize(1120, 860)
        self.shortcuts = []
        for key, callback, target in [("Ctrl+O", self._browse_files, self), ("Delete", self.remove_selected, self.table), ("Alt+Up", lambda: self.move_selected(-1), self.table), ("Alt+Down", lambda: self.move_selected(1), self.table)]:
            shortcut = QShortcut(QKeySequence(key), target)
            if target is self.table:
                shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)

    def sheet_settings(self):
        return SheetSettings(page_size=self.page_size.currentText(), orientation=self.orientation.currentText(), rows=self.rows.value(), columns=self.columns.value(), margin_mm=self.margin.value(), gap_mm=self.gap.value(), captions=self.captions.isChecked(), title=self.title_input.text(), dpi=int(self.dpi_combo.currentText().split()[0]))

    def _connect_controls(self):
        self.preset.activated.connect(self._apply_preset)
        for widget in (self.page_size, self.orientation, self.dpi_combo):
            widget.currentIndexChanged.connect(self._options_changed)
        for widget in (self.rows, self.columns, self.margin, self.gap):
            widget.valueChanged.connect(self._options_changed)
        self.captions.toggled.connect(self._options_changed)
        self.title_input.textChanged.connect(self._options_changed)
        self.format_combo.currentIndexChanged.connect(self._save_settings)
        self.stem_input.editingFinished.connect(self._save_settings)

    def _restore_settings(self):
        try:
            saved = json.loads(self.settings.value("layout", "{}", type=str))
            if not isinstance(saved, dict):
                return
            for key, widget in (("page_size", self.page_size), ("orientation", self.orientation)):
                widget.setCurrentText(str(saved.get(key, widget.currentText())))
            for key, widget in (("rows", self.rows), ("columns", self.columns), ("margin_mm", self.margin), ("gap_mm", self.gap)):
                widget.setValue(saved.get(key, widget.value()))
            self.captions.setChecked(bool(saved.get("captions", True)))
            self.title_input.setText(str(saved.get("title", "")))
            self.dpi_combo.setCurrentText(f"{saved.get('dpi', 200)} dpi")
            self.format_combo.setCurrentText(self.settings.value("format", "PDF", type=str))
            self.stem_input.setText(self.settings.value("stem", "contact-sheet", type=str))
            self.preset.setCurrentIndex(3 if saved else 0)
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
                if not any(screen.availableGeometry().intersects(self.frameGeometry()) for screen in QApplication.screens()):
                    self.move(self.screen().availableGeometry().topLeft())
            splitter = self.settings.value("splitter")
            if splitter:
                self.splitter.restoreState(splitter)
        except (ValueError, TypeError, OverflowError):
            pass  # Invalid saved preferences cannot prevent startup.

    def _save_settings(self, *_):
        if self._restoring:
            return
        self.settings.setValue("layout", json.dumps(asdict(self.sheet_settings())))
        self.settings.setValue("format", self.format_combo.currentText())
        self.settings.setValue("stem", self.stem_input.text())

    def _options_changed(self, *_):
        if self._restoring:
            return
        self.preset.setCurrentIndex(3)
        self._save_settings()
        self._schedule_preview()

    def _apply_preset(self, index):
        if index == 3:
            return
        self._restoring = True
        self.preset.setCurrentIndex(index)
        page, rows, columns = [("A4", 4, 3), ("Letter", 5, 4), ("A4", 3, 2)][index]
        self.page_size.setCurrentText(page); self.orientation.setCurrentText("Portrait")
        self.rows.setValue(rows); self.columns.setValue(columns)
        self.margin.setValue(10); self.gap.setValue(4); self.captions.setChecked(True)
        self._restoring = False
        self._save_settings(); self._schedule_preview()

    def _set_status(self, text):
        self.status.set_message(text)

    def _refresh(self):
        count = len(self.model.photos)
        self.count_label.setText(f"{count} photo{'s' if count != 1 else ''}")
        valid = True
        try:
            settings = self.sheet_settings(); settings.validate()
            pages = settings.page_count(count)
        except ValueError as exc:
            valid = False; pages = 0
            self._set_status(str(exc))
        self.page_index = max(0, min(self.page_index, max(0, pages - 1)))
        self.page_label.setText(f"Page {self.page_index + 1 if pages else 0} of {pages}")
        self.previous_button.setEnabled(pages > 0 and self.page_index > 0)
        self.next_button.setEnabled(pages > 0 and self.page_index < pages - 1)
        self.clear_button.setEnabled(bool(count) and not self.busy)
        self.export_button.setEnabled(bool(count) and valid and self.preview_ready and not self.busy)
        reason = "Choose a destination and export every page" if self.export_button.isEnabled() else "Wait for the current operation" if self.busy else "Add photos first" if not count else "Fix the layout to export" if not valid else "Wait for the current preview to finish"
        self.export_button.setToolTip(reason)
        self.zoom_button.setEnabled(self.preview_ready and not self.preview.pixmap.isNull())
        self._selection_changed()
        return valid

    def _selection_changed(self, *_):
        rows = self.selected_rows()
        self.remove_button.setEnabled(bool(rows) and not self.busy)
        self.up_button.setEnabled(bool(rows) and min(rows, default=0) > 0 and not self.busy)
        self.down_button.setEnabled(bool(rows) and max(rows, default=0) < len(self.model.photos) - 1 and not self.busy)

    def selected_rows(self):
        return sorted(index.row() for index in self.table.selectionModel().selectedRows())

    def _select_rows(self, rows, current_row):
        """Keep the keyboard anchor with the selection after a model reset."""
        selection = self.table.selectionModel()
        for row in rows:
            selection.select(self.model.index(row, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        current = self.model.index(current_row, 0)
        selection.setCurrentIndex(current, QItemSelectionModel.NoUpdate)
        self.table.scrollTo(current)
        self.table.setFocus(Qt.OtherFocusReason)

    def move_selected(self, direction):
        if self.busy:
            return
        rows = self.selected_rows()
        if not rows or (direction < 0 and rows[0] == 0) or (direction > 0 and rows[-1] == len(self.model.photos) - 1):
            return
        photos = self.model.photos.copy()
        current_row = self.table.currentIndex().row()
        if current_row not in rows:
            current_row = rows[0]
        for row in rows if direction < 0 else reversed(rows):
            photos[row], photos[row + direction] = photos[row + direction], photos[row]
        self.model.reset(photos)
        self._select_rows([row + direction for row in rows], current_row + direction)
        self._schedule_preview()

    def remove_selected(self):
        if self.busy:
            return
        selected = set(self.selected_rows())
        if selected:
            self.model.reset([photo for i, photo in enumerate(self.model.photos) if i not in selected])
            if self.model.photos:
                next_row = min(min(selected), len(self.model.photos) - 1)
                self._select_rows([next_row], next_row)
            else:
                self.table.setFocus(Qt.OtherFocusReason)
            self._schedule_preview()

    def clear_photos(self):
        if not self.busy:
            self.model.reset([]); self.page_index = 0
            self._schedule_preview()

    def _browse_files(self):
        if self.busy:
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Add Photos", self.settings.value("input_folder", "", type=str), "Photos (*.jpg *.jpeg *.png *.JPG *.JPEG *.PNG)")
        if files:
            self.settings.setValue("input_folder", str(Path(files[0]).parent))
            self.add_paths([Path(path) for path in files])

    def _browse_folder(self):
        if self.busy:
            return
        folder = QFileDialog.getExistingDirectory(self, "Add Folder", self.settings.value("input_folder", "", type=str))
        if folder:
            self.settings.setValue("input_folder", folder)
            self.add_paths([Path(folder)])

    def add_paths(self, paths):
        if self.busy or self.closing:
            return
        existing = {os.path.normcase(str(photo.path.resolve())) for photo in self.model.photos}
        def work(cancel, progress):
            candidates = collect_paths(paths, cancel=cancel)
            photos, errors = [], []
            duplicates = 0
            for index, path in enumerate(candidates):
                if cancel.is_set():
                    raise ExportCancelled("Import cancelled")
                if os.path.normcase(str(path.resolve())) not in existing:
                    try:
                        photos.append(inspect_photo(path, cancel=cancel))
                    except Exception as exc:
                        errors.append(f"{visible_text(path.name)}: {exc}")
                else:
                    duplicates += 1
                progress(index + 1, len(candidates))
            if cancel.is_set():
                raise ExportCancelled("Import cancelled")
            return photos, errors, duplicates
        self._start_operation(work, self._import_done, "Adding photos…",
                              cancel_message="Import cancelled. The photo list is unchanged.")

    def _import_done(self, result):
        photos, errors, duplicates = result
        if photos:
            self.model.reset(self.model.photos + photos)
            self._schedule_preview()
        parts = [f"Added {len(photos)} photo{'s' if len(photos) != 1 else ''}." if photos else "No photos added."]
        if duplicates:
            parts.append(f"{duplicates} already in the list.")
        if errors:
            parts.append(f"{len(errors)} could not be loaded.")
        if not photos and not errors and not duplicates:
            parts.append("No JPEG or PNG photos found in this selection.")
        # The automatic preview must not replace the import result.
        self.status_locked = True
        self.status.preview(len(self.model.photos), " ".join(parts))
        if errors and not self.closing:
            title = "Some photos could not be added" if photos else "Photos could not be added"
            box = QMessageBox(QMessageBox.Warning, title,
                              " ".join(parts) + "\n\nChoose Show Details to see which files failed and why.", parent=self)
            box.setTextFormat(Qt.PlainText)
            box.setDetailedText("\n".join(errors[:100]))
            if len(errors) > 100:
                box.setInformativeText("Details show the first 100 files that could not be loaded.")
            box.exec()

    def _schedule_preview(self):
        self.preview_ready = False
        self.status_locked = False
        self.preview_revision += 1
        self.preview_pending = True
        if self.preview_task:
            self.preview_task.cancel.set()
        valid = self._refresh()
        self.preview.show_message("Updating preview…" if self.model.photos and valid else "Add photos or a folder\nto build your contact sheet" if not self.model.photos else "This layout does not fit.\nReduce rows, columns, margins or gaps.")
        if self.model.photos and valid:
            self.debounce.start()
        else:
            self.preview_pending = False
            if not self.busy and not self.model.photos:
                self._set_status("Add photos to get started.")

    def _launch_preview(self):
        if self.preview_task or not self.preview_pending or self.closing or self.busy:
            return
        self.preview_pending = False
        revision = self.preview_revision
        photos = list(self.model.photos); settings = self.sheet_settings(); page_index = self.page_index
        def work(cancel, progress):
            page = render_page(photos, settings, page_index, dpi=90, cancel=cancel)
            output = io.BytesIO(); page.save(output, format="PNG"); page.close()
            return output.getvalue()
        task = Task(work, self)
        self.preview_task = task
        task.result.connect(lambda data: self._preview_done(revision, data))
        task.failed.connect(lambda exc: self._preview_failed(revision, exc))
        task.finished.connect(self._preview_finished)
        task.start()

    def _zoom_preview(self):
        if self.preview.pixmap.isNull() or not self.preview_ready:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Sheet preview · Page {self.page_index + 1} · 100%")
        layout = QVBoxLayout(dialog)
        note = QLabel("Full preview resolution. Scroll to inspect filenames and layout.")
        note.setObjectName("muted"); layout.addWidget(note)
        scroll = QScrollArea(); label = QLabel(); label.setPixmap(self.preview.pixmap)
        label.setAlignment(Qt.AlignCenter); scroll.setWidget(label); scroll.setAlignment(Qt.AlignCenter)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        area = self.screen().availableGeometry()
        dialog.resize(min(900, area.width() - 60), min(900, area.height() - 60))
        dialog.exec()

    def _preview_done(self, revision, data):
        if revision == self.preview_revision and not self.closing:
            self.preview.show_page(data)
            self.preview_ready = True
            self._refresh()
            if not self.busy and not self.status_locked:
                settings = self.sheet_settings()
                self.status.preview(len(self.model.photos), f"{len(self.model.photos)} photos · {settings.page_count(len(self.model.photos))} pages · Originals stay untouched")

    def _preview_failed(self, revision, exc):
        if revision == self.preview_revision and not isinstance(exc, ExportCancelled) and not self.closing:
            self.preview.show_message("Preview unavailable.\nCheck the source photos.")
            self.preview_ready = False
            self._refresh()
            self._set_status(str(exc))

    def _preview_finished(self):
        task = self.preview_task; self.preview_task = None
        if task:
            task.deleteLater()
        if self.closing:
            self._finish_close()
        elif self.preview_pending:
            self.debounce.start(0)

    def change_page(self, delta):
        if self.busy:
            return
        self.page_index += delta
        self._schedule_preview()

    def _start_operation(self, work, on_result, message, *, cancel_message="Cancelled. No new sheets were saved."):
        if self.busy:
            return
        self.busy = True
        self.operation_cancel_message = cancel_message
        self.status_locked = True
        if self.preview_task:
            self.preview_revision += 1
            self.preview_task.cancel.set()
            self.preview_pending = bool(self.model.photos)
        self.open_folder_button.hide()
        self._set_status(message)
        self.controls.setEnabled(False); self.output_controls.setEnabled(False)
        self.add_files.setEnabled(False); self.add_folder.setEnabled(False); self.settings_button.setEnabled(False)
        self.progress.file_count = max(1, len(self.model.photos))
        self.progress.setRange(0, 0); self.progress.setValue(0)
        self.cancel_button.setEnabled(True); self.cancel_button.show()
        self._refresh()
        self.previous_button.setEnabled(False); self.next_button.setEnabled(False)
        task = Task(work, self); self.task = task
        task.result.connect(on_result)
        task.failed.connect(self._operation_failed)
        task.progress.connect(self._operation_progress)
        task.finished.connect(self._operation_finished)
        task.start()

    def _operation_progress(self, done, total):
        if self.task and self.task.cancel.is_set():
            return  # Queued progress must not replace "Cancelling safely…".
        self.progress.file_count = max(1, total)
        self.progress.setRange(0, max(1, total)); self.progress.setValue(done)
        self.progress.setFormat(f"{done} / {total} · Processing…")

    def _operation_failed(self, exc):
        if isinstance(exc, ExportCancelled):
            self.status.preview(0, self.operation_cancel_message)
            return
        self.status.preview(0, str(exc))
        if not self.closing:
            QMessageBox.warning(self, "Operation could not finish", str(exc))

    def _operation_finished(self):
        task = self.task; self.task = None
        if task:
            task.deleteLater()
        self.busy = False
        self.controls.setEnabled(True); self.output_controls.setEnabled(True)
        self.add_files.setEnabled(True); self.add_folder.setEnabled(True); self.settings_button.setEnabled(True)
        self.cancel_button.hide()
        self.open_folder_button.setVisible(bool(self.last_outputs))
        self._refresh()
        if self.closing:
            self._finish_close()
        elif self.preview_pending:
            self.debounce.start(0)

    def cancel_operation(self):
        if self.task:
            self.task.cancel.set()
            self.cancel_button.setEnabled(False)
            self._set_status("Cancelling safely…")

    def _choose_export(self):
        if self.busy or not self.model.photos:
            return
        folder = QFileDialog.getExistingDirectory(self, "Export Contact Sheets", self.settings.value("output_folder", "", type=str))
        if not folder:
            return
        self.settings.setValue("output_folder", folder)
        destination = Path(folder)
        settings = self.sheet_settings()
        stem = self.stem_input.text().strip()
        fmt = self.format_combo.currentText()
        from .core import output_paths
        try:
            paths = output_paths(len(self.model.photos), settings, destination, stem, fmt)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Choose a valid output name", str(exc)); return
        conflicts = [path for path in paths if path.exists() or path.is_symlink()]
        overwrite = False
        if conflicts:
            box = QMessageBox(QMessageBox.Warning, "Replace existing sheets?", f"{len(conflicts)} output files already exist in this folder. Replace them?\n\nChoose No to change the filename or folder. Original photos can never be replaced.", QMessageBox.Yes | QMessageBox.No, self)
            box.setDefaultButton(QMessageBox.No)
            box.setDetailedText("\n".join(str(path) for path in conflicts))
            overwrite = box.exec() == QMessageBox.Yes
            if not overwrite:
                return
        self.start_export(destination, stem, fmt, overwrite)

    def start_export(self, destination, stem, fmt, overwrite=False):
        if self.busy or not self.model.photos:
            return
        photos = list(self.model.photos); settings = self.sheet_settings()
        self._save_settings()
        def work(cancel, progress):
            return export_sheets(photos, settings, Path(destination), stem=stem, format=fmt, overwrite=overwrite, cancel=cancel, progress=progress)
        self._start_operation(work, self._export_done, "Exporting sheets…")

    def _export_done(self, paths):
        self.last_outputs = paths
        self._set_status(f"Saved {len(paths)} file{'s' if len(paths) != 1 else ''} to {paths[0].parent}")
        self.open_folder_button.setToolTip(f"Open the last exported folder: {paths[0].parent}")
        self.open_folder_button.show()

    def _open_output_folder(self):
        if self.last_outputs:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_outputs[0].parent)))

    def _open_donate(self):
        if not QDesktopServices.openUrl(QUrl(DONATE_URL)):
            QMessageBox.information(self, "Support Steady State Studio", f"You can support development at:\n{DONATE_URL}\n\nEvery feature is free.")

    def _settings_dialog(self):
        dialog = SettingsDialog(self.settings.value("theme", "system", type=str), self)
        if dialog.exec() == QDialog.Accepted:
            preference = dialog.theme.currentText().lower()
            self.settings.setValue("theme", preference)
            apply_theme(QApplication.instance(), preference)
            self.preview.update()

    def _system_theme_changed(self, *_):
        if self.settings.value("theme", "system", type=str) == "system":
            apply_theme(QApplication.instance(), "system")
            self.preview.update()

    def _help(self):
        text = ("1. Add JPEG/PNG photos, add a folder, or drop files here. Folder import includes only that folder.\n\n"
                "2. Select rows and use ↑ / ↓ to set the sheet order. Remove and Clear only change this list.\n\n"
                "3. Choose a preset or adjust page size, orientation, grid, margins and gaps. The preview shows one full sheet; use ‹ / › to review every page.\n\n"
                "4. Choose PDF or JPEG, resolution and a filename, then Export Sheets. JPEG creates numbered page files. Existing outputs require an explicit replacement choice.\n\n"
                "Original photos are never modified. Everything runs on this computer, with no uploads or telemetry. Every feature is free; Donate opens the optional Studio Ko-fi page.\n\n"
                "Contact Sheet Maker 0.1.0 · Steady State Studio")
        box = QMessageBox(QMessageBox.Information, "Contact Sheet Maker · Help", text, parent=self)
        box.setTextFormat(Qt.PlainText); box.exec()

    def dragEnterEvent(self, event):
        if not self.busy and event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.busy:
            self.add_paths([Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.task or self.preview_task:
            if self.task and not self.closing:
                answer = QMessageBox.question(self, "Cancel and close?", "An operation is still running. Cancel it safely and close?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if answer != QMessageBox.Yes:
                    event.ignore(); return
            self.closing = True
            self.debounce.stop()
            if not self.task and not self.preview_task:
                QTimer.singleShot(0, self._finish_close)
            if self.task:
                self.task.cancel.set()
            if self.preview_task:
                self.preview_task.cancel.set()
            event.ignore(); return
        self._save_settings()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.saveState())
        self.settings.sync()
        event.accept()

    def _finish_close(self):
        if not self.task and not self.preview_task:
            self.close()
