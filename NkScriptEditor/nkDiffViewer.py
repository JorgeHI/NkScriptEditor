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
"""
Diff viewer for comparing two .nk scripts side-by-side.

This module provides a dialog for comparing two Nuke scripts with
visual highlighting of additions, deletions, and modifications.
"""
import difflib
import os

import nuke
from NkScriptEditor import nkUtils
from NkScriptEditor import nkConstants

logger = nkUtils.getLogger(__name__)

if nuke.NUKE_VERSION_MAJOR < 11:
    from PySide import QtWidgets, QtGui, QtCore
elif nuke.NUKE_VERSION_MAJOR < 16:
    from PySide2 import QtWidgets, QtGui, QtCore
else:
    from PySide6 import QtWidgets, QtGui, QtCore


class DiffLineNumberArea(QtWidgets.QWidget):
    """Widget to display line numbers for the diff text editors."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class DiffTextEdit(QtWidgets.QPlainTextEdit):
    """
    Custom text editor for displaying diff content with line numbers.

    Shows additions in green, deletions in red, and modifications in yellow.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)

        # Line number area
        self.line_number_area = DiffLineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.update_line_number_area_width(0)

        # Track line types for coloring: 'add', 'del', 'mod', 'equal', 'empty'
        self.line_types = []

        # Font setup
        font = QtGui.QFont("Courier New", 10)
        font.setStyleHint(QtGui.QFont.Monospace)
        self.setFont(font)

        # Colors for diff highlighting (from centralized constants)
        self.colors = {
            'add': QtGui.QColor(*nkConstants.colors.diff_add),
            'del': QtGui.QColor(*nkConstants.colors.diff_del),
            'mod': QtGui.QColor(*nkConstants.colors.diff_mod),
            'equal': QtGui.QColor(*nkConstants.colors.diff_equal),
            'empty': QtGui.QColor(*nkConstants.colors.diff_empty),
        }

    def line_number_area_width(self):
        """Calculate width needed for line number area."""
        digits = len(str(max(1, self.blockCount())))
        if hasattr(self.fontMetrics(), 'horizontalAdvance'):
            space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        else:
            space = 10 + self.fontMetrics().width('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(),
                                         self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QtCore.QRect(cr.left(), cr.top(),
                         self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        """Paint line numbers with background colors based on line type."""
        painter = QtGui.QPainter(self.line_number_area)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                # Get line type for coloring
                line_type = 'equal'
                if block_number < len(self.line_types):
                    line_type = self.line_types[block_number]

                # Draw background
                bg_color = self.colors.get(line_type, self.colors['equal'])
                painter.fillRect(0, int(top), self.line_number_area.width(),
                                 int(self.fontMetrics().height()), bg_color)

                # Draw line number
                number = str(block_number + 1)
                painter.setPen(QtGui.QColor(*nkConstants.colors.diff_line_number))
                painter.drawText(0, int(top), self.line_number_area.width() - 5,
                                 self.fontMetrics().height(),
                                 QtCore.Qt.AlignRight, number)

            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def set_content_with_types(self, lines, line_types):
        """
        Set the content and line types for highlighting.

        Args:
            lines (list[str]): The lines of text to display
            line_types (list[str]): The type of each line ('add', 'del', 'mod', 'equal', 'empty')
        """
        self.line_types = line_types
        self.setPlainText('\n'.join(lines))
        self.highlight_lines()

    def highlight_lines(self):
        """Apply background highlighting to lines based on their type."""
        extra_selections = []

        block = self.document().firstBlock()
        line_num = 0

        while block.isValid():
            if line_num < len(self.line_types):
                line_type = self.line_types[line_num]
                if line_type != 'equal':
                    selection = QtWidgets.QTextEdit.ExtraSelection()
                    selection.format.setBackground(self.colors.get(line_type, self.colors['equal']))
                    selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
                    selection.cursor = QtGui.QTextCursor(block)
                    selection.cursor.clearSelection()
                    extra_selections.append(selection)

            block = block.next()
            line_num += 1

        self.setExtraSelections(extra_selections)


class DiffViewer(QtWidgets.QDialog):
    """
    Dialog for comparing two .nk scripts side-by-side.

    Displays differences with color highlighting:
    - Green: Added lines
    - Red: Deleted lines
    - Yellow: Modified lines
    """

    def __init__(self, parent=None, left_text="", left_title="Current Script",
                 right_text="", right_title="Compare Script"):
        super().__init__(parent)
        self.setWindowTitle("Script Comparison")
        self.setMinimumSize(1200, 700)

        self.left_text = left_text
        self.right_text = right_text
        self.diff_positions = []  # Line numbers with differences
        self.current_diff_index = -1

        self._setup_ui(left_title, right_title)
        self._connect_signals()

        if left_text and right_text:
            self.compute_diff()

    def _setup_ui(self, left_title, right_title):
        """Set up the dialog UI."""
        layout = QtWidgets.QVBoxLayout(self)

        # -- Top toolbar
        toolbar = QtWidgets.QHBoxLayout()

        # Left file selector
        self.left_label = QtWidgets.QLabel(left_title)
        self.left_label.setStyleSheet("font-weight: bold;")

        # Right file selector
        self.right_label = QtWidgets.QLabel(right_title)
        self.right_label.setStyleSheet("font-weight: bold;")
        self.browse_right_btn = QtWidgets.QPushButton("Browse...")
        self.browse_right_btn.clicked.connect(self.browse_compare_file)

        # Navigation buttons
        self.prev_diff_btn = QtWidgets.QPushButton("< Prev Diff")
        self.next_diff_btn = QtWidgets.QPushButton("Next Diff >")
        self.diff_counter_label = QtWidgets.QLabel("0 / 0")

        toolbar.addWidget(self.left_label)
        toolbar.addStretch()
        toolbar.addWidget(self.prev_diff_btn)
        toolbar.addWidget(self.diff_counter_label)
        toolbar.addWidget(self.next_diff_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.right_label)
        toolbar.addWidget(self.browse_right_btn)

        layout.addLayout(toolbar)

        # -- Diff view splitter
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # Left editor (original/current)
        left_container = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_editor = DiffTextEdit()
        left_layout.addWidget(self.left_editor)
        splitter.addWidget(left_container)

        # Right editor (compare)
        right_container = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_editor = DiffTextEdit()
        right_layout.addWidget(self.right_editor)
        splitter.addWidget(right_container)

        # Equal split
        splitter.setSizes([600, 600])

        layout.addWidget(splitter)

        # -- Legend
        legend_layout = QtWidgets.QHBoxLayout()
        legend_layout.addStretch()

        for label_text, color in [("Added", "#285028"), ("Deleted", "#642828"),
                                  ("Modified", "#5a5028")]:
            indicator = QtWidgets.QLabel("  ")
            indicator.setStyleSheet(f"background-color: {color}; border: 1px solid #555;")
            indicator.setFixedSize(20, 16)
            legend_layout.addWidget(indicator)
            legend_layout.addWidget(QtWidgets.QLabel(label_text))
            legend_layout.addSpacing(20)

        legend_layout.addStretch()
        layout.addLayout(legend_layout)

        # -- Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _connect_signals(self):
        """Connect signals for synchronized scrolling and navigation."""
        # Sync scrolling between editors
        self.left_editor.verticalScrollBar().valueChanged.connect(
            self.right_editor.verticalScrollBar().setValue)
        self.right_editor.verticalScrollBar().valueChanged.connect(
            self.left_editor.verticalScrollBar().setValue)

        # Horizontal scroll sync
        self.left_editor.horizontalScrollBar().valueChanged.connect(
            self.right_editor.horizontalScrollBar().setValue)
        self.right_editor.horizontalScrollBar().valueChanged.connect(
            self.left_editor.horizontalScrollBar().setValue)

        # Navigation buttons
        self.prev_diff_btn.clicked.connect(self.go_to_prev_diff)
        self.next_diff_btn.clicked.connect(self.go_to_next_diff)

    def browse_compare_file(self):
        """Open file browser to select a file to compare against."""
        file_path = nuke.getFilename('Select a .nk file to compare', '*.nk')
        if file_path and os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.right_text = f.read()
                self.right_label.setText(os.path.basename(file_path))
                self.compute_diff()
            except Exception as e:
                logger.error(f"Error loading compare file: {e}")
                nuke.message(f"Error loading file:\n{e}")

    def compute_diff(self):
        """Compute and display the diff between left and right texts."""
        left_lines = self.left_text.splitlines()
        right_lines = self.right_text.splitlines()

        # Use SequenceMatcher for detailed comparison
        matcher = difflib.SequenceMatcher(None, left_lines, right_lines)

        left_result = []
        left_types = []
        right_result = []
        right_types = []
        self.diff_positions = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for line in left_lines[i1:i2]:
                    left_result.append(line)
                    left_types.append('equal')
                for line in right_lines[j1:j2]:
                    right_result.append(line)
                    right_types.append('equal')

            elif tag == 'replace':
                # Modified lines - show both versions
                left_count = i2 - i1
                right_count = j2 - j1
                max_count = max(left_count, right_count)

                self.diff_positions.append(len(left_result))

                for idx in range(max_count):
                    if idx < left_count:
                        left_result.append(left_lines[i1 + idx])
                        left_types.append('mod')
                    else:
                        left_result.append('')
                        left_types.append('empty')

                    if idx < right_count:
                        right_result.append(right_lines[j1 + idx])
                        right_types.append('mod')
                    else:
                        right_result.append('')
                        right_types.append('empty')

            elif tag == 'delete':
                # Lines only in left (deleted from right)
                self.diff_positions.append(len(left_result))
                for line in left_lines[i1:i2]:
                    left_result.append(line)
                    left_types.append('del')
                    right_result.append('')
                    right_types.append('empty')

            elif tag == 'insert':
                # Lines only in right (added)
                self.diff_positions.append(len(left_result))
                for line in right_lines[j1:j2]:
                    left_result.append('')
                    left_types.append('empty')
                    right_result.append(line)
                    right_types.append('add')

        # Set content in editors
        self.left_editor.set_content_with_types(left_result, left_types)
        self.right_editor.set_content_with_types(right_result, right_types)

        # Update diff counter
        self.current_diff_index = -1
        self._update_diff_counter()

        logger.debug(f"Diff computed: {len(self.diff_positions)} differences found")

    def _update_diff_counter(self):
        """Update the diff counter label."""
        total = len(self.diff_positions)
        current = self.current_diff_index + 1 if self.current_diff_index >= 0 else 0
        self.diff_counter_label.setText(f"{current} / {total}")

    def go_to_next_diff(self):
        """Navigate to the next difference."""
        if not self.diff_positions:
            return

        self.current_diff_index += 1
        if self.current_diff_index >= len(self.diff_positions):
            self.current_diff_index = 0

        self._scroll_to_diff(self.current_diff_index)
        self._update_diff_counter()

    def go_to_prev_diff(self):
        """Navigate to the previous difference."""
        if not self.diff_positions:
            return

        self.current_diff_index -= 1
        if self.current_diff_index < 0:
            self.current_diff_index = len(self.diff_positions) - 1

        self._scroll_to_diff(self.current_diff_index)
        self._update_diff_counter()

    def _scroll_to_diff(self, index):
        """Scroll both editors to show the diff at the given index."""
        if index < 0 or index >= len(self.diff_positions):
            return

        line_num = self.diff_positions[index]

        # Move cursor to the diff line
        block = self.left_editor.document().findBlockByNumber(line_num)
        if block.isValid():
            cursor = QtGui.QTextCursor(block)
            self.left_editor.setTextCursor(cursor)
            self.left_editor.centerCursor()

    def set_texts(self, left_text, right_text, left_title="Current Script",
                  right_title="Compare Script"):
        """
        Set the texts to compare.

        Args:
            left_text (str): The left/original text
            right_text (str): The right/compare text
            left_title (str): Title for the left panel
            right_title (str): Title for the right panel
        """
        self.left_text = left_text
        self.right_text = right_text
        self.left_label.setText(left_title)
        self.right_label.setText(right_title)

        if left_text and right_text:
            self.compute_diff()


def show_diff_dialog(parent, current_text, current_title="Current Script"):
    """
    Show the diff dialog to compare the current script with another file.

    Args:
        parent: Parent widget
        current_text (str): The current script text from the editor
        current_title (str): Title for the current script

    Returns:
        DiffViewer: The dialog instance
    """
    dialog = DiffViewer(parent, left_text=current_text, left_title=current_title)
    dialog.show()
    return dialog
