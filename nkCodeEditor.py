from PySide2 import QtWidgets, QtGui, QtCore
import sys

class LineNumberArea(QtWidgets.QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)

class CodeEditor(QtWidgets.QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.breakpoint_lines = set()
        self.update_line_number_area_width(0)
        self.highlight_current_line()

    def line_number_area_width(self):
        digits = len(str(max(1, self.blockCount())))
        space = 3 + self.fontMetrics().width('9') * digits
        return space + 20  # Extra space for breakpoint indicator

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QtCore.QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QtGui.QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QtCore.Qt.lightGray)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QtCore.Qt.black)
                painter.drawText(0, int(top), self.line_number_area.width() - 5, self.fontMetrics().height(),
                                 QtCore.Qt.AlignRight, number)

                # Dibujar breakpoint si existe
                if (block_number + 1) in self.breakpoint_lines:
                    radius = 5
                    center_x = 10
                    center_y = int(top) + self.fontMetrics().height() / 2
                    painter.setBrush(QtCore.Qt.red)
                    painter.drawEllipse(center_x - radius, center_y - radius, 2 * radius, 2 * radius)

            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            x = event.pos().x()
            if x < self.line_number_area_width():
                block = self.firstVisibleBlock()
                top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
                bottom = top + self.blockBoundingRect(block).height()
                y = event.pos().y()
                while block.isValid() and top <= y:
                    if block.isVisible() and bottom >= y:
                        line = block.blockNumber() + 1
                        if line in self.breakpoint_lines:
                            self.breakpoint_lines.remove(line)
                        else:
                            self.breakpoint_lines.add(line)
                        self.line_number_area.update()
                        break
                    block = block.next()
                    top = bottom
                    bottom = top + self.blockBoundingRect(block).height()
        super().mousePressEvent(event)

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QtWidgets.QTextEdit.ExtraSelection()
            line_color = QtGui.QColor(QtCore.Qt.yellow).lighter(160)
            selection.format.setBackground(line_color)
            selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

