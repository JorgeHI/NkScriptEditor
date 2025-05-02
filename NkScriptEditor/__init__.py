# -----------------------------------------------------------------------------
# Nk Script Editor for Nuke
# Copyright (c) 2025 Jorge Hernandez Ibañez
#
# This file is part of the Nk Script Editor project.
# Repository: https://github.com/JorgeHI/NkScriptEditor
#
# This file is licensed under the GNU General Public License v3.0.
# See the LICENSE file in the root of this repository for details.
# -----------------------------------------------------------------------------
# Def tool version
version = "0.1.1"

# Init tool
import nukescripts
from NkScriptEditor import nkUtils

# Create logger
logger = nkUtils.getLogger("NkScriptEditor")



from NkScriptEditor import nksePanel

def add_nk_script_editor_panel():
    logger.debug("Panel Created")
    return nksePanel.NkScriptEditor()

nukescripts.registerWidgetAsPanel(
    "NkScriptEditor.add_nk_script_editor_panel",
    "Nk Script Editor",
    "jorgehi.nkScriptEditor",
    True
)
