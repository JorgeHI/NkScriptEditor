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
import logging
import os

# Tool mode
dev_mode = False
logging_level = logging.DEBUG if dev_mode else logging.WARNING

# Tool paths
home_dir = os.path.expanduser("~")
config_dir = os.path.join(home_dir, ".nuke", "NkScriptEditor")
pref_filepath = os.path.join(config_dir, "preferences.pref")
code_dir = os.path.dirname(__file__)

# others
encodings = [
    "utf-8",
    "utf-8-sig",
    "windows-1252",
    "latin-1",
    "utf-16",
    "ascii"
]


class nkRegex:
    invalid = r"[^\x20-\x7E\t\r\n]"
    node_name = r"^\s*([a-zA-Z0-9_]+)\s\{$"
    flags = r"\s([\+\-])([A-Z]+)"
    userknob = r"^\s*(addUserKnob)\s\{([0-9]+)(?:\s([a-zA-Z0-9_]+))?"
    knob = r"^\s*(?!addUserKnob\b)([a-zA-Z0-9_]+)\s([a-zA-Z0-9_\"\\/\[\]\-]+)"
    callback = (
        r"^\s+(?:OnUserCreate|onCreate|onScriptLoad|onScriptSave|onScriptClose|"
        r"onDestroy|knobChanged|updateUI|autolabel|beforeRender|beforeFrameRender|"
        r"afterFrameRender|afterRender|afterBackgroundRender|afterBackgroundFrameRender|"
        r"filenameFilter|validateFilename|autoSaveFilter|autoSaveRestoreFilter)\s"
    )

class colors:
    """Centralized color definitions for theming consistency."""
    # Validation colors
    error_line_bg = (100, 30, 30)           # Dark red - paste error line background
    error_underline = (255, 80, 80)         # Bright red - validation error underline
    warning_underline = (220, 180, 50)      # Yellow/orange - validation warning underline
    current_line = (78, 78, 78)             # Gray - current line highlight
    paste_error_icon = (255, 100, 100)      # Red - paste error X icon

    # Line number area backgrounds for validation errors/warnings
    line_num_error_bg = (120, 40, 40)       # Error with marker
    line_num_error_light_bg = (100, 50, 50) # Error without marker
    line_num_warning_bg = (90, 90, 50)      # Warning with marker
    line_num_warning_light_bg = (90, 70, 30) # Warning without marker

    # Validation marker icons
    validation_error_icon = (255, 80, 80)   # Red exclamation mark
    validation_warning_icon = (220, 180, 50) # Yellow triangle

    # Diff viewer colors
    diff_add = (40, 80, 40)                 # Green - added lines
    diff_del = (100, 40, 40)                # Red - deleted lines
    diff_mod = (90, 80, 40)                 # Yellow - modified lines
    diff_equal = (45, 45, 45)               # Normal background
    diff_empty = (35, 35, 35)               # Empty/placeholder
    diff_line_number = (150, 150, 150)      # Line number text


class icons:
    icons_dir = os.path.join(code_dir, "icons")

    open_folder = os.path.join(icons_dir, "open_folder.png")
    nkse = os.path.join(icons_dir, "nkse_low.png")
