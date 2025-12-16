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
import difflib

import nuke
from NkScriptEditor import nkseHighlighter
from NkScriptEditor import nkCodeEditor
from NkScriptEditor import nkPreferences
from NkScriptEditor import nkHelpTab
from NkScriptEditor import nkConstants
from NkScriptEditor import nkUtils
from NkScriptEditor import nkParser
from NkScriptEditor import nkDiffViewer
from NkScriptEditor.nkDiffViewer import DiffTextEdit
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


from functools import partial


class MergeControlWidget(QtWidgets.QWidget):
    """Widget showing merge controls between diff editors.

    Displays arrow buttons at each diff block that allow copying changes
    from the right (compare) editor to the left (editable) editor.
    """

    merge_requested = QtCore.Signal(str, int, int, int, int)  # (tag, i1, i2, j1, j2)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(30)
        self.diff_blocks = []  # List of (tag, i1, i2, j1, j2, y_pos)
        self.buttons = []  # List of merge buttons
        self.editor_offset = 0  # Vertical offset to account for file selector

        # Style the widget
        self.setStyleSheet("""
            MergeControlWidget {
                background-color: #2a2a2a;
                border-left: 1px solid #555;
                border-right: 1px solid #555;
            }
            QPushButton {
                background-color: #3a7ebf;
                color: white;
                border: 1px solid #555;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a8ecf;
            }
            QPushButton:pressed {
                background-color: #2a6eaf;
            }
        """)

    def set_diff_blocks(self, diff_blocks, left_editor, right_editor, editor_widget):
        """Update diff blocks and create merge buttons.

        Args:
            diff_blocks: List of (tag, i1, i2, j1, j2) tuples from SequenceMatcher
            left_editor: Reference to left CodeEditor
            right_editor: Reference to right CodeEditor
            editor_widget: Reference to left_editor_container to calculate offset
        """
        # Clear existing buttons
        for btn in self.buttons:
            btn.deleteLater()
        self.buttons = []
        self.diff_blocks = []

        # Calculate offset from file selector and other widgets above the editor
        # Get the editor's position within its parent container
        editor_y_in_container = left_editor.mapTo(editor_widget, left_editor.rect().topLeft()).y()
        self.editor_offset = editor_y_in_container

        # Create buttons for each diff block
        for tag, i1, i2, j1, j2 in diff_blocks:
            if tag != 'equal':
                # Calculate vertical position based on left editor line position
                y_pos = self._get_line_y_position(left_editor, i1)

                # Add offset to account for file selector above editor
                adjusted_y_pos = y_pos + self.editor_offset

                # Create merge button (smaller to match line height)
                btn = QtWidgets.QPushButton("←", self)
                btn.setFixedSize(24, 16)  # Smaller height to match line height
                btn.setToolTip(self._get_tooltip(tag, i1, i2, j1, j2))
                btn.move(3, adjusted_y_pos)

                # Use partial to avoid lambda closure issues
                btn.clicked.connect(
                    partial(self._emit_merge_request, tag, i1, i2, j1, j2)
                )
                btn.show()

                self.buttons.append(btn)
                self.diff_blocks.append((tag, i1, i2, j1, j2, adjusted_y_pos))

    def _emit_merge_request(self, tag, i1, i2, j1, j2):
        """Helper method to emit merge request signal."""
        self.merge_requested.emit(tag, i1, i2, j1, j2)

    def _get_line_y_position(self, editor, line_num):
        """Get Y position for a line number in the editor relative to viewport."""
        block = editor.document().findBlockByNumber(line_num)
        if block.isValid():
            # Get the bounding geometry for the block
            block_geometry = editor.blockBoundingGeometry(block)
            # Translate by content offset to get position relative to viewport
            block_top = block_geometry.translated(editor.contentOffset()).top()
            return int(block_top)
        return 0

    def _get_tooltip(self, tag, i1, i2, j1, j2):
        """Generate tooltip text for merge button."""
        if tag == 'insert':
            return f"Accept {j2-j1} added line(s) from right"
        elif tag == 'delete':
            return f"Accept deletion of {i2-i1} line(s)"
        elif tag == 'replace':
            return f"Replace {i2-i1} line(s) with {j2-j1} from right"
        return "Merge change"

    def update_positions(self, left_editor):
        """Update button positions after scrolling or text changes."""
        for i, (tag, i1, i2, j1, j2, old_y) in enumerate(self.diff_blocks):
            new_y = self._get_line_y_position(left_editor, i1)
            # Add offset to account for file selector
            adjusted_y = new_y + self.editor_offset
            if i < len(self.buttons):
                self.buttons[i].move(3, adjusted_y)
                # Update stored position
                self.diff_blocks[i] = (tag, i1, i2, j1, j2, adjusted_y)


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

        # Menu button with actions
        self.menu_button = QtWidgets.QToolButton()
        self.menu_button.setText("⋮")
        self.menu_button.setToolTip("Additional actions")
        self.menu_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.menu_button.setStyleSheet(
            "QToolButton { font-size: 14px; padding: 2px 4px; } "
            "QToolButton::menu-indicator { width: 0px; }"
        )

        # Create menu with actions
        self.actions_menu = QtWidgets.QMenu(self.menu_button)
        self.validate_action = self.actions_menu.addAction("Validate Script")
        self.validate_action.setToolTip("Check script structure for errors")
        self.compare_action = self.actions_menu.addAction("Compare...")
        self.compare_action.setToolTip("Compare current script with another .nk file")
        self.actions_menu.addSeparator()
        self.debug_toggle_action = self.actions_menu.addAction("Show Debug")
        self.debug_toggle_action.setToolTip("Show/hide debugging controls")

        self.menu_button.setMenu(self.actions_menu)
        buttons_layout.addWidget(self.menu_button)

        editor_layout.addLayout(buttons_layout)

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

        # -- Dual editor layout with horizontal splitter
        self.editor_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        # Set size policy to expand vertically
        self.editor_splitter.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        self.editor_splitter.setHandleWidth(4)

        # === LEFT EDITOR CONTAINER (Main/Editable) ===
        self.left_editor_container = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(self.left_editor_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        # Add file selector for left editor
        left_file_selector_layout, self.left_file_path_lineedit, self.browse_button, self.load_nk_button = self._create_file_selector(
            "Select a file .nk...", "Load nk file"
        )
        # Keep backward compatibility reference
        self.file_path_lineedit = self.left_file_path_lineedit
        # Connect signals
        self.browse_button.clicked.connect(self.browse_file)
        self.load_nk_button.clicked.connect(self.load_nk_file_into_editor)
        left_layout.addLayout(left_file_selector_layout)

        # Add main script editor
        self.text_edit = nkCodeEditor.CodeEditor()
        left_layout.addWidget(self.text_edit)  # No stretch factor in splitter
        self.highlighter = nkseHighlighter.NkHighlighter(self.text_edit.document())

        # === RIGHT EDITOR CONTAINER (Compare View) ===
        self.right_editor_container = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(self.right_editor_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        # Add right file selector for compare
        right_file_selector_layout, self.right_file_path_lineedit, self.right_browse_button, self.right_load_compare_button = self._create_file_selector(
            "Select file to compare...", "Load compare file"
        )
        right_layout.addLayout(right_file_selector_layout)

        # Create compare editor (read-only CodeEditor)
        self.compare_editor = nkCodeEditor.CodeEditor()
        self.compare_editor.setReadOnly(True)  # Make it read-only
        self.compare_editor.disable_breakpoints()  # Disable breakpoint toggling
        right_layout.addWidget(self.compare_editor)

        # Add syntax highlighter to compare editor
        self.compare_highlighter = nkseHighlighter.NkHighlighter(self.compare_editor.document())

        # Create merge control widget
        self.merge_control_widget = MergeControlWidget()
        self.merge_control_widget.merge_requested.connect(self._handle_merge_request)

        # Add all three widgets to splitter (left, merge controls, right)
        self.editor_splitter.addWidget(self.left_editor_container)
        self.editor_splitter.addWidget(self.merge_control_widget)
        self.editor_splitter.addWidget(self.right_editor_container)

        # Set sizes: left=600, merge=30, right=600
        self.editor_splitter.setSizes([600, 30, 600])

        # Style splitter
        self.editor_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #555;
            }
            QSplitter::handle:hover {
                background-color: #777;
            }
        """)

        # Hide compare view and merge controls by default
        self.right_editor_container.setVisible(False)
        self.merge_control_widget.setVisible(False)
        self.compare_visible = False

        # Add state tracking for diff
        self.diff_positions = []
        self.current_diff_index = -1
        self.diff_extra_selections = []  # Store diff highlights for left editor
        self.diff_extra_selections_right = []  # Store diff highlights for right editor

        # Setup scroll synchronization
        self._setup_scroll_sync()

        # Connect to preserve diff highlighting when editors update selections or text changes
        # Use lambda with QTimer to ensure it runs after CodeEditor's own highlight_current_line
        self.text_edit.cursorPositionChanged.connect(
            lambda: QtCore.QTimer.singleShot(0, self._update_left_editor_selections)
        )
        self.compare_editor.cursorPositionChanged.connect(
            lambda: QtCore.QTimer.singleShot(0, self._update_right_editor_selections)
        )

        # Also update when text content changes (editing)
        self.text_edit.textChanged.connect(
            lambda: QtCore.QTimer.singleShot(0, self._update_left_editor_selections)
        )

        # Add splitter to main layout
        editor_layout.addWidget(self.editor_splitter)

        # -- Compare controls (outside splitter, at bottom, spanning full width)
        self.compare_controls_widget = QtWidgets.QWidget()
        compare_controls_layout = QtWidgets.QHBoxLayout(self.compare_controls_widget)
        compare_controls_layout.setContentsMargins(0, 0, 0, 0)
        compare_controls_layout.setSpacing(8)

        # Compare title
        self.compare_title_label = QtWidgets.QLabel("Compare View")
        self.compare_title_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        compare_controls_layout.addWidget(self.compare_title_label)

        # Separator
        compare_controls_layout.addSpacing(10)

        # Diff legend
        legend_items = [
            ("Added", "#285028"),
            ("Deleted", "#642828"),
            ("Modified", "#5a5028")
        ]

        for label_text, color in legend_items:
            indicator = QtWidgets.QLabel("  ")
            indicator.setStyleSheet(f"background-color: {color}; border: 1px solid #555;")
            indicator.setFixedSize(16, 12)
            compare_controls_layout.addWidget(indicator)
            label = QtWidgets.QLabel(label_text)
            label.setStyleSheet("font-size: 9pt;")
            compare_controls_layout.addWidget(label)
            compare_controls_layout.addSpacing(8)

        # Stretch to push navigation to the right
        compare_controls_layout.addStretch()

        # Navigation buttons
        self.prev_diff_btn = QtWidgets.QPushButton("< Prev")
        self.prev_diff_btn.setMaximumWidth(60)
        compare_controls_layout.addWidget(self.prev_diff_btn)

        self.diff_counter_label = QtWidgets.QLabel("0 / 0")
        self.diff_counter_label.setStyleSheet("padding: 0 8px;")
        compare_controls_layout.addWidget(self.diff_counter_label)

        self.next_diff_btn = QtWidgets.QPushButton("Next >")
        self.next_diff_btn.setMaximumWidth(60)
        compare_controls_layout.addWidget(self.next_diff_btn)

        # Close button
        self.close_compare_button = QtWidgets.QPushButton("✕")
        self.close_compare_button.setFixedSize(24, 24)
        self.close_compare_button.setToolTip("Close compare view")
        compare_controls_layout.addWidget(self.close_compare_button)

        # Hide compare controls by default
        self.compare_controls_widget.setVisible(False)
        editor_layout.addWidget(self.compare_controls_widget)

        # -- Auto-validation timer (500ms debounce)
        self.validation_timer = QtCore.QTimer()
        self.validation_timer.setSingleShot(True)
        self.validation_timer.setInterval(500)
        self.validation_timer.timeout.connect(self._on_validation_timer)

        # -- Status bar counters
        self.node_count = 0
        self.error_count = 0
        self.warning_count = 0
        self.current_line = 1
        self.current_column = 1
        self.total_lines = 1

        # -- Debug controls (wrapped in a widget for visibility toggle)
        self.debug_widget = QtWidgets.QWidget()
        self.debug_layout = QtWidgets.QHBoxLayout(self.debug_widget)
        self.debug_layout.setContentsMargins(0, 0, 0, 0)
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
        self.debug_widget.setVisible(False)  # Hidden by default
        editor_layout.addWidget(self.debug_widget)

        # -- Paste / Save controls
        self.save_layout = QtWidgets.QHBoxLayout()
        self.paste_button = QtWidgets.QPushButton("Paste Script")
        self.paste_button.clicked.connect(self.paste_script)
        self.saveas_button = QtWidgets.QPushButton("Save Script")
        self.saveas_button.clicked.connect(self.save_script)
        self.save_layout.addWidget(self.paste_button)
        self.save_layout.addWidget(self.saveas_button)
        editor_layout.addLayout(self.save_layout)

        # -- Status Bar
        self.status_bar_layout = QtWidgets.QHBoxLayout()
        self.error_counter_label = QtWidgets.QLabel("⚠ 0 errors")
        self.error_counter_label.setStyleSheet("color: gray; padding: 2px 8px;")
        self.error_counter_label.setToolTip("Number of validation errors")
        self.warning_counter_label = QtWidgets.QLabel("⚠ 0 warnings")
        self.warning_counter_label.setStyleSheet("color: gray; padding: 2px 8px;")
        self.warning_counter_label.setToolTip("Number of validation warnings")
        self.line_position_label = QtWidgets.QLabel("Ln 1, Col 1 | 0 lines")
        self.line_position_label.setStyleSheet("color: #c0c0c0; padding: 2px 8px;")
        self.line_position_label.setToolTip("Current cursor position and total lines")
        self.node_counter_label = QtWidgets.QLabel("0 nodes")
        self.node_counter_label.setStyleSheet("color: #a0a0a0; padding: 2px 8px;")
        self.node_counter_label.setToolTip("Number of nodes detected in script")
        self.status_bar_layout.addWidget(self.error_counter_label)
        self.status_bar_layout.addWidget(self.warning_counter_label)
        self.status_bar_layout.addWidget(self.line_position_label)
        self.status_bar_layout.addWidget(self.node_counter_label)
        self.status_bar_layout.addStretch()
        editor_layout.addLayout(self.status_bar_layout)

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
        self.prefs_page.showEncodingToggled.connect(self.toggle_encoding_visibility)
        self.prefs_page.apply_preferences.connect(self.highlighter.update_formats)
        # Debug button connections
        self.debug_clear_button.clicked.connect(self.text_edit.clean_all_debug_points)
        self.debug_prev_button.clicked.connect(self.text_edit.set_prev_debug_point)
        self.debug_next_button.clicked.connect(self.text_edit.set_next_debug_point)
        self.debug_paste_button.clicked.connect(self.debug_script)

        # Menu actions connections
        self.validate_action.triggered.connect(self.validate_script)
        self.compare_action.triggered.connect(self.toggle_compare_view)
        self.debug_toggle_action.triggered.connect(self.toggle_debug_visibility)

        # Compare view signal connections
        self.close_compare_button.clicked.connect(self.toggle_compare_view)
        self.right_browse_button.clicked.connect(self.browse_compare_file)
        self.right_load_compare_button.clicked.connect(self.load_compare_file)
        self.prev_diff_btn.clicked.connect(self.go_to_prev_diff)
        self.next_diff_btn.clicked.connect(self.go_to_next_diff)

        # Auto-validation and status bar connections
        self.text_edit.textChanged.connect(self._on_text_changed)
        self.text_edit.cursorPositionChanged.connect(self._update_cursor_position)
        # Initial status bar update
        self._update_cursor_position()
        self._update_status_bar()

        # Force refresh to load current preferences state
        self.prefs_page.force_refresh()

        # Load debug visibility preference
        self.load_debug_visibility_preference()

        # Load compare visibility preference
        self.load_compare_visibility_preference()

    def _create_file_selector(self, placeholder_text, load_button_text=None):
        """
        Create a reusable file selector layout with lineedit, browse button, and optional load button.

        Args:
            placeholder_text (str): Placeholder text for the line edit
            load_button_text (str, optional): Text for the load button. If None, no load button is created.

        Returns:
            tuple: (layout, lineedit, browse_button, load_button or None)
        """
        file_selector_layout = QtWidgets.QHBoxLayout()

        # Create line edit
        file_path_lineedit = QtWidgets.QLineEdit()
        file_path_lineedit.setPlaceholderText(placeholder_text)

        # Create browse button
        browse_button = QtWidgets.QToolButton()
        browse_icon = QtGui.QIcon(nkConstants.icons.open_folder)
        browse_button.setIcon(browse_icon)

        # Add widgets to layout
        file_selector_layout.addWidget(file_path_lineedit)
        file_selector_layout.addWidget(browse_button)

        # Create optional load button
        load_button = None
        if load_button_text:
            load_button = QtWidgets.QPushButton(load_button_text)
            file_selector_layout.addWidget(load_button)

        return file_selector_layout, file_path_lineedit, browse_button, load_button

    def load_debug_visibility_preference(self):
        """Load the debug visibility state from preferences on startup."""
        import json
        import os

        try:
            if os.path.isfile(nkConstants.pref_filepath):
                with open(nkConstants.pref_filepath, 'r') as f:
                    prefs = json.load(f)
                is_visible = prefs.get("debug_visible", False)  # Default to hidden
            else:
                is_visible = False  # Default to hidden

            # Apply visibility state
            self.debug_widget.setVisible(is_visible)

            # Update menu action text
            self.debug_toggle_action.setText("Hide Debug" if is_visible else "Show Debug")

            logger.debug(f"Debug visibility loaded from preferences: {is_visible}")
        except Exception as e:
            logger.error(f"Failed to load debug visibility preference: {e}")
            # Default to hidden on error
            self.debug_widget.setVisible(False)
            self.debug_toggle_action.setText("Show Debug")

    def on_ctrl_f_pressed(self):
        """Show the search bar only if this widget or its text editor is focused."""
        if self.isActiveWindow() or self.text_edit.hasFocus():
            self.show_search_bar()

    def show_search_bar(self):
        """Toggle the visibility of the search bar widget and focus the input if shown."""
        self.search_layout_widget.setVisible(not self.search_layout_widget.isVisible())
        if self.search_layout_widget.isVisible():
            self.search_input.setFocus()

    def toggle_debug_visibility(self):
        """
        Toggle the visibility of the debug controls row.

        Updates the menu action text based on current state and saves the
        preference for persistence across sessions.
        """
        # Toggle visibility
        is_visible = not self.debug_widget.isVisible()
        self.debug_widget.setVisible(is_visible)

        # Update menu action text
        self.debug_toggle_action.setText("Hide Debug" if is_visible else "Show Debug")

        # Save preference
        self.save_debug_visibility_preference(is_visible)

        logger.info(f"Debug controls {'shown' if is_visible else 'hidden'}")

    def save_debug_visibility_preference(self, is_visible):
        """
        Save the debug visibility state to preferences.

        Args:
            is_visible (bool): Whether debug controls are visible
        """
        import json
        import os

        try:
            # Load existing preferences
            if os.path.isfile(nkConstants.pref_filepath):
                with open(nkConstants.pref_filepath, 'r') as f:
                    prefs = json.load(f)
            else:
                prefs = {}

            # Update debug visibility
            prefs["debug_visible"] = is_visible

            # Save preferences
            os.makedirs(nkConstants.config_dir, exist_ok=True)
            with open(nkConstants.pref_filepath, 'w', encoding='utf-8') as f:
                json.dump(prefs, f, indent=4)

            logger.debug(f"Debug visibility preference saved: {is_visible}")
        except Exception as e:
            logger.error(f"Failed to save debug visibility preference: {e}")

    def toggle_compare_view(self):
        """Toggle visibility of the compare view."""
        self.compare_visible = not self.compare_visible
        self.right_editor_container.setVisible(self.compare_visible)
        self.compare_controls_widget.setVisible(self.compare_visible)
        self.merge_control_widget.setVisible(self.compare_visible)

        # Update menu action text
        self.compare_action.setText("Hide Compare" if self.compare_visible else "Compare...")

        # If showing, trigger diff computation if both texts are available
        if self.compare_visible:
            left_text = self.text_edit.toPlainText()
            right_text = self.compare_editor.toPlainText()
            if left_text.strip() and right_text.strip():
                self.compute_inline_diff()
        else:
            # If hiding, clear diff highlighting from both editors
            self.diff_extra_selections = []
            self.diff_extra_selections_right = []
            self._update_left_editor_selections()
            self._update_right_editor_selections()

        # Save preference
        self.save_compare_visibility_preference(self.compare_visible)

        logger.info(f"Compare view {'shown' if self.compare_visible else 'hidden'}")

    def load_compare_visibility_preference(self):
        """Load compare visibility state from preferences on startup."""
        try:
            if os.path.isfile(nkConstants.pref_filepath):
                with open(nkConstants.pref_filepath, 'r') as f:
                    prefs = json.load(f)
                is_visible = prefs.get("compare_visible", False)
            else:
                is_visible = False

            self.compare_visible = is_visible
            self.right_editor_container.setVisible(is_visible)
            self.compare_controls_widget.setVisible(is_visible)
            self.merge_control_widget.setVisible(is_visible)
            self.compare_action.setText("Hide Compare" if is_visible else "Compare...")

            logger.debug(f"Compare visibility loaded: {is_visible}")
        except Exception as e:
            logger.error(f"Failed to load compare visibility: {e}")
            self.compare_visible = False
            self.right_editor_container.setVisible(False)
            self.compare_controls_widget.setVisible(False)
            self.merge_control_widget.setVisible(False)

    def save_compare_visibility_preference(self, is_visible):
        """Save compare visibility state to preferences."""
        try:
            if os.path.isfile(nkConstants.pref_filepath):
                with open(nkConstants.pref_filepath, 'r') as f:
                    prefs = json.load(f)
            else:
                prefs = {}

            prefs["compare_visible"] = is_visible

            os.makedirs(nkConstants.config_dir, exist_ok=True)
            with open(nkConstants.pref_filepath, 'w', encoding='utf-8') as f:
                json.dump(prefs, f, indent=4)

            logger.debug(f"Compare visibility saved: {is_visible}")
        except Exception as e:
            logger.error(f"Failed to save compare visibility: {e}")

    def browse_compare_file(self):
        """Open file dialog to select compare file."""
        file_path = nuke.getFilename('Select a .nk file to compare', '*.nk')
        if file_path:
            self.right_file_path_lineedit.setText(file_path)

    def load_compare_file(self):
        """Load selected file into compare editor."""
        file_path = self.right_file_path_lineedit.text()
        if file_path and os.path.isfile(file_path):
            selected_encoding = self.encoding_combo.currentText()
            try:
                with open(file_path, 'r', encoding=selected_encoding) as f:
                    content = f.read()
                self.compare_editor.setPlainText(content)
                self.compare_title_label.setText(f"Compare: {os.path.basename(file_path)}")

                # Auto-compute diff if compare view is visible
                if self.compare_visible:
                    self.compute_inline_diff()

                logger.info(f"Compare file loaded: {file_path}")
            except Exception as e:
                msg = f"Compare file could not be loaded:\n{e}"
                logger.error(msg)
                nuke.message(msg)
        else:
            nuke.message(f"The filepath '{file_path}' does not exist.")

    def compute_inline_diff(self):
        """Compute and display diff between left and right editors."""
        left_text = self.text_edit.toPlainText()
        right_text = self.compare_editor.toPlainText()

        if not left_text.strip() or not right_text.strip():
            logger.warning("Cannot compute diff: one or both editors are empty")
            return

        left_lines = left_text.splitlines()
        right_lines = right_text.splitlines()

        matcher = difflib.SequenceMatcher(None, left_lines, right_lines)

        # Build line types for left editor (original content, just highlighting)
        # Build line types for right editor (original content, just highlighting)
        left_line_types = {}  # Map: line_num -> type
        right_line_types = {}  # Map: line_num -> type
        self.diff_positions = []
        self.diff_blocks = []  # Store diff blocks for merge controls

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                # Equal lines - no highlighting needed
                for idx in range(i1, i2):
                    left_line_types[idx] = 'equal'
                for idx in range(j1, j2):
                    right_line_types[idx] = 'equal'
            elif tag == 'replace':
                # Modified lines - show as mod on both sides
                for idx in range(i1, i2):
                    left_line_types[idx] = 'mod'
                    self.diff_positions.append(idx)
                for idx in range(j1, j2):
                    right_line_types[idx] = 'mod'
                # Store for merge controls
                self.diff_blocks.append((tag, i1, i2, j1, j2))
            elif tag == 'delete':
                # Deleted lines - show as del on left only
                for idx in range(i1, i2):
                    left_line_types[idx] = 'del'
                    self.diff_positions.append(idx)
                # Store for merge controls
                self.diff_blocks.append((tag, i1, i2, j1, j2))
            elif tag == 'insert':
                # Added lines - show as add on right only
                for idx in range(j1, j2):
                    right_line_types[idx] = 'add'
                    self.diff_positions.append(idx)
                # Store for merge controls
                self.diff_blocks.append((tag, i1, i2, j1, j2))

        # Apply highlighting to both editors (keeps original content in both)
        self._apply_diff_highlighting_to_left(left_line_types)
        self._apply_diff_highlighting_to_right(right_line_types)

        # Update merge control buttons
        self.merge_control_widget.set_diff_blocks(
            self.diff_blocks, self.text_edit, self.compare_editor, self.left_editor_container
        )

        # Update diff counter
        self.current_diff_index = -1
        self._update_diff_counter()

        logger.debug(f"Inline diff computed: {len(self.diff_positions)} differences")

    def _apply_diff_highlighting_to_left(self, line_types_dict):
        """Apply diff highlighting to the left (main) editor.

        Args:
            line_types_dict: Dictionary mapping line_num -> type ('add', 'del', 'mod', 'equal')
        """
        # Store diff selections separately to preserve them
        self.diff_extra_selections = []

        colors = {
            'add': QtGui.QColor(40, 80, 40),    # Green
            'del': QtGui.QColor(100, 40, 40),   # Red
            'mod': QtGui.QColor(90, 80, 40),    # Yellow
        }

        for line_num, line_type in line_types_dict.items():
            if line_type in colors:
                selection = QtWidgets.QTextEdit.ExtraSelection()
                selection.format.setBackground(colors[line_type])
                selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
                # Mark this as a diff selection so we can identify it later
                selection.format.setProperty(QtGui.QTextFormat.UserProperty, "diff_highlight")

                # Create cursor and select the entire line to highlight wrapped portions
                block = self.text_edit.document().findBlockByNumber(line_num)
                cursor = QtGui.QTextCursor(block)
                cursor.movePosition(QtGui.QTextCursor.StartOfBlock)
                cursor.movePosition(QtGui.QTextCursor.EndOfBlock, QtGui.QTextCursor.KeepAnchor)
                selection.cursor = cursor
                self.diff_extra_selections.append(selection)

        # Merge with existing extra selections (like current line highlight)
        self._update_left_editor_selections()

    def _apply_diff_highlighting_to_right(self, line_types_dict):
        """Apply diff highlighting to the right (compare) editor.

        Args:
            line_types_dict: Dictionary mapping line_num -> type ('add', 'del', 'mod', 'equal')
        """
        # Store diff selections separately to preserve them
        self.diff_extra_selections_right = []

        colors = {
            'add': QtGui.QColor(40, 80, 40),    # Green
            'del': QtGui.QColor(100, 40, 40),   # Red
            'mod': QtGui.QColor(90, 80, 40),    # Yellow
        }

        for line_num, line_type in line_types_dict.items():
            if line_type in colors:
                selection = QtWidgets.QTextEdit.ExtraSelection()
                selection.format.setBackground(colors[line_type])
                selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
                # Mark this as a diff selection so we can identify it later
                selection.format.setProperty(QtGui.QTextFormat.UserProperty, "diff_highlight")

                # Create cursor and select the entire line to highlight wrapped portions
                block = self.compare_editor.document().findBlockByNumber(line_num)
                cursor = QtGui.QTextCursor(block)
                cursor.movePosition(QtGui.QTextCursor.StartOfBlock)
                cursor.movePosition(QtGui.QTextCursor.EndOfBlock, QtGui.QTextCursor.KeepAnchor)
                selection.cursor = cursor
                self.diff_extra_selections_right.append(selection)

        # Merge with existing extra selections (like current line highlight)
        self._update_right_editor_selections()

    def _update_left_editor_selections(self):
        """Update left editor selections, merging diff highlights with existing selections."""
        # Get current extra selections from the editor (if any)
        current_selections = self.text_edit.extraSelections()

        # Filter out old diff selections but keep all other selections (current line, errors, etc.)
        other_selections = []
        for sel in current_selections:
            # Keep selection if it's NOT marked as a diff highlight
            if sel.format.property(QtGui.QTextFormat.UserProperty) != "diff_highlight":
                other_selections.append(sel)

        # Combine: other selections + new diff selections
        all_selections = other_selections + self.diff_extra_selections

        # Apply all selections
        self.text_edit.setExtraSelections(all_selections)

    def _update_right_editor_selections(self):
        """Update right editor selections, merging diff highlights with existing selections."""
        # Get current extra selections from the editor (if any)
        current_selections = self.compare_editor.extraSelections()

        # Filter out old diff selections but keep all other selections (current line, errors, etc.)
        other_selections = []
        for sel in current_selections:
            # Keep selection if it's NOT marked as a diff highlight
            if sel.format.property(QtGui.QTextFormat.UserProperty) != "diff_highlight":
                other_selections.append(sel)

        # Combine: other selections + new diff selections
        all_selections = other_selections + self.diff_extra_selections_right

        # Apply all selections
        self.compare_editor.setExtraSelections(all_selections)

    def _update_diff_counter(self):
        """Update diff counter label."""
        total = len(self.diff_positions)
        current = self.current_diff_index + 1 if self.current_diff_index >= 0 else 0
        self.diff_counter_label.setText(f"{current} / {total}")

    def go_to_next_diff(self):
        """Navigate to next difference."""
        if not self.diff_positions:
            return

        self.current_diff_index += 1
        if self.current_diff_index >= len(self.diff_positions):
            self.current_diff_index = 0

        self._scroll_to_diff(self.current_diff_index)
        self._update_diff_counter()

    def go_to_prev_diff(self):
        """Navigate to previous difference."""
        if not self.diff_positions:
            return

        self.current_diff_index -= 1
        if self.current_diff_index < 0:
            self.current_diff_index = len(self.diff_positions) - 1

        self._scroll_to_diff(self.current_diff_index)
        self._update_diff_counter()

    def _scroll_to_diff(self, index):
        """Scroll both editors to show diff at given index."""
        if index < 0 or index >= len(self.diff_positions):
            return

        line_num = self.diff_positions[index]

        # Scroll compare editor
        block = self.compare_editor.document().findBlockByNumber(line_num)
        if block.isValid():
            cursor = QtGui.QTextCursor(block)
            self.compare_editor.setTextCursor(cursor)
            self.compare_editor.centerCursor()

        # Scroll main editor to same position
        block = self.text_edit.document().findBlockByNumber(line_num)
        if block.isValid():
            cursor = QtGui.QTextCursor(block)
            self.text_edit.setTextCursor(cursor)
            self.text_edit.centerCursor()

    def _handle_merge_request(self, tag, i1, i2, j1, j2):
        """Handle merge button click - copy changes from right to left.

        Args:
            tag: Diff type ('insert', 'delete', 'replace')
            i1, i2: Line range in left editor
            j1, j2: Line range in right editor
        """
        # Check if merge involves many lines and confirm with user
        num_lines = abs(i2 - i1) if tag in ('delete', 'replace') else abs(j2 - j1)
        if num_lines > 10:
            msg = f"This will merge {num_lines} lines. Continue?"
            reply = QtWidgets.QMessageBox.question(
                self, "Confirm Merge", msg,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.No:
                logger.info("Merge cancelled by user")
                return

        # Get current text from both editors
        left_lines = self.text_edit.toPlainText().splitlines(keepends=True)
        right_lines = self.compare_editor.toPlainText().splitlines(keepends=True)

        # Ensure lines end with newline for proper joining
        if left_lines and not left_lines[-1].endswith('\n'):
            left_lines[-1] += '\n'
        if right_lines and not right_lines[-1].endswith('\n'):
            right_lines[-1] += '\n'

        # Perform merge based on tag type
        if tag == 'insert':
            # Insert lines from right into left at position i1
            new_lines = left_lines[:i1] + right_lines[j1:j2] + left_lines[i1:]
        elif tag == 'delete':
            # Remove lines from left (accept deletion)
            new_lines = left_lines[:i1] + left_lines[i2:]
        elif tag == 'replace':
            # Replace lines in left with lines from right
            new_lines = left_lines[:i1] + right_lines[j1:j2] + left_lines[i2:]
        else:
            logger.warning(f"Unknown diff tag: {tag}")
            return

        # Update left editor with merged content
        self.text_edit.setPlainText(''.join(new_lines))

        # Recompute diff after merge (with slight delay to let UI update)
        QtCore.QTimer.singleShot(100, self.compute_inline_diff)

        logger.info(f"Merged {tag} block: left[{i1}:{i2}] <- right[{j1}:{j2}]")

    def _setup_scroll_sync(self):
        """Setup synchronized scrolling between left and right editors."""
        # Vertical scroll sync
        self.text_edit.verticalScrollBar().valueChanged.connect(
            self.compare_editor.verticalScrollBar().setValue)
        self.compare_editor.verticalScrollBar().valueChanged.connect(
            self.text_edit.verticalScrollBar().setValue)

        # Horizontal scroll sync
        self.text_edit.horizontalScrollBar().valueChanged.connect(
            self.compare_editor.horizontalScrollBar().setValue)
        self.compare_editor.horizontalScrollBar().valueChanged.connect(
            self.text_edit.horizontalScrollBar().setValue)

        # Update merge button positions on vertical scroll
        self.text_edit.verticalScrollBar().valueChanged.connect(
            lambda: self.merge_control_widget.update_positions(self.text_edit)
        )

    def clear_compare_view(self):
        """Clear the compare editor and reset diff state."""
        self.compare_editor.clear()
        self.right_file_path_lineedit.clear()
        self.compare_title_label.setText("Compare View")
        self.diff_positions = []
        self.current_diff_index = -1
        self.diff_extra_selections = []  # Clear diff highlighting
        self._update_left_editor_selections()  # Update to remove highlights
        self._update_diff_counter()
        logger.debug("Compare view cleared")

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
                    # Clear any previous error markers when loading new content
                    self.text_edit.clear_error_line()
                    # Trigger auto-validation via timer
                    self.validation_timer.stop()
                    self.validation_timer.start()

                    # Auto-compute diff if compare view is visible
                    if self.compare_visible and self.compare_editor.toPlainText().strip():
                        self.compute_inline_diff()
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

    def toggle_encoding_visibility(self, show):
        """
        Show or hide the encoding combobox in the editor.

        Args:
            show (bool): True to show the encoding combobox, False to hide it and use UTF-8
        """
        self.encoding_combo.setVisible(show)
        # When hidden, always use UTF-8
        if not show:
            self.encoding_combo.setCurrentText("utf-8")
        logger.debug(f"Encoding selector {'shown' if show else 'hidden'}")

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
            # Clear any previous error markers when loading new content
            self.text_edit.clear_error_line()
            # Trigger auto-validation via timer
            self.validation_timer.stop()
            self.validation_timer.start()

            # Auto-compute diff if compare view is visible
            if self.compare_visible and self.compare_editor.toPlainText().strip():
                self.compute_inline_diff()

    def load_root_into_editor(self):
        """Load the root Nuke script path into the editor if available."""
        file_path = nuke.scriptName()
        if file_path:
            self.file_path_lineedit.setText(file_path)
            self.load_nk_file_into_editor()

    def _get_existing_node_names(self):
        """
        Get the names of all nodes currently existing in the Nuke nodegraph.

        Returns:
            set[str]: A set of node names currently in Nuke.
        """
        try:
            return {node.name() for node in nuke.allNodes(recurseGroups=True)}
        except Exception as e:
            logger.error(f"Error getting existing nodes: {e}")
            return set()

    def _detect_error_line(self, script_text, error_message=None, nodes_before_paste=None):
        """
        Detect the line where a script load/paste operation failed.

        This method uses multiple strategies to identify the error location:
        1. Parse the error message for explicit line numbers
        2. Compare nodes that existed before/after paste to find the last loaded node
        3. Find the first node that failed to load

        Args:
            script_text (str): The full script that was being loaded
            error_message (str, optional): The error message from Nuke, if any
            nodes_before_paste (set[str], optional): Node names that existed before paste

        Returns:
            tuple: (error_line, error_info) where error_line is the 1-based line number
                   and error_info is a string describing what was detected
        """
        # Strategy 1: Try to parse line number from error message
        if error_message:
            line_from_error = nkParser.parse_error_line_from_message(str(error_message))
            if line_from_error:
                logger.debug(f"Found line {line_from_error} from error message")
                return (line_from_error, f"Error reported at line {line_from_error}")

        # Strategy 2 & 3: Compare nodes
        try:
            # Parse all nodes from the script
            script_nodes = nkParser.parse_nk_script(script_text)
            if not script_nodes:
                logger.warning("No nodes found in script")
                return (1, "Could not parse script nodes")

            # Get current nodes in Nuke
            current_nodes = self._get_existing_node_names()

            # If we have nodes_before_paste, find newly created nodes
            if nodes_before_paste is not None:
                new_nodes = current_nodes - nodes_before_paste
                logger.debug(f"New nodes created: {new_nodes}")
            else:
                new_nodes = current_nodes

            # Find the first node that failed to load
            first_missing = nkParser.find_first_missing_node(script_nodes, current_nodes)
            if first_missing:
                logger.debug(f"First missing node: {first_missing}")
                return (first_missing.start_line,
                        f"Node '{first_missing.name}' ({first_missing.node_type}) failed to load")

            # Find the last node that was successfully loaded
            last_loaded = nkParser.find_last_matching_node(script_nodes, current_nodes)
            if last_loaded:
                # Error is likely right after the last loaded node
                error_line = last_loaded.end_line + 1
                logger.debug(f"Last loaded node: {last_loaded}, error at line {error_line}")
                return (error_line,
                        f"Error after node '{last_loaded.name}' (line {error_line})")

        except Exception as e:
            logger.error(f"Error during node comparison: {e}")

        # Fallback: return line 1
        return (1, "Could not determine error location")

    def _move_cursor_to_error_line(self, line_number, add_debug_point=False, error_info=None):
        """
        Move the cursor to a specific line number and optionally add a debug point.

        Args:
            line_number (int): The 1-based line number to move to
            add_debug_point (bool): Whether to add a breakpoint at this line
            error_info (str, optional): Description of the error to display

        Returns:
            int: The line number that was navigated to
        """
        if line_number is None or line_number < 1:
            line_number = 1

        # Ensure line number doesn't exceed document
        max_line = self.text_edit.document().blockCount()
        if line_number > max_line:
            line_number = max_line

        # Move cursor to the error line
        block = self.text_edit.document().findBlockByNumber(line_number - 1)
        if block.isValid():
            cursor = self.text_edit.textCursor()
            cursor.setPosition(block.position())
            self.text_edit.setTextCursor(cursor)
            self.text_edit.centerCursor()
            self.text_edit.setFocus()

            if add_debug_point:
                self.text_edit.add_debug_point(line_number)
                self.text_edit.set_active_debug_point(line_number)

            logger.info(f"Cursor moved to line {line_number}")

        return line_number


    def _paste_plain_text(self, script, clean_nodegraph=False):
        """
        Paste the given plain text script into Nuke.

        If an error occurs during paste, this method will detect the error location
        and move the cursor to the problematic line, adding a debug point for easy
        navigation.

        Args:
            script (str): Nuke script as plain text.
            clean_nodegraph (bool): Whether to clear the current node graph before pasting.

        Notes:
            This method uses the %clipboard% to paste the text. It makes a backup
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

            # Get nodes before paste for comparison
            nodes_before = self._get_existing_node_names()

            if clean_nodegraph:
                for node in nuke.allNodes(recurseGroups=False):
                    nuke.delete(node)
                nodes_before = set()  # Reset since we cleared

            # Load clipboard in Nuke
            paste_error = None
            try:
                nuke.nodePaste("%clipboard%")
                # Clear any previous error markers on successful paste
                self.text_edit.clear_error_line()
            except Exception as e:
                paste_error = e
                logger.error(f"Error on script paste: {e}")

            # Restore backup
            clipboard.setMimeData(backup)

            # Handle paste error - detect and navigate to error line
            if paste_error:
                self._handle_paste_error(script, paste_error, nodes_before)

        except Exception as e:
            msg = f"Error pasting node graph: {e}"
            logger.error(msg)
            nuke.message(msg)

    def _handle_paste_error(self, script, error, nodes_before_paste):
        """
        Handle a paste error by detecting and navigating to the error location.

        Args:
            script (str): The script that was being pasted
            error (Exception): The exception that occurred
            nodes_before_paste (set[str]): Node names that existed before paste
        """
        # Detect the error line
        error_line, error_info = self._detect_error_line(
            script,
            error_message=str(error),
            nodes_before_paste=nodes_before_paste
        )

        # Set error line marker for visual feedback
        self.text_edit.set_error_line(error_line)

        # Move cursor to error line and add debug point
        self._move_cursor_to_error_line(
            error_line,
            add_debug_point=True,
            error_info=error_info
        )

        # Show user message with error details
        msg = f"Script paste failed.\n\n{error_info}\n\nCursor moved to line {error_line}.\n\nOriginal error: {error}"
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

    def validate_script(self, show_success_message=True):
        """
        Validate the current script structure and display results.

        Checks for:
        - Unmatched braces (unclosed or extra closing braces)
        - Malformed node definitions
        - Duplicate node names

        Args:
            show_success_message (bool): Whether to show a message when no errors found

        Note:
            This method is kept for backward compatibility and manual validation.
            Auto-validation is now handled by _run_validation_silent().
        """
        current_text = self.text_edit.toPlainText()
        if not current_text.strip():
            self.text_edit.clear_validation_errors()
            self.error_count = 0
            self.warning_count = 0
            self.node_count = 0
            self._update_status_bar()
            return

        # Run validation
        errors = self.text_edit.validate_structure()
        error_count, warning_count = self.text_edit.get_validation_error_count()

        # Count nodes
        nodes = nkParser.parse_nk_script(current_text)
        self.node_count = len(nodes)

        # Update counters
        self.error_count = error_count
        self.warning_count = warning_count

        # Update status bar
        self._update_status_bar()

        # Log and optionally show message
        if error_count > 0 or warning_count > 0:
            status_parts = []
            if error_count > 0:
                status_parts.append(f"{error_count} error{'s' if error_count > 1 else ''}")
            if warning_count > 0:
                status_parts.append(f"{warning_count} warning{'s' if warning_count > 1 else ''}")
            status_text = ", ".join(status_parts)
            logger.info(f"Validation: {status_text}")
        else:
            if show_success_message:
                nuke.message("Script structure is valid.\n\nNo errors found.")
            logger.info("Validation: No errors found")

    def _on_text_changed(self):
        """
        Restart validation timer on text change.

        Implements debounced auto-validation: validation only runs after 500ms
        of no typing activity.
        """
        self.validation_timer.stop()
        self.validation_timer.start()
        self.total_lines = self.text_edit.document().blockCount()
        self._update_status_bar()

    def _on_validation_timer(self):
        """
        Run validation when timer expires (500ms after last text change).

        Performs validation silently without showing success messages.
        """
        current_text = self.text_edit.toPlainText()
        if current_text.strip():
            self._run_validation_silent()
        else:
            self.text_edit.clear_validation_errors()
            self.error_count = 0
            self.warning_count = 0
            self.node_count = 0
            self._update_status_bar()

    def _run_validation_silent(self):
        """
        Run validation without user messages.

        Updates error/warning counts and node count, then refreshes the status bar.
        """
        current_text = self.text_edit.toPlainText()

        # Run structure validation
        errors = self.text_edit.validate_structure()
        error_count, warning_count = self.text_edit.get_validation_error_count()

        # Count nodes using parser
        nodes = nkParser.parse_nk_script(current_text)
        self.node_count = len(nodes)

        # Update counters
        self.error_count = error_count
        self.warning_count = warning_count

        # Update status bar display
        self._update_status_bar()

        logger.debug(f"Auto-validation: {error_count} errors, {warning_count} warnings, {self.node_count} nodes")

    def _update_cursor_position(self):
        """
        Update the current cursor position (line and column).

        Called whenever the cursor moves in the text editor.
        Updates the line/position display in the status bar.
        """
        cursor = self.text_edit.textCursor()

        # Get line number (1-based)
        self.current_line = cursor.blockNumber() + 1

        # Get column number (1-based)
        self.current_column = cursor.columnNumber() + 1

        # Update total lines
        self.total_lines = self.text_edit.document().blockCount()

        # Update status bar
        self._update_status_bar()

    def _update_status_bar(self):
        """
        Update all status bar labels with current counts and position.

        Updates:
        - Error counter (red if > 0, gray otherwise)
        - Warning counter (orange if > 0, gray otherwise)
        - Line/position display (always visible)
        - Node counter (always visible)
        """
        # Update error counter
        error_text = f"⚠ {self.error_count} error{'s' if self.error_count != 1 else ''}"
        if self.error_count > 0:
            self.error_counter_label.setStyleSheet("color: #ff5050; font-weight: bold; padding: 2px 8px;")
        else:
            self.error_counter_label.setStyleSheet("color: gray; padding: 2px 8px;")
        self.error_counter_label.setText(error_text)

        # Update warning counter
        warning_text = f"⚠ {self.warning_count} warning{'s' if self.warning_count != 1 else ''}"
        if self.warning_count > 0:
            self.warning_counter_label.setStyleSheet("color: #dca030; font-weight: bold; padding: 2px 8px;")
        else:
            self.warning_counter_label.setStyleSheet("color: gray; padding: 2px 8px;")
        self.warning_counter_label.setText(warning_text)

        # Update line/position counter
        position_text = f"Ln {self.current_line}, Col {self.current_column} | {self.total_lines} lines"
        self.line_position_label.setText(position_text)

        # Update node counter
        node_text = f"{self.node_count} node{'s' if self.node_count != 1 else ''}"
        self.node_counter_label.setText(node_text)
