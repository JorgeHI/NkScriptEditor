# -----------------------------------------------------------------------------
# Nk Script Editor for Nuke
# Copyright (c) 2025 Jorge Hernandez Ibañez
#
# This file is part of the Nk Script Editor project.
# Repository: https://github.com/JorgeHI/NkScriptEditor
#
# This software is licensed under the MIT License.
# See the LICENSE file in the root of this repository for details.
# -----------------------------------------------------------------------------
import os
import sys
import tempfile
import json

import nuke
from NkScriptEditor import nkseHighlighter
from NkScriptEditor import nkCodeEditor
from NkScriptEditor import nkPreferences
from NkScriptEditor import nkConstants
from NkScriptEditor import nkUtils
# Create logger
logger = nkUtils.getLogger(__name__)

if nuke.NUKE_VERSION_MAJOR < 11:
    # PySide for Nuke up to 10
    from PySide import QtWidgets, QtGui, QtCore
elif nuke.NUKE_VERSION_MAJOR < 16:
    # PySide2 for default Nuke 11
    from PySide2 import QtWidgets, QtGui, QtCore
else:
    # PySide6 for Nuke 16+
    from PySide6 import QtWidgets, QtGui, QtCore


class NkScriptEditor(QtWidgets.QWidget):
    def __init__(self):
        super(NkScriptEditor, self).__init__()

        self.setWindowTitle("Nk Script Editor")

        # Create the main tab widget that will hold Editor and Preferences tabs
        self.tabs = QtWidgets.QTabWidget(self)

        # ----------------------
        # 1) Editor Tab
        # ----------------------
        self.editor_page = QtWidgets.QWidget()
        editor_layout = QtWidgets.QVBoxLayout(self.editor_page)

        # -- Load Nodegraph / Load Root buttons
        buttons_layout = QtWidgets.QHBoxLayout()
        self.load_nodegraph_button = QtWidgets.QPushButton("Load nodegraph")
        self.load_nodegraph_button.setToolTip(
            "Loads the current nodegraph without saving the current script."
        )
        self.load_nodegraph_button.clicked.connect(self.load_nodegraph_into_editor)

        self.load_root_button = QtWidgets.QPushButton("Load Root filepath")
        self.load_root_button.setToolTip("Loads the current root open filepath.")
        self.load_root_button.clicked.connect(self.load_root_into_editor)

        buttons_layout.addWidget(self.load_nodegraph_button)
        buttons_layout.addWidget(self.load_root_button)
        editor_layout.addLayout(buttons_layout)

        # -- File selector
        file_selector_layout = QtWidgets.QHBoxLayout()
        self.file_path_lineedit = QtWidgets.QLineEdit()
        self.file_path_lineedit.setPlaceholderText("Select a file .nk...")
        self.browse_button = QtWidgets.QToolButton()
        self.browse_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirOpenIcon))
        self.browse_button.clicked.connect(self.browse_file)
        self.load_nk_button = QtWidgets.QPushButton("Load nk file")
        self.load_nk_button.clicked.connect(self.load_nk_file_into_editor)

        file_selector_layout.addWidget(self.file_path_lineedit)
        file_selector_layout.addWidget(self.browse_button)
        file_selector_layout.addWidget(self.load_nk_button)
        editor_layout.addLayout(file_selector_layout)

        # -- Search bar (hidden by default)
        self.search_layout = QtWidgets.QHBoxLayout()
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search text...")
        self.search_filter_combo = QtWidgets.QComboBox()
        self.search_filter_combo.setFixedWidth(120)
        self.search_filter_combo.addItems(
            ["All", "Node Name", "Node Type", "Knob", "User Knob"]
        )
        self.search_filter_combo.setToolTip("Filter type for search")
        self.search_prev_button = QtWidgets.QPushButton("<")
        self.search_next_button = QtWidgets.QPushButton(">")
        self.search_close_button = QtWidgets.QPushButton("x")
        self.invalid_char_button = QtWidgets.QPushButton("⚠")

        for btn in (self.search_prev_button, self.search_next_button, self.search_close_button, self.invalid_char_button):
            btn.setFixedWidth(30)
        self.search_prev_button.clicked.connect(self.find_previous)
        self.search_next_button.clicked.connect(self.find_next)
        self.search_close_button.clicked.connect(lambda: self.search_layout_widget.setVisible(False))
        self.search_input.returnPressed.connect(self.find_next)
        self.invalid_char_button.setToolTip("Find next invalid character")
        self.invalid_char_button.clicked.connect(self.find_next_invalid_char)

        self.search_layout.addWidget(self.search_input)
        self.search_layout.addWidget(self.search_filter_combo)
        self.search_layout.addWidget(self.search_prev_button)
        self.search_layout.addWidget(self.search_next_button)
        self.search_layout.addWidget(self.invalid_char_button)
        self.search_layout.addWidget(self.search_close_button)

        self.search_layout_widget = QtWidgets.QWidget()
        self.search_layout_widget.setLayout(self.search_layout)
        self.search_layout_widget.setVisible(False)
        editor_layout.addWidget(self.search_layout_widget)

        # -- Script editor widget and syntax highlighter
        self.text_edit = nkCodeEditor.CodeEditor()
        editor_layout.addWidget(self.text_edit)
        self.highlighter = nkseHighlighter.NkHighlighter(self.text_edit.document())

        # -- Debug controls
        self.debug_layout = QtWidgets.QHBoxLayout()
        self.debug_label = QtWidgets.QLabel("Debugging:")
        self.debug_prev_button = QtWidgets.QPushButton("<")
        self.debug_prev_button.setToolTip("Go to previous breakpoint.")
        self.debug_next_button = QtWidgets.QPushButton(">")
        self.debug_next_button.setToolTip("Go to next breakpoint.")
        self.debug_clear_button = QtWidgets.QPushButton("Clean Points")
        self.debug_clear_button.setToolTip("Remove all breakpoints")
        self.debug_paste_button = QtWidgets.QPushButton("Debug")
        self.debug_paste_button.setToolTip(
            "Paste script until the current active debug point."
        )
        self.override_checkbox = QtWidgets.QCheckBox("Override")
        self.override_checkbox.setChecked(True)
        self.override_checkbox.setToolTip(
            "Override the current node graph when pasting to avoid duplication."
        )

        for w in (
            self.debug_label,
            self.debug_prev_button,
            self.debug_next_button,
            self.debug_clear_button,
            self.override_checkbox,
            self.debug_paste_button,
        ):
            self.debug_layout.addWidget(w)
        self.debug_layout.addStretch()
        editor_layout.addLayout(self.debug_layout)

        # -- Paste / Save controls
        self.save_layout = QtWidgets.QHBoxLayout()
        self.paste_button = QtWidgets.QPushButton("Paste Script")
        self.paste_button.clicked.connect(self.paste_script)
        self.saveas_button = QtWidgets.QPushButton("Save Script")
        self.saveas_button.clicked.connect(self.save_script)
        self.save_layout.addWidget(self.paste_button)
        self.save_layout.addWidget(self.saveas_button)
        editor_layout.addLayout(self.save_layout)

        # Add the Editor page to the tabs
        self.tabs.addTab(self.editor_page, "Editor")

        # ----------------------
        # 2) Preferences Tab
        # ----------------------
        self.prefs_page = nkPreferences.PreferenceTabWidget()
        self.tabs.addTab(self.prefs_page, "Preferences")

        # Show Editor tab by default
        self.tabs.setCurrentIndex(0)

        # ----------------------
        # Final assembly
        # ----------------------
        # Set the tab widget as the sole child of this widget
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(self.tabs)

        # ----------------------
        # Shortcuts & Signals
        # ----------------------
        # Ctrl+F to open search, only when this panel is active
        if hasattr(QtWidgets, 'QShortcut'):
            ShortcutClass = QtWidgets.QShortcut
        else:
            ShortcutClass = QtGui.QShortcut
        search_shortcut = ShortcutClass(QtGui.QKeySequence("Ctrl+F"), self)
        search_shortcut.setContext(QtCore.Qt.ApplicationShortcut)
        search_shortcut.activated.connect(self.on_ctrl_f_pressed)

        # Preference signals
        self.prefs_page.wrapTextToggled.connect(self.toggle_wrap_text)
        # Debug button connections
        self.debug_clear_button.clicked.connect(self.text_edit.clean_all_debug_points)
        self.debug_prev_button.clicked.connect(self.text_edit.set_prev_debug_point)
        self.debug_next_button.clicked.connect(self.text_edit.set_next_debug_point)
        self.debug_paste_button.clicked.connect(self.debug_script)

    def on_ctrl_f_pressed(self):
        # Activar búsqueda solo si este panel tiene foco
        if self.isActiveWindow() or self.text_edit.hasFocus():
            self.show_search_bar()

    def show_search_bar(self):
        self.search_layout_widget.setVisible(not self.search_layout_widget.isVisible())
        if self.search_layout_widget.isVisible():
            self.search_input.setFocus()

    def get_search_value(self):
        search_text = self.search_input.text()
        if not search_text:
            return
        search_filter = self.search_filter_combo.currentText()
        if search_filter == "Node Type":
            search_text = r"^\s*(" + search_text + r")\s\{$"
        elif search_filter == "Node Name":
            search_text = r"^\s*name " + search_text + r"$"
        elif search_filter == "Knob":
            search_text = r"^\s*(" + search_text + r")(?:\s([a-zA-Z0-9_]+))?"
        elif search_filter == "User Knob":
            search_text = r"^\s*(addUserKnob)\s\{([0-9]+)\s(" + search_text + r")"
        return search_text

    def find_previous(self):
        search_text = self.get_search_value()
        if not search_text:
            return
        cursor = self.text_edit.textCursor()
        document = self.text_edit.document()
        found = document.find(QtCore.QRegExp(search_text), cursor, QtGui.QTextDocument.FindBackward)
        if found.isNull():
            cursor.setPosition(document.characterCount() - 1)
            found = document.find(search_text, cursor, QtGui.QTextDocument.FindBackward)
        if not found.isNull():
            self.text_edit.setTextCursor(found)

    def find_next(self):
        search_text = self.get_search_value()
        if not search_text:
            return
        cursor = self.text_edit.textCursor()
        document = self.text_edit.document()
        found = document.find(QtCore.QRegExp(search_text), cursor)
        if found.isNull():
            # Wrap around and search from top
            cursor.setPosition(0)
            found = document.find(search_text, cursor)
        if not found.isNull():
            self.text_edit.setTextCursor(found)

    def find_next_invalid_char(self):
        # Regex for invalid characters (same as in NkHighlighter)
        invalid_pattern = QtCore.QRegExp(r"[^\x20-\x7E\t\r\n]")
        document = self.text_edit.document()
        cursor = self.text_edit.textCursor()
        found = document.find(invalid_pattern, cursor)

        if found.isNull():
            # Wrap and search from start
            cursor.setPosition(0)
            found = document.find(invalid_pattern, cursor)

        if not found.isNull():
            self.text_edit.setTextCursor(found)
        else:
            nuke.message("No invalid characters found.")

    def browse_file(self):
        file_path = nuke.getFilename('Select a .nk', '*.nk')
        if file_path:
            self.file_path_lineedit.setText(file_path)

    def load_nk_file_into_editor(self):
        file_path = self.file_path_lineedit.text()
        if file_path and os.path.isfile(file_path):
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                    self.text_edit.setPlainText(content)
            except Exception as e:
                nuke.message(f"No se pudo cargar el archivo:\n{e}")
        else:
            nuke.message(f"The filepath '{file_path}' does not exist.")

    def toggle_wrap_text(self, checked):
        self.text_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth if checked else QtWidgets.QPlainTextEdit.NoWrap)

    def load_nodegraph_into_editor(self):
        try:
            import tempfile
            temp_path = os.path.join(tempfile.gettempdir(), 'nk_temp_script.nk')
            nuke.scriptSaveToTemp(temp_path)
            with open(temp_path, 'r') as f:
                content = f.read()
                self.text_edit.setPlainText(content)
            os.remove(temp_path)
        except Exception as e:
            nuke.message(f"Error loading node graph: {e}")

    def load_root_into_editor(self):
        file_path = nuke.scriptName()
        if file_path:
            self.file_path_lineedit.setText(file_path)
            self.load_nk_file_into_editor()

    def _paste_plain_text(self, script, clean_nodegraph=False):
        try:
            app = QtWidgets.QApplication.instance()
            clipboard = app.clipboard()

            # Backup the current clipboard
            old_mime = clipboard.mimeData()
            backup = QtCore.QMimeData()
            for fmt in old_mime.formats():
                backup.setData(fmt, old_mime.data(fmt))

            # Override clipboard with PlainText Script
            clipboard.setText(script)
            if clean_nodegraph:
                for node in nuke.allNodes(recurseGroups=False):
                    nuke.delete(node)

            # Load clipboard in Nuke
            nuke.nodePaste("%clipboard%")

            # Restore backup
            clipboard.setMimeData(backup)
        except Exception as e:
            nuke.message(f"Error pasting node graph: {e}")

    def debug_script(self):
        script = self.text_edit.get_text_until_debug_point()
        self._paste_plain_text(
            script, clean_nodegraph=self.override_checkbox.isChecked())

    def paste_script(self):
        script = self.text_edit.toPlainText()
        self._paste_plain_text(script)

    def save_script(self):
        file_path = nuke.getFilename('Select a .nk', '*.nk')
        if file_path:
            script = self.text_edit.toPlainText()
            try:
                with open(file_path, 'w') as f:
                    f.write(script)
                nuke.message(f"Script saved to: {file_path}")
            except Exception as e:
                nuke.message(f"Error saving script: {e}")
