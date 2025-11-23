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
from NkScriptEditor import nkUtils
from NkScriptEditor import nkValidator
# Create logger
logger = nkUtils.getLogger(__name__)

import nuke
if nuke.NUKE_VERSION_MAJOR < 11:
    # PySide for Nuke up to 10
    from PySide import QtWidgets, QtGui, QtCore
    pyside_version = 1
elif nuke.NUKE_VERSION_MAJOR < 16:
    # PySide2 for default Nuke 11
    from PySide2 import QtWidgets, QtGui, QtCore
    pyside_version = 2
else:
    # PySide6 for Nuke 16+
    from PySide6 import QtWidgets, QtGui, QtCore
    pyside_version = 6

import sys

class LineNumberArea(QtWidgets.QWidget):
    """
    Widget displayed to the left of the text editor to show line numbers and breakpoints.

    Clicking on a line number toggles a breakpoint. Active debug points are visually highlighted.
    """
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        """Return the preferred width of the line number area."""
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        """Delegate painting of line numbers to the parent CodeEditor."""
        self.code_editor.line_number_area_paint_event(event)

    def mousePressEvent(self, event):
        """
        Handle mouse clicks in the line number area.

        Clicking toggles breakpoints and updates the active debug point.
        """
        if event.button() == QtCore.Qt.LeftButton:
            editor = self.code_editor
            y = event.pos().y()

            block = editor.firstVisibleBlock()
            block_number = block.blockNumber()
            top = editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top()
            bottom = top + editor.blockBoundingRect(block).height()

            while block.isValid() and top <= y:
                if block.isVisible() and bottom >= y:
                    line = block_number + 1
                    if line in editor.breakpoint_lines:
                        editor.breakpoint_lines.remove(line)
                        if editor.active_debug_point == line:
                            editor.active_debug_point = None
                    else:
                        editor.breakpoint_lines.add(line)
                    self.update()
                    break
                block = block.next()
                top = bottom
                bottom = top + editor.blockBoundingRect(block).height()
                block_number += 1


