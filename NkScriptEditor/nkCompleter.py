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
"""
Autocomplete system for .nk script editing.

Provides context-aware autocompletion for:
- Node callbacks (knobChanged, onCreate, etc.)
- Standard knob names (name, xpos, ypos, etc.)
- addUserKnob syntax and knob types
- Node-specific knobs via Nuke API
"""
import re
import nuke
from NkScriptEditor import nkUtils

logger = nkUtils.getLogger(__name__)

if nuke.NUKE_VERSION_MAJOR < 11:
    from PySide import QtWidgets, QtGui, QtCore
elif nuke.NUKE_VERSION_MAJOR < 16:
    from PySide2 import QtWidgets, QtGui, QtCore
else:
    from PySide6 import QtWidgets, QtGui, QtCore


# =============================================================================
# Static Completion Data
# =============================================================================

# Node callbacks - these are standard for all nodes
CALLBACKS = [
    ("knobChanged", "Called when any knob value changes"),
    ("onCreate", "Called when node is created"),
    ("onDestroy", "Called when node is deleted"),
    ("onScriptLoad", "Called when script is loaded"),
    ("onScriptSave", "Called when script is saved"),
    ("onScriptClose", "Called when script is closed"),
    ("updateUI", "Called to update UI elements"),
    ("autolabel", "Called to generate node label"),
    ("beforeRender", "Called before render starts"),
    ("beforeFrameRender", "Called before each frame renders"),
    ("afterFrameRender", "Called after each frame renders"),
    ("afterRender", "Called after render completes"),
    ("afterBackgroundRender", "Called after background render"),
    ("afterBackgroundFrameRender", "Called after background frame render"),
    ("filenameFilter", "Called to filter filenames"),
    ("validateFilename", "Called to validate filenames"),
]

# Standard knobs present on all/most nodes
STANDARD_KNOBS = [
    ("name", "Node name identifier"),
    ("xpos", "X position in node graph"),
    ("ypos", "Y position in node graph"),
    ("tile_color", "Node tile color (hex)"),
    ("note_font", "Note font name"),
    ("note_font_size", "Note font size"),
    ("note_font_color", "Note font color (hex)"),
    ("selected", "Whether node is selected"),
    ("hide_input", "Hide input arrows"),
    ("cached", "Cache node output"),
    ("disable", "Disable node processing"),
    ("dope_sheet", "Show in dope sheet"),
    ("postage_stamp", "Show postage stamp preview"),
    ("postage_stamp_frame", "Frame for postage stamp"),
    ("lifetimeStart", "Lifetime start frame"),
    ("lifetimeEnd", "Lifetime end frame"),
    ("useLifetime", "Use lifetime range"),
    ("label", "Node label text"),
    ("icon", "Custom icon path"),
    ("indicators", "Node indicators"),
    ("gl_color", "OpenGL display color"),
]

# addUserKnob types (the number is the knob type ID)
USERKNOB_TYPES = [
    ("1", "Int_Knob - Integer value"),
    ("2", "Enumeration_Knob - Dropdown menu"),
    ("3", "Bitmask_Knob - Bitmask selector"),
    ("4", "Boolean_Knob - Checkbox (older)"),
    ("6", "Boolean_Knob - Checkbox"),
    ("7", "Double_Knob - Float value"),
    ("8", "Float_Knob - Float value (older)"),
    ("12", "String_Knob - Text input"),
    ("13", "File_Knob - File path"),
    ("14", "MultiLine_Knob - Multiline text"),
    ("15", "XY_Knob - 2D position"),
    ("16", "XYZ_Knob - 3D position"),
    ("18", "WH_Knob - Width/Height"),
    ("19", "BBox_Knob - Bounding box"),
    ("20", "Tab_Knob - Tab divider"),
    ("22", "PyScript_Knob - Python button"),
    ("23", "PythonCustomKnob - Custom Python"),
    ("26", "Text_Knob - Label text (no input)"),
    ("30", "Transform2d_Knob - 2D Transform"),
    ("41", "Channel_Knob - Channel selector"),
    ("68", "Link_Knob - Link to another knob"),
]

