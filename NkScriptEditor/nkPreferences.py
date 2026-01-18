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
    """
    A preferences tab widget for customizing the appearance and behavior of the Nk Script Editor.

    This includes options for toggling text wrapping and setting syntax highlighting
    preferences such as text color and boldness for different script components.
    """

    wrapTextToggled = QtCore.Signal(bool)
    apply_preferences = QtCore.Signal(dict)
    showEncodingToggled = QtCore.Signal(bool)
    validationToggled = QtCore.Signal(bool)

    def __init__(self):
        """Initialize the preference panel with UI elements and load saved or default preferences."""
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
        # Show encoding selector checkbox
        self.show_encoding_checkbox = QtWidgets.QCheckBox("Show encoding selector")
        self.show_encoding_checkbox.setChecked(False)  # Disabled by default
        self.show_encoding_checkbox.setToolTip("Show/hide the encoding combobox in the editor (defaults to UTF-8 when hidden)")
        textEdit_pref_layout.addWidget(self.show_encoding_checkbox)
        # Enable validation checkbox
        self.enable_validation_checkbox = QtWidgets.QCheckBox("Enable script validation")
        self.enable_validation_checkbox.setChecked(True)  # Enabled by default
        self.enable_validation_checkbox.setToolTip("Enable/disable automatic script validation (checks for syntax errors and warnings)")
        textEdit_pref_layout.addWidget(self.enable_validation_checkbox)

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

        # Save Preferences buttons
        buttons_layout = QtWidgets.QHBoxLayout(self)
        self.reset_prefs_button = QtWidgets.QPushButton("Reset")
        self.reset_prefs_button.clicked.connect(self.reset_pref)
        buttons_layout.addWidget(self.reset_prefs_button)
        self.save_prefs_button = QtWidgets.QPushButton("Save")
        self.save_prefs_button.clicked.connect(self.save_preferences)
        buttons_layout.addWidget(self.save_prefs_button)
        prefs_layout.addLayout(buttons_layout)

        # Signals
        self.wrap_checkbox.toggled.connect(self.wrapTextToggled.emit)
        self.show_encoding_checkbox.toggled.connect(self.showEncodingToggled.emit)
        self.enable_validation_checkbox.toggled.connect(self.validationToggled.emit)

        # Load Preferences
        if os.path.isfile(nkConstants.pref_filepath):
            # Load user preferences
            self.load_preferences(filepath=nkConstants.pref_filepath)
        else:  # Set default preferences
            self.apply_default_preferences()

    def force_refresh(self):
        """Force re-emit of current wrap text and highlight preferences to apply changes instantly."""
        self.wrapTextToggled.emit(self.wrap_checkbox.isChecked())
        self.showEncodingToggled.emit(self.show_encoding_checkbox.isChecked())
        self.apply_preferences.emit(self.collect_color_preferences())

    def apply_default_preferences(self):
        """Set default highlighting preferences and wrap setting."""
        # Wrap text default
        prefs = {}
        prefs["wrap"] = False
        prefs["show_encoding"] = False  # Encoding selector hidden by default
        prefs["enable_validation"] = True  # Validation enabled by default
        # Defaults for highlight colors
        prefs["highlight"] = {
            'node_type':       {'color': [255, 200, 150], 'bold': True},
            'flag':            {'color': [120, 180, 255], 'bold': False},
            'node_name':       {'color': [255, 255, 255], 'bold': True},
            'knob':            {'color': [200, 160, 255], 'bold': False},
            'user_knob':       {'color': [240, 220, 160], 'bold': False},
            'user_knob_name':  {'color': [220, 220, 160], 'bold': False},
            'callback':        {'color': [128, 200, 255], 'bold': True},
        }
        self.set_preferences(prefs)

    def set_preferences(self, prefs):
        """
        Apply a dictionary of saved preferences to the UI widgets.

        Args:
            prefs (dict): The preference dictionary with wrap, show_encoding, enable_validation, and highlight settings.
        """
        if prefs.get("wrap") is not None:
            self.wrap_checkbox.setChecked(prefs["wrap"])
        if prefs.get("show_encoding") is not None:
            self.show_encoding_checkbox.setChecked(prefs["show_encoding"])
        if prefs.get("enable_validation") is not None:
            self.enable_validation_checkbox.setChecked(prefs["enable_validation"])

        # Get highlight preferences with defaults as fallback
        highlight_prefs = prefs.get("highlight", {})

        # Default highlight colors (used if not in saved preferences)
        default_highlights = {
            'node_type':       {'color': [255, 200, 150], 'bold': True},
            'flag':            {'color': [120, 180, 255], 'bold': False},
            'node_name':       {'color': [255, 255, 255], 'bold': True},
            'knob':            {'color': [200, 160, 255], 'bold': False},
            'user_knob':       {'color': [240, 220, 160], 'bold': False},
            'user_knob_name':  {'color': [220, 220, 160], 'bold': False},
            'callback':        {'color': [128, 200, 255], 'bold': True},
        }

        # Apply highlights for all preference items
        for label_text, attr in self.pref_items:
            # Use saved value if exists, otherwise use default
            opts = highlight_prefs.get(attr, default_highlights.get(attr, {'color': [255, 255, 255], 'bold': False}))

            # Ensure color exists and is valid
            if opts.get('color') is None:
                opts['color'] = default_highlights.get(attr, {}).get('color', [255, 255, 255])

            color = QtGui.QColor(*opts['color'])
            bold = opts.get('bold', False)

            # Set color button stylesheet
            btn = getattr(self, f"{attr}_color_button")
            btn.setStyleSheet(f"background-color: {color.name()};")
            setattr(self, f"{attr}_color", color)
            # Set bold checkbox
            chk = getattr(self, f"{attr}_bold_checkbox")
            chk.setChecked(bold)

    def reset_pref(self):
        """Reset preferences to their default values and update UI accordingly."""
        self.apply_default_preferences()
        self.force_refresh()

    def choose_color(self, attr):
        """
        Open a QColorDialog to pick a color and apply it to the given attribute.

        Args:
            attr (str): The attribute name whose color is being set.
        """
        color = QtWidgets.QColorDialog.getColor(parent=self)
        if not color.isValid():
            return
        # Update the button's stylesheet to show the selected color
        btn = getattr(self, f"{attr}_color_button")
        btn.setStyleSheet(f"background-color: {color.name()};")
        # Store the color object
        setattr(self, f"{attr}_color", color)
        # Make sure color changes update the color
        logger.debug(f"Color saved: {str(color)}")
        self.apply_preferences.emit(self.collect_color_preferences())
        logger.debug(f"Apply changes submited.")

    def load_preferences(self, filepath=None):
        """
        Load user preferences from a .pref JSON file.

        Args:
            filepath (str, optional): Custom path to preference file. Defaults to nkConstants.pref_filepath.
        """
        pref_path = filepath or nkConstants.pref_filepath
        try:
            with open(pref_path, 'r') as f:
                prefs_data = json.load(f)
            self.set_preferences(prefs_data)
        except Exception as e:
            logger.error(f"Failed to load preferences: {e}")
            logger.warning("Applying default preferences "
                "because local pref file can not be read")
            self.apply_default_preferences()

    def save_preferences(self):
        """
        Save current editor preferences to disk in a JSON .pref file under the user's config folder.
        """
        # 1. Build preferences dict
        prefs = self.collect_preferences()
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

    def collect_color_preferences(self):
        """
        Collect current highlight color and bold settings for each preference item.

        Returns:
            dict: Mapping from attribute names to dictionaries with 'color' and 'bold' keys.
        """
        prefs = {}
        for label_text, attr in self.pref_items:
            # Retrieve stored color; may be None if not set
            qcolor = getattr(self, f"{attr}_color", None)
            color = qcolor.getRgb()[:3] if isinstance(qcolor, QtGui.QColor) else None
            # Retrieve bold state from checkbox
            bold = getattr(self, f"{attr}_bold_checkbox").isChecked()
            prefs[attr] = {
                'color': color,
                'bold': bold
            }
        return prefs

    def collect_preferences(self):
        """
        Collect all user preferences including wrap setting and syntax highlight formatting.

        Returns:
            dict: Full preference dictionary including "wrap", "show_encoding", "enable_validation", and "highlight" keys.
        """
        prefs = {}
        prefs["wrap"] = self.wrap_checkbox.isChecked()
        prefs["show_encoding"] = self.show_encoding_checkbox.isChecked()
        prefs["enable_validation"] = self.enable_validation_checkbox.isChecked()
        prefs["highlight"] = self.collect_color_preferences()

        return prefs

