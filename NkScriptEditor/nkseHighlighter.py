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
from NkScriptEditor import nkUtils
# Create logger
logger = nkUtils.getLogger(__name__)

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

        # Prepare default formats and patterns
        self.node_name_pattern = r"^\s*([a-zA-Z0-9_]+)\s\{$"
        self.flags_pattern = r"\s([\+\-])([A-Z]+)"
        self.userknob_pattern = r"^\s*(addUserKnob)\s\{([0-9]+)(?:\s([a-zA-Z0-9_]+))?"
        self.knob_pattern = r"^\s*(?!addUserKnob\b)([a-zA-Z0-9_]+)\s([a-zA-Z0-9_\"\\/\[\]\-]+)"
        self.callback_pattern = (
            r"^\s+(?:OnUserCreate|onCreate|onScriptLoad|onScriptSave|onScriptClose|"
            r"onDestroy|knobChanged|updateUI|autolabel|beforeRender|beforeFrameRender|"
            r"afterFrameRender|afterRender|afterBackgroundRender|afterBackgroundFrameRender|"
            r"filenameFilter|validateFilename|autoSaveFilter|autoSaveRestoreFilter)\s"
        )
        self.invalid_char_pattern = r"[^\x20-\x7E\t\r\n]"
        # Default QTextCharFormat setups
        self.formats = {
            'node_type':      self.make_format((255,200,150), bold=True),
            'node_name':      self.make_format((255,255,255), bold=True),
            'flag':           self.make_format((120,180,255)),
            'user_knob':      self.make_format((240,220,160)),
            'user_knob_num':  self.make_format((220,220,160)),
            'user_knob_name': self.make_format((220,220,160)),
            'knob':           self.make_format((200,160,255)),
            'callback':       self.make_format((128,200,255), bold=True),
            'invalid':        self.make_format((255,60,60)),
        }

        # Build initial rules list
        self._build_highlighting_rules()

    def make_format(self, color, bold=False):
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(QtGui.QColor(*color))
        if bold:
            fmt.setFontWeight(QtGui.QFont.Bold)
        return fmt

    def _build_highlighting_rules(self):
        """
        Internal: constructs the highlighting_rules list from patterns and current formats.
        """
        self.highlighting_rules = [
            (self._qRe_class(self.node_name_pattern), self.formats['node_type']),
            (self._qRe_class(self.flags_pattern), self.formats['flag']),
            (self._qRe_class(self.userknob_pattern), self.formats['user_knob']),
            (self._qRe_class(self.knob_pattern), self.formats['knob']),
            (self._qRe_class(self.callback_pattern), self.formats['callback']),
            (self._qRe_class(self.invalid_char_pattern), self.formats['invalid']),
        ]

    def update_formats(self, new_formats):
        """
        Update text formats for each attribute and rebuild highlighting rules.

        Args:
            new_formats (dict): mapping attribute names (keys in self.formats)
                                to QtGui.QTextCharFormat instances.
        """
        # Replace existing formats where provided
        for key, fmt in new_formats.items():
            if key in self.formats and isinstance(fmt, QtGui.QTextCharFormat):
                self.formats[key] = fmt
            elif fmt.get('color') is not None:
                logger.debug(f"Processing format: {fmt}")
                self.formats[key] = self.make_format(
                    fmt.get('color'), bold=fmt.get('bold', False))
            else:
                logger.error(f"Format {fmt} can not be recononized.")

        # Rebuild rules with updated formats
        self._build_highlighting_rules()
        # Re-apply highlighting to existing document
        self.rehighlight()

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
                        # groups: (1)=addUserKnob, (2)=knob_number, (3)=knob_name
                        for grp, grp_fmt in (
                            (1, fmt),
                            (2, self.formats['user_knob_num']),
                            (3, self.formats['user_knob_name']),
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
                            self.setFormat(s1, l1, fmt)
                            self.setFormat(s2, l2, self.formats['node_name'])
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
                        self.set_format(text, num, index, self.formats['user_knob_num'])
                        self.set_format(text, nm, index, self.formats['user_knob_name'])

                    elif pat == self.knob_pattern:
                        nm = pattern.cap(1)
                        if nm == "name":
                            nn = pattern.cap(2)
                            self.set_format(text, nm, index, fmt)
                            self.set_format(text, nn, index, self.formats['node_name'])
                        else:
                            self.set_format(text, nm, index, fmt)

                    else:
                        self.setFormat(index, length, fmt)

                    index = pattern.indexIn(text, index + length)
