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
elif nuke.NUKE_VERSION_MAJOR < 16:
    # PySide2 for default Nuke 11
    from PySide2 import QtWidgets, QtGui, QtCore
else:
    # PySide6 for Nuke 16+
    from PySide6 import QtWidgets, QtGui, QtCore

class NkHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, document):
        super(NkHighlighter, self).__init__(document)

        self.highlighting_rules = []

        # 5. Node Type
        self.node_name_format = QtGui.QTextCharFormat()
        self.node_name_format.setForeground(QtGui.QColor(255, 200, 150))
        self.node_name_format.setFontWeight(QtGui.QFont.Bold)
        self.node_name_pattern = r"^\s*([a-zA-Z0-9_]+)\s\{$"
        self.highlighting_rules.append((QtCore.QRegExp(self.node_name_pattern), self.node_name_format))

        # Flags highlight
        self.plus_format = QtGui.QTextCharFormat()
        self.plus_format.setForeground(QtGui.QColor(120, 180, 255))
        self.flags_pattern = r"\s([\+\-])([A-Z]+)"
        self.highlighting_rules.append((QtCore.QRegExp(self.flags_pattern), self.plus_format))

        # 2. Add user knobs lines
        self.adduser_format = QtGui.QTextCharFormat()
        self.adduser_format.setForeground(QtGui.QColor(240, 220, 160))  # Crema más suave que amarillo
        self.adduser_number_format = QtGui.QTextCharFormat()
        self.adduser_number_format.setForeground(QtGui.QColor(220, 220, 160))  # Crema más suave que amarillo
        self.adduser_name_format = QtGui.QTextCharFormat()
        self.adduser_name_format.setForeground(QtGui.QColor(220, 220, 160))  # Crema más suave que amarillo
        self.userknob_pattern = r"^\s*(addUserKnob)\s\{([0-9]+)(?:\s([a-zA-Z0-9_]+))?"
        self.highlighting_rules.append((QtCore.QRegExp(self.userknob_pattern), self.adduser_format))

        # 3. Knob names on value set
        self.knob_format = QtGui.QTextCharFormat()
        self.knob_format.setForeground(QtGui.QColor(200, 160, 255))
        self.knob_name_format = QtGui.QTextCharFormat()
        self.knob_name_format.setForeground(QtGui.QColor(200, 160, 255))
        self.knob_name_format.setFontWeight(QtGui.QFont.Bold)
        self.node_name_format = QtGui.QTextCharFormat()
        self.node_name_format.setForeground(QtGui.QColor(255, 255, 255))
        self.node_name_format.setFontWeight(QtGui.QFont.Bold)
        self.knob_pattern = r"^\s*(?!addUserKnob\b)([a-zA-Z0-9_]+)\s([a-zA-Z0-9_\"\\\/\[\]\-]+)"
        self.highlighting_rules.append((QtCore.QRegExp(self.knob_pattern), self.knob_format))

        # 4. Callbacks
        self.callback_format = QtGui.QTextCharFormat()
        self.callback_format.setForeground(QtGui.QColor(128, 200, 255))  # Azul claro
        self.callback_format.setFontWeight(QtGui.QFont.Bold)
        self.callback_pattern = (
            r"^\s+(?:OnUserCreate|onCreate|onScriptLoad|onScriptSave|onScriptClose|"
            r"onDestroy|knobChanged|updateUI|autolabel|beforeRender|beforeFrameRender|"
            r"afterFrameRender|afterRender|afterBackgroundRender|afterBackgroundFrameRender|"
            r"filenameFilter|validateFilename|autoSaveFilter|autoSaveRestoreFilter)\s"
        )
        self.highlighting_rules.append((QtCore.QRegExp(self.callback_pattern), self.callback_format))

        # Invalid characters (non-ASCII visible) -> red
        self.invalid_char_format = QtGui.QTextCharFormat()
        self.invalid_char_format.setForeground(QtGui.QColor(255, 60, 60))
        self.invalid_char_pattern = r"[^\x20-\x7E\t\r\n]"
        self.highlighting_rules.append((QtCore.QRegExp(self.invalid_char_pattern), self.invalid_char_format))


    def set_format(self, text, pattern, index, fmt):
        if pattern:
            try:
                start = text.index(pattern, index)
                self.setFormat(start, len(pattern), fmt)
            except ValueError:
                pass

    def highlightBlock(self, text):
        for pattern, fmt in self.highlighting_rules:
            index = pattern.indexIn(text)
            while index >= 0:
                length = pattern.matchedLength()
                # Si es el patrón de knobs indentados, resaltar solo el grupo capturado
                pattern_re = pattern.pattern()
                if pattern_re == self.node_name_pattern: # Node Type
                    captured = pattern.cap(1)
                    if captured:
                        try:
                            start = text.index(captured, index)
                            self.setFormat(start, len(captured), fmt)
                        except ValueError:
                            pass
                elif pattern_re == self.flags_pattern: # Flags
                    preflag = pattern.cap(1)
                    flag = pattern.cap(2)
                    if preflag and flag:
                        try:
                            start = text.index(preflag, index)
                            self.setFormat(start, len(preflag) + len(flag), fmt)
                        except ValueError:
                            pass
                elif pattern_re == self.userknob_pattern:
                    addUserKnob = pattern.cap(1)
                    knob_number = pattern.cap(2)
                    knob_name = pattern.cap(3)
                    self.set_format(text, addUserKnob, index, fmt)
                    self.set_format(text, knob_number, index, self.adduser_number_format)
                    self.set_format(text, knob_name, index, self.adduser_name_format)
                elif pattern_re == self.knob_pattern:
                    knob_name = pattern.cap(1)
                    if knob_name == "name":
                        node_name = pattern.cap(2)
                        self.set_format(text, knob_name, index, self.knob_name_format)
                        self.set_format(text, node_name, index, self.node_name_format)
                    else:
                        self.set_format(text, knob_name, index, fmt)
                else:
                    self.setFormat(index, length, fmt)
                index = pattern.indexIn(text, index + length)