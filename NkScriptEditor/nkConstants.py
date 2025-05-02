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
