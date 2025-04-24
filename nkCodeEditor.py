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
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)

    def mousePressEvent(self, event):
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
    def __init__(self):
        super().__init__()
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.breakpoint_lines = set()
        self.active_debug_point = None
        self.update_line_number_area_width(0)
        self.highlight_current_line()

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

                # Highlight active debug point line with a soft yellow
                if line_num == self.active_debug_point:
                    painter.fillRect(0, int(top), self.line_number_area.width(), int(self.fontMetrics().height()), QtGui.QColor(90, 90, 50))

                number = str(line_num)
                painter.setPen(QtCore.Qt.black)
                painter.drawText(0, int(top), self.line_number_area.width() - 5, self.fontMetrics().height(),
                                 QtCore.Qt.AlignRight, number)

                # Draw breakpoint
                if line_num in self.breakpoint_lines:
                    radius = 5
                    center_x = 10
                    center_y = int(top) + self.fontMetrics().height() / 2
                    painter.setBrush(QtCore.Qt.red)
                    painter.drawEllipse(center_x - radius, center_y - radius, 2 * radius, 2 * radius)

            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QtWidgets.QTextEdit.ExtraSelection()
            line_color = QtGui.QColor(78, 78, 78)
            selection.format.setBackground(line_color)
            selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

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
            return points[0]
        for point in points:
            if point > self.active_debug_point:
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
            return points[-1]
        for point in reversed(points):
            if point < self.active_debug_point:
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
