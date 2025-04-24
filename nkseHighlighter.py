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

        if hasattr(QtCore, 'QRegularExpression'):  # PySide6
            self._qRe_class = QtCore.QRegularExpression
        else:
            self._qRe_class = QtCore.QRegExp
        self.highlighting_rules = []

        # 5. Node Type
        self.node_name_format = QtGui.QTextCharFormat()
        self.node_name_format.setForeground(QtGui.QColor(255, 200, 150))
        self.node_name_format.setFontWeight(QtGui.QFont.Bold)
        self.node_name_pattern = r"^\s*([a-zA-Z0-9_]+)\s\{$"
        self.highlighting_rules.append((self._qRe_class(self.node_name_pattern), self.node_name_format))

        # Flags highlight
        self.plus_format = QtGui.QTextCharFormat()
        self.plus_format.setForeground(QtGui.QColor(120, 180, 255))
        self.flags_pattern = r"\s([\+\-])([A-Z]+)"
        self.highlighting_rules.append((self._qRe_class(self.flags_pattern), self.plus_format))

        # 2. Add user knobs lines
        self.adduser_format = QtGui.QTextCharFormat()
        self.adduser_format.setForeground(QtGui.QColor(240, 220, 160))  # Crema más suave que amarillo
        self.adduser_number_format = QtGui.QTextCharFormat()
        self.adduser_number_format.setForeground(QtGui.QColor(220, 220, 160))  # Crema más suave que amarillo
        self.adduser_name_format = QtGui.QTextCharFormat()
        self.adduser_name_format.setForeground(QtGui.QColor(220, 220, 160))  # Crema más suave que amarillo
        self.userknob_pattern = r"^\s*(addUserKnob)\s\{([0-9]+)(?:\s([a-zA-Z0-9_]+))?"
        self.highlighting_rules.append((self._qRe_class(self.userknob_pattern), self.adduser_format))

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
        self.highlighting_rules.append((self._qRe_class(self.knob_pattern), self.knob_format))

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
        self.highlighting_rules.append((self._qRe_class(self.callback_pattern), self.callback_format))

        # Invalid characters (non-ASCII visible) -> red
        self.invalid_char_format = QtGui.QTextCharFormat()
        self.invalid_char_format.setForeground(QtGui.QColor(255, 60, 60))
        self.invalid_char_pattern = r"[^\x20-\x7E\t\r\n]"
        self.highlighting_rules.append((self._qRe_class(self.invalid_char_pattern), self.invalid_char_format))


    def set_format(self, text, pattern, index, fmt):
        if pattern:
            try:
                start = text.index(pattern, index)
                self.setFormat(start, len(pattern), fmt)
            except ValueError:
                pass

    def highlightBlock(self, text):
        for pattern, fmt in self.highlighting_rules:
            # Qt6: QRegularExpression
            if hasattr(pattern, 'globalMatch'):
                it = pattern.globalMatch(text)
                while it.hasNext():
                    match = it.next()
                    pat = pattern.pattern()

                    if pat == self.node_name_pattern:
                        start = match.capturedStart(1)
                        length = match.capturedLength(1)
                        if start >= 0:
                            self.setFormat(start, length, fmt)

                    elif pat == self.flags_pattern:
                        start = match.capturedStart(1)
                        length = match.capturedLength(1) + match.capturedLength(2)
                        if start >= 0:
                            self.setFormat(start, length, fmt)

                    elif pat == self.userknob_pattern:
                        # grupos: (1)=addUserKnob, (2)=knob_number, (3)=knob_name
                        for grp, grp_fmt in (
                            (1, fmt),
                            (2, self.adduser_number_format),
                            (3, self.adduser_name_format),
                        ):
                            s = match.capturedStart(grp)
                            l = match.capturedLength(grp)
                            if s >= 0:
                                self.setFormat(s, l, grp_fmt)

                    elif pat == self.knob_pattern:
                        name = match.captured(1)
                        if name == "name":
                            s1 = match.capturedStart(1)
                            l1 = match.capturedLength(1)
                            s2 = match.capturedStart(2)
                            l2 = match.capturedLength(2)
                            self.setFormat(s1, l1, self.knob_name_format)
                            self.setFormat(s2, l2, self.node_name_format)
                        else:
                            s = match.capturedStart(1)
                            l = match.capturedLength(1)
                            if s >= 0:
                                self.setFormat(s, l, fmt)

                    else:
                        # resaltado completo del match
                        s0 = match.capturedStart(0)
                        l0 = match.capturedLength(0)
                        if s0 >= 0:
                            self.setFormat(s0, l0, fmt)

            # Qt5: QRegExp
            else:
                index = pattern.indexIn(text)
                while index >= 0:
                    length = pattern.matchedLength()
                    pat = pattern.pattern()

                    if pat == self.node_name_pattern:
                        cap = pattern.cap(1)
                        if cap:
                            try:
                                start = text.index(cap, index)
                                self.setFormat(start, len(cap), fmt)
                            except ValueError:
                                pass

                    elif pat == self.flags_pattern:
                        pre = pattern.cap(1)
                        flag = pattern.cap(2)
                        if pre and flag:
                            try:
                                start = text.index(pre, index)
                                self.setFormat(start, len(pre) + len(flag), fmt)
                            except ValueError:
                                pass

                    elif pat == self.userknob_pattern:
                        a = pattern.cap(1)
                        num = pattern.cap(2)
                        nm = pattern.cap(3)
                        self.set_format(text, a, index, fmt)
                        self.set_format(text, num, index, self.adduser_number_format)
                        self.set_format(text, nm, index, self.adduser_name_format)

                    elif pat == self.knob_pattern:
                        nm = pattern.cap(1)
                        if nm == "name":
                            nn = pattern.cap(2)
                            self.set_format(text, nm, index, self.knob_name_format)
                            self.set_format(text, nn, index, self.node_name_format)
                        else:
                            self.set_format(text, nm, index, fmt)

                    else:
                        self.setFormat(index, length, fmt)

                    index = pattern.indexIn(text, index + length)
