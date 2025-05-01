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


class PreferenceTabWidget(QtWidgets.QWidget):

    wrapTextToggled = QtCore.Signal(bool)

    def __init__(self):
        super(PreferenceTabWidget, self).__init__()

        prefs_layout = QtWidgets.QVBoxLayout(self)

        textEdit_group = QtWidgets.QGroupBox("Text Editor")
        prefs_layout.addWidget(textEdit_group)
        textEdit_pref_layout = QtWidgets.QVBoxLayout()
        textEdit_group.setLayout(textEdit_pref_layout)
        # Wrap text checkbox
        self.wrap_checkbox = QtWidgets.QCheckBox("Wrap text")
        self.wrap_checkbox.setChecked(True)
        textEdit_pref_layout.addWidget(self.wrap_checkbox)

        highlight_group = QtWidgets.QGroupBox("Highlighting Colors")
        prefs_layout.addWidget(highlight_group)
        highlighter_pref_layout = QtWidgets.QVBoxLayout()
        highlight_group.setLayout(highlighter_pref_layout)
        # Define the list of preference items: label and attribute prefix
        self.pref_items = [
            ("Node Type",        "node_type"),
            ("Node Name",        "node_name"),
            ("Knob",             "knob"),
            ("User Knob",        "user_knob"),
            ("User Knob Name",   "user_knob_name"),
            ("Flag",             "flag"),
            ("Callback",         "callback"),
        ]

        # Create one horizontal row per preference item
        for label_text, attr in self.pref_items:
            # Horizontal layout: Label → Color Picker → Bold Checkbox
            row = QtWidgets.QHBoxLayout()

            # 1) Label
            lbl = QtWidgets.QLabel(f"{label_text}:")
            row.addWidget(lbl)

            # 2) Color picker button
            btn = QtWidgets.QPushButton()
            btn.setFixedSize(24, 24)
            # ← here: accept *any* args, ignore them, and use our “attr” default
            btn.clicked.connect(lambda *_, a=attr: self.choose_color(a))
            setattr(self, f"{attr}_color_button", btn)
            row.addWidget(btn)

            # 3) Bold checkbox
            chk = QtWidgets.QCheckBox("Bold")
            setattr(self, f"{attr}_bold_checkbox", chk)
            row.addWidget(chk)

            highlighter_pref_layout.addLayout(row)

        # Add stretch to push the Save button to the bottom
        prefs_layout.addStretch()

        # Save Preferences button
        self.save_prefs_button = QtWidgets.QPushButton("Save Preferences")
        self.save_prefs_button.clicked.connect(self.save_preferences)
        prefs_layout.addWidget(self.save_prefs_button)

        # Signals
        self.wrap_checkbox.toggled.connect(self.wrapTextToggled.emit)

        # Load Preferences
        # TODO check for a pref file
        self.apply_default_preferences()

    def apply_default_preferences(self):
        """
        Apply default settings for wrap text and highlighting colors/bold states.
        """
        # Wrap text default
        self.wrap_checkbox.setChecked(False)

        # Defaults for highlight colors
        defaults = {
            'node_type':       {'color': QtGui.QColor(255, 200, 150), 'bold': True},
            'flag':            {'color': QtGui.QColor(120, 180, 255), 'bold': False},
            'node_name':       {'color': QtGui.QColor(255, 255, 255), 'bold': True},
            'knob':            {'color': QtGui.QColor(200, 160, 255), 'bold': False},
            'user_knob':       {'color': QtGui.QColor(240, 220, 160), 'bold': False},
            'user_knob_name':  {'color': QtGui.QColor(220, 220, 160), 'bold': False},
            'callback':        {'color': QtGui.QColor(128, 200, 255), 'bold': True},
        }
        for attr, opts in defaults.items():
            color = opts['color']
            bold = opts['bold']
            # Set color button stylesheet
            btn = getattr(self, f"{attr}_color_button")
            btn.setStyleSheet(f"background-color: {color.name()};")
            setattr(self, f"{attr}_color", color)
            # Set bold checkbox
            chk = getattr(self, f"{attr}_bold_checkbox")
            chk.setChecked(bold)


    def choose_color(self, attr):
        """Open a QColorDialog, store the chosen color, and update the button background."""
        color = QtWidgets.QColorDialog.getColor(parent=self)
        if not color.isValid():
            return
        # Update the button's stylesheet to show the selected color
        btn = getattr(self, f"{attr}_color_button")
        btn.setStyleSheet(f"background-color: {color.name()};")
        # Store the color object
        setattr(self, f"{attr}_color", color)
        logger.debug(f"Color saved: {str(color)}")

    def save_preferences(self):
        """
        Gather color and bold settings for each preference item,
        then persist them as a JSON file with .pref extension under ~/.nuke/NkScriptEditor/.
        """
        # 1. Build preferences dict
        prefs = {}
        for label_text, attr in self.pref_items:
            color = getattr(self, f"{attr}_color", None)
            bold  = getattr(self, f"{attr}_bold_checkbox").isChecked()
            # Store color as hex string if present
            prefs[attr] = {
                "color": color.name() if color else None,
                "bold": bold
            }

        # 2. Create output dir
        os.makedirs(nkConstants.config_dir, exist_ok=True)
        filepath = nkConstants.pref_filepath

        # 3. Write JSON to .pref file
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(prefs, f, indent=4)
            msg = f"Preferences saved to:\n{filepath}"
            logger.info(msg)
            QtWidgets.QMessageBox.information(
                self,
                "Preferences Saved",
                msg
            )
        except Exception as e:
            logger.error(str(e))
            QtWidgets.QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save preferences:\n{e}"
            )