class CodeEditor(QtWidgets.QPlainTextEdit):
    """
    Custom text editor for displaying and editing Nuke .nk scripts with debugging support.

    Features:
    - Line numbers and breakpoint display
    - Highlighting of the current line and active debug line
    - Error line highlighting for failed script loads
    - Structure validation with error markers and underlines
    - Cursor navigation to breakpoints
    - Automatic update of breakpoint positions when editing
    """
    def __init__(self):
        super().__init__()
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.breakpoint_lines = set()
        self.active_debug_point = None
        self.error_line = None  # Line with detected error (from paste failure)
        self.validation_errors = {}  # Dict of line_number -> list[StructureError]
        self.update_line_number_area_width(0)
        self.highlight_current_line()

        self._last_text = self.toPlainText()
        self.document().contentsChange.connect(self._on_contents_change)

        # Enable mouse tracking for tooltips
        self.setMouseTracking(True)
        self.line_number_area.setMouseTracking(True)

    def line_number_area_width(self):
        """Calculate and return the width required for the line number area.

        Returns:
            int: Width in pixels required for the line number display, with extra space
                 for the breakpoint indicator.
        """
        digits = len(str(max(1, self.blockCount())))
        if pyside_version < 6:
            space = 3 + self.fontMetrics().width('9') * digits
        else:
            space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space + 20  # Extra space for breakpoint indicator

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            #self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
            r = QtCore.QRect(0, rect.y(), self.line_number_area.width(), rect.height())
            self.line_number_area.update(r)
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QtCore.QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QtGui.QPainter(self.line_number_area)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line_num = block_number + 1

                # Check for validation errors on this line
                has_validation_error = line_num in self.validation_errors
                has_error_severity = False
                if has_validation_error:
                    has_error_severity = any(
                        e.severity == nkValidator.StructureError.ERROR
                        for e in self.validation_errors[line_num]
                    )

                # Highlight error line with a red tint (highest priority - paste errors)
                if line_num == self.error_line:
                    painter.fillRect(0, int(top), self.line_number_area.width(),
                                     int(self.fontMetrics().height()), QtGui.QColor(120, 40, 40))
                # Highlight validation errors (structure errors)
                elif has_validation_error and has_error_severity:
                    painter.fillRect(0, int(top), self.line_number_area.width(),
                                     int(self.fontMetrics().height()), QtGui.QColor(100, 50, 50))
                # Highlight active debug point line with a soft yellow
                elif line_num == self.active_debug_point:
                    painter.fillRect(0, int(top), self.line_number_area.width(),
                                     int(self.fontMetrics().height()), QtGui.QColor(90, 90, 50))
                # Highlight validation warnings
                elif has_validation_error:
                    painter.fillRect(0, int(top), self.line_number_area.width(),
                                     int(self.fontMetrics().height()), QtGui.QColor(90, 70, 30))

                number = str(line_num)
                painter.setPen(QtCore.Qt.black)
                painter.drawText(0, int(top), self.line_number_area.width() - 5, self.fontMetrics().height(),
                                 QtCore.Qt.AlignRight, number)

                # Draw error marker (X icon) - highest priority (paste error)
                if line_num == self.error_line:
                    center_x = 10
                    center_y = int(top) + self.fontMetrics().height() / 2
                    painter.setPen(QtGui.QPen(QtGui.QColor(255, 100, 100), 2))
                    size = 4
                    painter.drawLine(center_x - size, int(center_y) - size,
                                     center_x + size, int(center_y) + size)
                    painter.drawLine(center_x - size, int(center_y) + size,
                                     center_x + size, int(center_y) - size)
                # Draw validation error marker (! icon)
                elif has_validation_error and has_error_severity:
                    center_x = 10
                    center_y = int(top) + self.fontMetrics().height() / 2
                    painter.setPen(QtGui.QPen(QtGui.QColor(255, 80, 80), 2))
                    # Draw exclamation mark
                    painter.drawLine(center_x, int(center_y) - 5, center_x, int(center_y) + 1)
                    painter.drawPoint(center_x, int(center_y) + 4)
                # Draw validation warning marker (triangle)
                elif has_validation_error:
                    center_x = 10
                    center_y = int(top) + self.fontMetrics().height() / 2
                    painter.setPen(QtGui.QPen(QtGui.QColor(220, 180, 50), 2))
                    painter.setBrush(QtCore.Qt.NoBrush)
                    # Draw small triangle
                    points = [
                        QtCore.QPoint(center_x, int(center_y) - 5),
                        QtCore.QPoint(center_x - 5, int(center_y) + 4),
                        QtCore.QPoint(center_x + 5, int(center_y) + 4),
                    ]
                    painter.drawPolygon(points)
                # Draw breakpoint (red circle)
                elif line_num in self.breakpoint_lines:
                    radius = 5
                    center_x = 10
                    center_y = int(top) + self.fontMetrics().height() / 2
                    painter.setBrush(QtCore.Qt.red)
                    painter.setPen(QtCore.Qt.NoPen)
                    painter.drawEllipse(center_x - radius, int(center_y) - radius, 2 * radius, 2 * radius)

            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def highlight_current_line(self):
        extra_selections = []

        # Highlight error line with red background (highest priority - paste error)
        if self.error_line is not None:
            error_selection = QtWidgets.QTextEdit.ExtraSelection()
            error_color = QtGui.QColor(100, 30, 30)  # Dark red
            error_selection.format.setBackground(error_color)
            error_selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
            block = self.document().findBlockByNumber(self.error_line - 1)
            if block.isValid():
                error_selection.cursor = QtGui.QTextCursor(block)
                error_selection.cursor.clearSelection()
                extra_selections.append(error_selection)

        # Add underlines for validation errors
        for line_num, errors in self.validation_errors.items():
            block = self.document().findBlockByNumber(line_num - 1)
            if block.isValid():
                for err in errors:
                    selection = QtWidgets.QTextEdit.ExtraSelection()

                    # Set underline style based on severity
                    if err.severity == nkValidator.StructureError.ERROR:
                        selection.format.setUnderlineColor(QtGui.QColor(255, 80, 80))
                    else:
                        selection.format.setUnderlineColor(QtGui.QColor(220, 180, 50))

                    selection.format.setUnderlineStyle(QtGui.QTextCharFormat.WaveUnderline)

                    # Position cursor at error location
                    cursor = QtGui.QTextCursor(block)
                    cursor.movePosition(QtGui.QTextCursor.StartOfBlock)

                    # Move to error column
                    for _ in range(min(err.column, block.length() - 1)):
                        cursor.movePosition(QtGui.QTextCursor.Right)

                    # Select the error length (or rest of line if longer)
                    chars_to_select = min(err.length, block.length() - err.column - 1)
                    if chars_to_select < 1:
                        chars_to_select = max(1, block.length() - 1)
                    for _ in range(chars_to_select):
                        cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor)

                    selection.cursor = cursor
                    extra_selections.append(selection)

        # Highlight current cursor line
        if not self.isReadOnly():
            selection = QtWidgets.QTextEdit.ExtraSelection()
            line_color = QtGui.QColor(78, 78, 78)
            selection.format.setBackground(line_color)
            selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        self.setExtraSelections(extra_selections)

    def _on_contents_change(self, position, chars_removed, chars_added):
        """
        Called after any document edit:
          - position is the character offset where the change began
          - chars_removed is the number of characters removed
          - chars_added   is the number of characters inserted
        """
        # Keep a snapshot of the old text
        old_text = self._last_text
        new_text = self.toPlainText()

        # Extract the deleted and inserted substrings
        removed_text = old_text[position:position + chars_removed]
        added_text   = new_text[position:position + chars_added]

        # Count how many newline characters were removed or added
        removed_lines = removed_text.count('\n')
        added_lines   = added_text.count('\n')
        delta = added_lines - removed_lines

        # Only adjust breakpoints if the number of logical lines has changed
        if delta != 0:
            # Find which logical line the edit happened on
            block = self.document().findBlock(position)
            edit_line = block.blockNumber() + 2

            # Shift all breakpoints that are below the edit line
            updated_breakpoints = set()
            for bp in self.breakpoint_lines:
                if bp > edit_line:
                    updated_breakpoints.add(bp + delta)
                # If the breakpoint is in the current line remove it
                elif bp != edit_line:  # else, keep it
                    updated_breakpoints.add(bp)
            self.breakpoint_lines = updated_breakpoints

            # Adjust the active debug point as well
            if self.active_debug_point is not None:
                if self.active_debug_point > edit_line:
                    self.active_debug_point += delta
                elif self.active_debug_point == edit_line and removed_lines > 0:
                    # If the active line itself was deleted, clear it
                    self.active_debug_point = None

            # Force a repaint of the line-number gutter
            self.line_number_area.update()

        # Update our snapshot for the next edit
        self._last_text = new_text

    def add_debug_point(self, line):
        """Adds a debug point to the line given."""
        self.breakpoint_lines.add(line)
        logger.debug(f"Debug point {line} added.")

    def set_active_debug_point(self, line):
        """
        Sets the given line like active breakpoint if 
        that line have an existing breakpoint.
        """
        if line in self.breakpoint_lines:
            self.active_debug_point = line
            logger.debug(f"Debug point {line} set.")
        else:
            logger.error(f"The line {line} is not in the breakpoint line list. "
                         f"It can not be an active breakpoint.")

    def get_all_debug_points(self):
        """Return all currently defined debug points in sorted order.

        Returns:
            list[int]: A list of line numbers (1-based) that contain active debug points.
        """
        return sorted(self.breakpoint_lines)

    def clean_all_debug_points(self):
        """Clear all debug points and reset the active debug point.

        This method removes all breakpoints from the editor and clears any currently
        active debug point. It also triggers a visual update of the line number area.
        """
        self.breakpoint_lines.clear()
        self.active_debug_point = None
        self.line_number_area.update()
        logger.debug(f"Debug points removed.")

    def get_next_debug_point(self):
        """Return the next debug point after the active one, or the first if none is active.

        Returns:
            int or None: The next debug point's line number. If no debug points exist,
            or no next point is found, returns None.
        """
        points = sorted(self.breakpoint_lines)
        if not points:
            return None
        if self.active_debug_point is None:
            logger.debug(f"Next point found {points[0]}.")
            return points[0]
        for point in points:
            if point > self.active_debug_point:
                logger.debug(f"Next point found {point}.")
                return point
        return None  # No next point

    def get_prev_debug_point(self):
        """Return the previous debug point before the active one, or the last if none is active.

        Returns:
            int or None: The previous debug point's line number. If no debug points exist,
            or no previous point is found, returns None.
        """
        points = sorted(self.breakpoint_lines)
        if not points:
            return None
        if self.active_debug_point is None:
            logger.debug(f"Previous point found {points[-1]}.")
            return points[-1]
        for point in reversed(points):
            if point < self.active_debug_point:
                logger.debug(f"Previous point found {point}.")
                return point
        return None  # No previous point

    def get_text_until_debug_point(self):
        """Return all lines of text from the start until the active debug point (inclusive).

        Returns:
            str: A string containing the lines up to and including the active debug point.
                 Returns an empty string if no debug point is active.
        """
        if not self.active_debug_point:
            return ""
        lines = self.toPlainText().splitlines()
        return "\n".join(lines[:self.active_debug_point]) + "\n"

    def move_cursor_to_line(self, line_number):
        """Move cursor to the given line number (1-based)."""
        block = self.document().findBlockByNumber(line_number - 1)
        if block.isValid():
            cursor = QtGui.QTextCursor(block)
            self.setTextCursor(cursor)
            self.centerCursor()

    def set_error_line(self, line_number):
        """
        Set an error marker at the specified line.

        Args:
            line_number (int): The 1-based line number to mark as error
        """
        self.error_line = line_number
        self.line_number_area.update()
        self.highlight_current_line()  # Refresh highlighting
        logger.debug(f"Error line set to {line_number}")

    def clear_error_line(self):
        """Clear the error line marker."""
        self.error_line = None
        self.line_number_area.update()
        self.highlight_current_line()  # Refresh highlighting
        logger.debug("Error line cleared")

    def set_next_debug_point(self):
        """Set the active debug point to the next one and move the cursor to that line.

        If a next debug point exists after the current active one, this function sets
        it as the new active point and scrolls the editor to center that line.
        """
        next_point = self.get_next_debug_point()
        if next_point:
            self.active_debug_point = next_point
            self.move_cursor_to_line(next_point)
            self.line_number_area.update()

    def set_prev_debug_point(self):
        """Set the active debug point to the previous one and move the cursor to that line.

        If a previous debug point exists before the current active one, this function sets
        it as active and centers the editor view on it.
        """
        prev_point = self.get_prev_debug_point()
        if prev_point:
            self.active_debug_point = prev_point
            self.move_cursor_to_line(prev_point)
            self.line_number_area.update()

    # -------------------------------------------------------------------------
    # Validation Methods
    # -------------------------------------------------------------------------

    def validate_structure(self):
        """
        Run structure validation on the current script content.

        Validates brace matching and node definitions, updating the
        validation_errors dictionary and refreshing the display.

        Returns:
            list[StructureError]: List of errors found
        """
        script_text = self.toPlainText()
        errors = nkValidator.validate_script(script_text)
        self.validation_errors = nkValidator.get_errors_by_line(errors)

        # Refresh display
        self.line_number_area.update()
        self.highlight_current_line()

        logger.debug(f"Validation complete: {len(errors)} errors found")
        return errors

    def set_validation_errors(self, errors):
        """
        Set validation errors from an external source.

        Args:
            errors (list[StructureError]): List of validation errors
        """
        self.validation_errors = nkValidator.get_errors_by_line(errors)
        self.line_number_area.update()
        self.highlight_current_line()

    def clear_validation_errors(self):
        """Clear all validation errors."""
        self.validation_errors = {}
        self.line_number_area.update()
        self.highlight_current_line()
        logger.debug("Validation errors cleared")

    def get_validation_error_count(self):
        """
        Get the total count of validation errors.

        Returns:
            tuple: (error_count, warning_count)
        """
        error_count = 0
        warning_count = 0
        for errors in self.validation_errors.values():
            for err in errors:
                if err.severity == nkValidator.StructureError.ERROR:
                    error_count += 1
                else:
                    warning_count += 1
        return error_count, warning_count

    def get_error_at_line(self, line_number):
        """
        Get validation errors at a specific line.

        Args:
            line_number (int): 1-based line number

        Returns:
            list[StructureError]: List of errors at that line, empty if none
        """
        return self.validation_errors.get(line_number, [])

    def event(self, event):
        """Handle events including tooltips for validation errors."""
        if event.type() == QtCore.QEvent.ToolTip:
            # Get position in document
            pos = event.pos()
            cursor = self.cursorForPosition(pos)
            line_num = cursor.blockNumber() + 1

            # Check for validation errors on this line
            errors = self.get_error_at_line(line_num)
            if errors:
                # Build tooltip text from all errors on this line
                tooltip_lines = []
                for err in errors:
                    severity = "Error" if err.severity == nkValidator.StructureError.ERROR else "Warning"
                    tooltip_lines.append(f"[{severity}] {err.message}")
                tooltip_text = "\n".join(tooltip_lines)
                QtWidgets.QToolTip.showText(event.globalPos(), tooltip_text, self)
                return True
            else:
                QtWidgets.QToolTip.hideText()

        return super().event(event)
