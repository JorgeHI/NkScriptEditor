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

import nukescripts
import nksePanel

def add_nk_script_editor_panel():
    return nksePanel.NkScriptEditor()

nukescripts.registerWidgetAsPanel(
    "nkScriptEditor.add_nk_script_editor_panel",
    "Nk Script Editor",
    "jorgehi.nkScriptEditor",
    True
)
