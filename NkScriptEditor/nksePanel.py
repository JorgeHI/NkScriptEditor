# -----------------------------------------------------------------------------
# Nk Script Editor for Nuke
# Copyright (c) 2025 Jorge Hernandez Ibañez
#
# This file is part of the Nk Script Editor project.
# Repository: https://github.com/JorgeHI/NkScriptEditor
#
# This file is licensed under the MIT License.
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
from NkScriptEditor import nkHelpTab
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
    """
    Main widget for the Nk Script Editor panel in Nuke.

    This tool provides an integrated editor for viewing and editing `.nk` files
    with syntax highlighting, breakpoint navigation, and script management capabilities.
    It features:
    - Live loading of nodegraph or '.nk' file paths
    - A custom syntax highlighter for key Nuke script elements
    - Debugging support with clickable breakpoints and playback slicing
    - Configurable preferences, including color and bold styles for syntax elements
    - File encoding options for proper reading/writing of international text

    The panel is structured as a tabbed interface including an "Editor" tab and a "Preferences" tab.
    """
    def __init__(self):
        super(NkScriptEditor, self).__init__()

        self.setWindowTitle("Nk Script Editor")

        if hasattr(QtCore, 'QRegularExpression'):  # PySide6
            self._qRe_class = QtCore.QRegularExpression
        else:
            self._qRe_class = QtCore.QRegExp

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
        self.encoding_combo = QtWidgets.QComboBox()
        self.encoding_combo.addItems(nkConstants.encodings)
        self.encoding_combo.setCurrentText("utf-8")  # default
        # Compute minimin width based n the elements
        font_metrics = self.encoding_combo.fontMetrics()
        max_width = max(
            font_metrics.boundingRect(self.encoding_combo.itemText(i)).width()
            for i in range(self.encoding_combo.count())
        )
        self.encoding_combo.setMaximumWidth(max_width + 10)
        self.encoding_combo.setToolTip("Encoding used for loading and save scripts.")
        buttons_layout.addWidget(self.encoding_combo)
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

        # ----------------------
        # 3) Help Tab
        # ----------------------
        self.help_page = nkHelpTab.HelpTabWidget()
        self.tabs.addTab(self.help_page, "Help")

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
        self.prefs_page.apply_preferences.connect(self.highlighter.update_formats)
        # Debug button connections
        self.debug_clear_button.clicked.connect(self.text_edit.clean_all_debug_points)
        self.debug_prev_button.clicked.connect(self.text_edit.set_prev_debug_point)
        self.debug_next_button.clicked.connect(self.text_edit.set_next_debug_point)
        self.debug_paste_button.clicked.connect(self.debug_script)

        # Force refresh to load current preferences state
        self.prefs_page.force_refresh()

    def on_ctrl_f_pressed(self):
        """Show the search bar only if this widget or its text editor is focused."""
        if self.isActiveWindow() or self.text_edit.hasFocus():
            self.show_search_bar()

    def show_search_bar(self):
        """Toggle the visibility of the search bar widget and focus the input if shown."""
        self.search_layout_widget.setVisible(not self.search_layout_widget.isVisible())
        if self.search_layout_widget.isVisible():
            self.search_input.setFocus()

    def get_search_value(self):
        """
        Generate a regular expression based on the search filter and input text.

        Returns:
            str: A regular expression string to match in the editor.
        """
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
        """Find and select the previous occurrence of the search value in the editor."""
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
        """Find and select the next occurrence of the search value in the editor."""
        search_text = self.get_search_value()
        if not search_text:
            return
        cursor = self.text_edit.textCursor()
        document = self.text_edit.document()
        found = document.find(self._qRe_class(search_text), cursor)
        if found.isNull():
            # Wrap around and search from top
            cursor.setPosition(0)
            found = document.find(search_text, cursor)
        if not found.isNull():
            self.text_edit.setTextCursor(found)

    def find_next_invalid_char(self):
        """Find and select the next invalid character in the editor."""
        # Regex for invalid characters (same as in NkHighlighter)
        invalid_pattern = self._qRe_class(nkConstants.nkRegex.invalid)
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
        """Open a file dialog and populate the file path field with the selected file."""
        file_path = nuke.getFilename('Select a .nk', '*.nk')
        if file_path:
            self.file_path_lineedit.setText(file_path)

    def load_nk_file_into_editor(self):
        """Load a '.nk' file into the editor based on the user-selected encoding."""
        file_path = self.file_path_lineedit.text()
        if file_path and os.path.isfile(file_path):
            selected_encoding = self.encoding_combo.currentText()
            try:
                with open(file_path, 'r', encoding=selected_encoding) as f:
                    content = f.read()
                    self.text_edit.setPlainText(content)
            except Exception as e:
                msg = f"Nk file could not be loaded:\n{e}"
                logger.error(msg)
                nuke.message(msg)
        else:
            msg = f"The filepath '{file_path}' does not exist."
            logger.error(msg)
            nuke.message(msg)

    def toggle_wrap_text(self, checked):
        """Enable or disable text wrapping in the editor based on the checkbox state."""
        self.text_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth if checked else QtWidgets.QPlainTextEdit.NoWrap)

    def get_nodegraph_script(self):
        try:
            import tempfile
            temp_path = os.path.join(tempfile.gettempdir(), 'nk_temp_script.nk')
            nuke.scriptSaveToTemp(temp_path)
            selected_encoding = self.encoding_combo.currentText()
            with open(temp_path, 'r', encoding=selected_encoding) as f:
                content = f.read()
            os.remove(temp_path)
        except Exception as e:
            msg = f"Error loading node graph: {e}"
            logger.error(msg)
            nuke.message(msg)
            return
        return content

    def load_nodegraph_into_editor(self):
        """Dump the current node graph to a temporary file and load its contents into the editor."""
        content = self.get_nodegraph_script()
        if content:
            self.text_edit.setPlainText(content)

    def load_root_into_editor(self):
        """Load the root Nuke script path into the editor if available."""
        file_path = nuke.scriptName()
        if file_path:
            self.file_path_lineedit.setText(file_path)
            self.load_nk_file_into_editor()

    def _move_cursor_to_error_line(self, add_debug_point=False):
        """
        Estimate the line number where nodePaste failed by comparing the partial
        nodegraph script with the full text editor content, starting from 'Root {'.

        Moves the text cursor to that approximate error line.

        Returns:
            int: The last loaded line number.

        TODO:
            Instead of compare directly, get the last loaded node with Regex.
            Find that node in the text editor and set the cursor to the next line.
        """
        error_script = self.get_nodegraph_script()
        error_lines = error_script.splitlines()

        # Find the Root start
        try:
            root_index_error = next(i for i, l in enumerate(error_lines) if "Root {" in l)
        except StopIteration:
            logger.warning("'Root {' not found in error script.")
            return

        # Find number of lines after root
        error_lines_after_root = error_lines[root_index_error:]
        num_valid_lines = len(error_lines_after_root) - 1

        # Obtener el texto actual en el editor
        full_text = self.text_edit.toPlainText()
        full_lines = full_text.splitlines()

        try:
            root_index_editor = next(i for i, l in enumerate(full_lines) if "Root {" in l)
        except StopIteration:
            logger.warning("'Root {' not found in text editor.")
            return

        # Last valid line
        target_line = root_index_editor + num_valid_lines

        block = self.text_edit.document().findBlockByLineNumber(target_line)
        if block.isValid():
            cursor = self.text_edit.textCursor()
            cursor.setPosition(block.position())
            self.text_edit.setTextCursor(cursor)
            self.text_edit.setFocus()
            if add_debug_point:
                self.text_edit.add_debug_point(target_line)
                self.text_edit.set_active_debug_point(target_line)
        return target_line


    def _paste_plain_text(self, script, clean_nodegraph=False):
        """
        Paste the given plain text script into Nuke.

        Args:
            script (str): Nuke script as plain text.
            clean_nodegraph (bool): Whether to clear the current node graph before pasting.

        Notes:
            This method use the %clipboard% to paste the text. It makes a backup
            of the clipboard to restore it after paste.
        """
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
            try:
                nuke.nodePaste("%clipboard%")
            except Exception as e:
                logger.error(f"Error on script paste: {e}")
                # TODO look for errors on paste and move the cursor to the line
                # self._move_cursor_to_error_line(add_debug_point=True)

            # Restore backup
            clipboard.setMimeData(backup)
        except Exception as e:
            msg = f"Error pasting node graph: {e}"
            logger.error(msg)
            nuke.message(msg)

    def debug_script(self):
        """Paste the portion of the script up to the current debug point into Nuke."""
        script = self.text_edit.get_text_until_debug_point()
        self._paste_plain_text(
            script, clean_nodegraph=self.override_checkbox.isChecked())

    def paste_script(self):
        """Paste the entire contents of the editor into Nuke."""
        script = self.text_edit.toPlainText()
        self._paste_plain_text(script)

    def save_script(self):
        """Open a file dialog and save the script to a selected path using chosen encoding."""
        file_path = nuke.getFilename('Select a .nk', '*.nk')
        if file_path:
            script = self.text_edit.toPlainText()
            selected_encoding = self.encoding_combo.currentText()
            try:
                with open(file_path, 'w', encoding=selected_encoding) as f:
                    f.write(script)
                nuke.message(f"Script saved to: {file_path}")
            except Exception as e:
                msg = f"Error saving script: {e}"
                logger.error(msg)
                nuke.message(msg)