# Common node types for quick reference
COMMON_NODE_TYPES = [
    "Root", "Grade", "ColorCorrect", "Merge2", "Merge",
    "Transform", "Reformat", "Crop", "Read", "Write",
    "Blur", "Defocus", "EdgeBlur", "Sharpen",
    "Roto", "RotoPaint", "Tracker4",
    "Shuffle", "Shuffle2", "ShuffleCopy",
    "Copy", "CopyBBox", "AddChannels",
    "Premult", "Unpremult", "Invert",
    "Keyer", "Primatte", "IBKGizmo", "Keylight",
    "Group", "NoOp", "Dot", "BackdropNode",
    "Switch", "Dissolve", "TimeOffset",
    "FrameHold", "FrameRange", "Retime",
    "ScanlineRender", "Card", "Camera", "Light",
    "Constant", "CheckerBoard", "ColorBars", "ColorWheel",
    "Expression", "STMap", "IDistort", "LensDistortion",
    "VectorBlur", "MotionBlur", "ZDefocus",
    "DeepRead", "DeepWrite", "DeepMerge",
]


# =============================================================================
# Dynamic Knob Lookup via Nuke API
# =============================================================================

# Cache for node knobs to avoid repeated node creation
# Max size prevents unbounded memory growth in long Nuke sessions
_knob_cache = {}
_KNOB_CACHE_MAX_SIZE = 100


def get_knobs_for_node_type(node_type):
    """
    Get all knob names for a given node type using Nuke API.

    Creates a temporary node, extracts knob names, then deletes it.
    Results are cached to avoid repeated node creation.

    Args:
        node_type (str): The node class name (e.g., 'Grade', 'Merge2')

    Returns:
        list[tuple]: List of (knob_name, knob_type) tuples, or empty list if failed
    """
    # Check cache first
    if node_type in _knob_cache:
        return _knob_cache[node_type]

    knobs = []
    temp_node = None

    try:
        # Create a temporary node
        temp_node = nuke.createNode(node_type, inpanel=False)
        if temp_node:
            # Get all knobs
            for knob_name in temp_node.knobs():
                knob = temp_node.knob(knob_name)
                if knob:
                    knob_class = knob.Class()
                    knobs.append((knob_name, knob_class))

            logger.debug(f"Found {len(knobs)} knobs for {node_type}")

    except Exception as e:
        logger.debug(f"Could not create temp node for {node_type}: {e}")

    finally:
        # Clean up temporary node
        if temp_node:
            try:
                nuke.delete(temp_node)
            except Exception:
                pass

    # Cache the results (with size limit to prevent unbounded memory growth)
    if len(_knob_cache) >= _KNOB_CACHE_MAX_SIZE:
        _knob_cache.clear()
        logger.debug("Knob cache cleared due to size limit")
    _knob_cache[node_type] = knobs
    return knobs


def clear_knob_cache():
    """Clear the knob cache."""
    global _knob_cache
    _knob_cache = {}
    logger.debug("Knob cache cleared")


# =============================================================================
# Context Detection
# =============================================================================

