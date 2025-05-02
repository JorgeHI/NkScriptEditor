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
import nuke
import nukescripts
from NkScriptEditor import nkUtils
from NkScriptEditor import version as nkseVersion
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


class HelpTabWidget(QtWidgets.QWidget):
    """Help tab widget for Nk Script Editor. Provides links to GitHub and bug reporting."""
    def __init__(self, parent=None):
        super(HelpTabWidget, self).__init__(parent)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        group_box = QtWidgets.QGroupBox("Nk Script Editor")
        group_layout = QtWidgets.QVBoxLayout(group_box)

        # Info label
        info_label = QtWidgets.QLabel(
            f'<b>Nk Script Editor v{nkseVersion}</b> - Node developed by Jorge Hernandez Ibañez (JorgeHI)<br>'
            f'<span style="color: gray;">For assistance or bug report contact: info@jorgehi.com</span>'
        )
        info_label.setWordWrap(True)
        group_layout.addWidget(info_label)

        # Horizontal layout for buttons
        buttons_layout = QtWidgets.QHBoxLayout()

        github_button = QtWidgets.QPushButton("GitHub")
        github_button.clicked.connect(lambda: nukescripts.start(
            "https://github.com/JorgeHI/NkScriptEditor"))

        license_button = QtWidgets.QPushButton("License")
        license_button.clicked.connect(lambda: nukescripts.start(
            "https://github.com/JorgeHI/NkScriptEditor/blob/main/LICENSE"))

        report_button = QtWidgets.QPushButton("Report Problem")
        report_button.clicked.connect(lambda: nukescripts.start(
            "https://github.com/JorgeHI/NkScriptEditor/issues/new?"
            "assignees=JorgeHI&labels=bug&projects=&template=bug_report.md&title="))

        buttons_layout.addWidget(github_button)
        buttons_layout.addWidget(license_button)
        buttons_layout.addWidget(report_button)

        group_layout.addLayout(buttons_layout)
        main_layout.addWidget(group_box)
        main_layout.addStretch()