def detect_context(text, cursor_position):
    """
    Detect the context at the cursor position.

    Determines:
    - Whether we're inside a node definition
    - What node type we're in
    - Whether we're at a knob name or value position

    Args:
        text (str): The full editor text
        cursor_position (int): Character position of cursor

    Returns:
        dict: Context information with keys:
            - 'in_node': bool - Whether inside a node definition
            - 'node_type': str or None - The node type if in a node
            - 'at_line_start': bool - Whether at start of line (for knob names)
            - 'current_word': str - The word being typed
            - 'line_text': str - Current line text
    """
    context = {
        'in_node': False,
        'node_type': None,
        'at_line_start': False,
        'current_word': '',
        'line_text': '',
    }

    if not text or cursor_position < 0:
        return context

    # Get text up to cursor
    text_before = text[:cursor_position]
    lines_before = text_before.splitlines()

    if not lines_before:
        return context

    # Current line text
    current_line = lines_before[-1] if lines_before else ''
    context['line_text'] = current_line

    # Check if at line start (only whitespace before cursor on this line)
    context['at_line_start'] = not current_line.strip()

    # Extract current word being typed
    word_match = re.search(r'(\w*)$', current_line)
    if word_match:
        context['current_word'] = word_match.group(1)

    # Find if we're inside a node by tracking brace depth
    # Go backwards through the text
    brace_depth = 0
    node_type = None

    # Pattern to find node starts
    node_pattern = re.compile(r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*\{', re.MULTILINE)

    # Count braces from start to cursor
    for i, char in enumerate(text_before):
        if char == '{':
            brace_depth += 1
            # Check if this is a node definition
            # Look backwards for node type
            line_start = text_before.rfind('\n', 0, i) + 1
            line = text_before[line_start:i+1]
            match = re.match(r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*\{', line)
            if match and brace_depth == 1:
                node_type = match.group(1)
        elif char == '}':
            brace_depth -= 1
            if brace_depth == 0:
                node_type = None

    context['in_node'] = brace_depth > 0
    context['node_type'] = node_type

    return context


# =============================================================================
# Completion Popup Widget
# =============================================================================

class CompletionPopup(QtWidgets.QListWidget):
    """
    Popup widget showing autocomplete suggestions.
    """

    completionSelected = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Use Qt.Tool instead of Qt.Popup to prevent aggressive auto-hiding
        # Qt.Popup can close unexpectedly on focus events
        self.setWindowFlags(
            QtCore.Qt.Tool |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint
        )
        # Use ClickFocus so the popup can receive mouse clicks
        # but won't steal focus from editor on keyboard navigation
        self.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.setMouseTracking(True)

        # Styling
        self.setStyleSheet("""
            QListWidget {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #555;
                font-family: "Courier New", monospace;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 3px 8px;
            }
            QListWidget::item:selected {
                background-color: #0066cc;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #4a4a4a;
            }
        """)

        self.itemClicked.connect(self._on_item_clicked)
        self.setMaximumHeight(200)
        self.setMinimumWidth(250)

    def _on_item_clicked(self, item):
        """Handle item click."""
        completion_text = item.data(QtCore.Qt.UserRole) or item.text()
        logger.debug(f"Autocomplete item clicked: {completion_text}")
        self.completionSelected.emit(completion_text)
        self.hide()

    def keyPressEvent(self, event):
        """Handle key presses for navigation."""
        if event.key() == QtCore.Qt.Key_Return or event.key() == QtCore.Qt.Key_Tab:
            current = self.currentItem()
            if current:
                self.completionSelected.emit(current.data(QtCore.Qt.UserRole) or current.text())
            self.hide()
        elif event.key() == QtCore.Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def set_completions(self, completions):
        """
        Set the completion items.

        Args:
            completions: List of (text, description) tuples or just strings
        """
        self.clear()
        for item in completions:
            if isinstance(item, tuple):
                text, description = item[0], item[1] if len(item) > 1 else ""
                list_item = QtWidgets.QListWidgetItem(f"{text}  - {description}" if description else text)
                list_item.setData(QtCore.Qt.UserRole, text)
            else:
                list_item = QtWidgets.QListWidgetItem(str(item))
                list_item.setData(QtCore.Qt.UserRole, str(item))
            self.addItem(list_item)

        if self.count() > 0:
            self.setCurrentRow(0)

    def move_selection(self, delta):
        """Move selection up or down."""
        current = self.currentRow()
        new_row = max(0, min(self.count() - 1, current + delta))
        self.setCurrentRow(new_row)


# =============================================================================
# Autocomplete Manager
# =============================================================================

class AutocompleteManager(QtCore.QObject):
    """
    Manages autocomplete for a code editor.

    Provides context-aware completions based on cursor position
    and current text content.
    """

    def __init__(self, editor):
        """
        Args:
            editor: The CodeEditor widget to attach to
        """
        super(AutocompleteManager, self).__init__(editor)
        self.editor = editor
        self.popup = CompletionPopup()
        self.popup.completionSelected.connect(self._insert_completion)
        self.enabled = True
        self.min_chars = 2  # Minimum characters before showing completions

        # Install event filter to handle clicks outside popup
        self.editor.installEventFilter(self)

    def _get_completions(self, context, prefix):
        """
        Get relevant completions based on context.

        Args:
            context (dict): Context from detect_context()
            prefix (str): The prefix to filter by

        Returns:
            list: Filtered completion items
        """
        completions = []
        prefix_lower = prefix.lower()

        # If at line start in a node, suggest knob names
        if context['in_node'] and context['at_line_start']:
            # Add callbacks
            for name, desc in CALLBACKS:
                if name.lower().startswith(prefix_lower):
                    completions.append((name, f"Callback: {desc}"))

            # Add standard knobs
            for name, desc in STANDARD_KNOBS:
                if name.lower().startswith(prefix_lower):
                    completions.append((name, desc))

            # Add node-specific knobs if we know the node type
            if context['node_type']:
                node_knobs = get_knobs_for_node_type(context['node_type'])
                for name, knob_class in node_knobs:
                    if name.lower().startswith(prefix_lower):
                        # Avoid duplicates with standard knobs
                        if not any(c[0] == name for c in completions):
                            completions.append((name, f"[{knob_class}]"))

        # If typing "addUserKnob", suggest knob types
        elif 'addUserKnob' in context['line_text']:
            for type_id, desc in USERKNOB_TYPES:
                if type_id.startswith(prefix) or desc.lower().startswith(prefix_lower):
                    completions.append((type_id, desc))

        # If at root level, suggest node types
        elif not context['in_node']:
            for node_type in COMMON_NODE_TYPES:
                if node_type.lower().startswith(prefix_lower):
                    completions.append((node_type, "Node type"))

        return completions

    def show_completions(self):
        """Show completion popup based on current cursor position."""
        if not self.enabled:
            return

        # Get context
        cursor = self.editor.textCursor()
        text = self.editor.toPlainText()
        position = cursor.position()

        context = detect_context(text, position)
        prefix = context['current_word']

        # Don't show if prefix too short
        if len(prefix) < self.min_chars:
            self.popup.hide()
            return

        # Get completions
        completions = self._get_completions(context, prefix)

        if not completions:
            self.popup.hide()
            return

        # Set completions and show popup
        self.popup.set_completions(completions)

        # Position popup below cursor
        cursor_rect = self.editor.cursorRect()
        global_pos = self.editor.mapToGlobal(cursor_rect.bottomLeft())
        self.popup.move(global_pos)
        self.popup.show()
        self.popup.raise_()  # Bring to front
        logger.debug(f"Autocomplete popup shown with {len(completions)} completions")

    def _insert_completion(self, text):
        """Insert the selected completion."""
        logger.debug(f"Inserting autocomplete: {text}")
        cursor = self.editor.textCursor()
        logger.debug(f"Cursor position before: {cursor.position()}")

        # Remove the prefix that was already typed
        cursor.movePosition(QtGui.QTextCursor.StartOfWord, QtGui.QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        logger.debug(f"Cursor position after removing prefix: {cursor.position()}")

        # Insert completion
        cursor.insertText(text)
        self.editor.setTextCursor(cursor)
        logger.debug(f"Inserted completion text: {text}")

    def handle_key_press(self, event):
        """
        Handle key press events for autocomplete.

        Returns:
            bool: True if event was handled, False otherwise
        """
        if not self.popup.isVisible():
            return False

        key = event.key()
        logger.debug(f"Autocomplete key press: key={key}")

        if key == QtCore.Qt.Key_Down:
            self.popup.move_selection(1)
            return True
        elif key == QtCore.Qt.Key_Up:
            self.popup.move_selection(-1)
            return True
        elif key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Tab):
            current = self.popup.currentItem()
            logger.debug(f"Return/Tab pressed, current item: {current}")
            if current:
                completion_text = current.data(QtCore.Qt.UserRole) or current.text()
                logger.debug(f"Completion text to insert: {completion_text}")
                self._insert_completion(completion_text)
            else:
                logger.warning("No current item selected in autocomplete popup")
            self.popup.hide()
            return True
        elif key == QtCore.Qt.Key_Escape:
            self.popup.hide()
            return True

        return False

    def hide_popup(self):
        """Hide the completion popup."""
        self.popup.hide()

    def is_popup_visible(self):
        """Check if popup is visible."""
        return self.popup.isVisible()

    def eventFilter(self, obj, event):
        """
        Filter events on the editor to handle clicks outside popup.

        This closes the popup when user clicks in the editor outside
        the popup area while it's visible.
        """
        if obj == self.editor and event.type() == QtCore.QEvent.MouseButtonPress:
            if self.popup.isVisible():
                # Get click position in global coordinates
                global_pos = self.editor.mapToGlobal(event.pos())
                # Check if click is outside popup
                if not self.popup.geometry().contains(self.popup.mapFromGlobal(global_pos)):
                    self.popup.hide()
        return False  # Don't filter the event, let it continue
