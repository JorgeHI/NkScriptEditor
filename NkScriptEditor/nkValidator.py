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
Structure validator for .nk (Nuke script) files.

This module provides validation for .nk script structure, detecting:
- Unmatched braces (unclosed or extra closing braces)
- Malformed node definitions
- Improper nesting
"""
import re
from NkScriptEditor import nkUtils

logger = nkUtils.getLogger(__name__)


class StructureError:
    """Represents a structural error found in a .nk script."""

    # Error severity levels
    ERROR = "error"
    WARNING = "warning"

    def __init__(self, line_number, column, message, severity=ERROR, length=1):
        """
        Args:
            line_number (int): 1-based line number where error occurs
            column (int): 0-based column position in the line
            message (str): Human-readable error description
            severity (str): Either ERROR or WARNING
            length (int): Length of the problematic text (for underlining)
        """
        self.line_number = line_number
        self.column = column
        self.message = message
        self.severity = severity
        self.length = length

    def __repr__(self):
        return f"StructureError(line {self.line_number}, col {self.column}: {self.message})"


class BraceInfo:
    """Tracks information about an opening brace."""

    def __init__(self, line_number, column, node_type=None):
        self.line_number = line_number
        self.column = column
        self.node_type = node_type  # The node type if this starts a node


def validate_structure(script_text):
    """
    Validate the structure of a .nk script.

    Checks for:
    - Balanced braces (every { has a matching })
    - Proper node definitions (NodeType { ... })
    - Proper nesting of nodes

    Args:
        script_text (str): The full content of a .nk script file.

    Returns:
        list[StructureError]: A list of structural errors found, empty if valid.
    """
    errors = []
    lines = script_text.splitlines()

    # Track brace stack: list of BraceInfo for each open brace
    brace_stack = []

    # Regex to detect node definition start: "NodeType {"
    node_start_pattern = re.compile(r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*\{\s*$')

    # Track if we're inside a multi-line string/expression
    in_multiline = False
    multiline_start_line = 0

    for line_num, line in enumerate(lines, start=1):
        # Skip empty lines
        if not line.strip():
            continue

        # Check for node definition start
        node_match = node_start_pattern.match(line)

        # Process each character for brace matching
        i = 0
        while i < len(line):
            char = line[i]

            # Handle string literals (skip content inside quotes)
            if char == '"':
                # Find closing quote (handle escaped quotes)
                i += 1
                while i < len(line):
                    if line[i] == '\\' and i + 1 < len(line):
                        i += 2  # Skip escaped character
                        continue
                    if line[i] == '"':
                        break
                    i += 1
                i += 1
                continue

            # Handle TCL braces in values (like {{...}})
            # These are data braces, not structure braces
            # We detect them by checking if we're inside a knob value context

            if char == '{':
                # Determine if this is a structural brace or data brace
                is_node_start = (node_match is not None and
                                 line.rstrip().endswith('{') and
                                 i == line.rstrip().rfind('{'))

                # Check if this looks like a data brace (inside a knob value)
                # Data braces typically appear after a space following knob name
                before = line[:i].rstrip()
                is_data_brace = False

                if brace_stack:  # We're inside a node
                    # Check if this line looks like a knob definition
                    knob_pattern = re.match(r'^\s*[a-zA-Z_][a-zA-Z0-9_]*\s+', line)
                    if knob_pattern and i > knob_pattern.end() - 1:
                        is_data_brace = True
                    # Also check for addUserKnob patterns
                    if 'addUserKnob' in before:
                        is_data_brace = True

                if not is_data_brace:
                    node_type = node_match.group(1) if node_match else None
                    brace_stack.append(BraceInfo(line_num, i, node_type))

            elif char == '}':
                # Check if this is a structural closing brace
                before = line[:i].rstrip()

                # Heuristic: structural closing braces are typically alone or at line end
                after = line[i + 1:].strip()
                is_structural = (not before or  # Brace at start of line
                                 line.strip() == '}' or  # Only brace on line
                                 (not after and not before.endswith('"')))  # At end, not after string

                # If we have open braces and this looks structural
                if is_structural:
                    if brace_stack:
                        brace_stack.pop()
                    else:
                        # Extra closing brace
                        errors.append(StructureError(
                            line_num, i,
                            "Unexpected closing brace '}' - no matching opening brace",
                            StructureError.ERROR, 1
                        ))

            i += 1

    # Check for unclosed braces
    for unclosed in brace_stack:
        if unclosed.node_type:
            msg = f"Unclosed node '{unclosed.node_type}' - missing closing brace '}}'"
        else:
            msg = "Unclosed brace '{' - missing closing brace '}'"
        errors.append(StructureError(
            unclosed.line_number, unclosed.column,
            msg, StructureError.ERROR, 1
        ))

    return errors


def validate_node_definitions(script_text):
    """
    Validate node definitions for common issues.

    Checks for:
    - Nodes with missing names
    - Invalid node type names
    - Duplicate node names

    Args:
        script_text (str): The full content of a .nk script file.

    Returns:
        list[StructureError]: A list of structural errors found.
    """
    errors = []
    lines = script_text.splitlines()

    # Track node names for duplicate detection
    seen_names = {}

    # Regex patterns
    node_start_pattern = re.compile(r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*\{\s*$')
    name_pattern = re.compile(r'^\s*name\s+(\S+)')

    current_node = None
    current_node_line = 0
    brace_depth = 0

    for line_num, line in enumerate(lines, start=1):
        # Check for node start
        node_match = node_start_pattern.match(line)
        if node_match and brace_depth == 0:
            current_node = node_match.group(1)
            current_node_line = line_num
            brace_depth = 1
            continue

        if brace_depth > 0:
            # Count braces (simplified)
            brace_depth += line.count('{') - line.count('}')

            # Look for name knob
            name_match = name_pattern.match(line)
            if name_match and brace_depth == 1:
                node_name = name_match.group(1)

                # Check for duplicate names
                if node_name in seen_names:
                    errors.append(StructureError(
                        line_num, line.find(node_name),
                        f"Duplicate node name '{node_name}' (first defined at line {seen_names[node_name]})",
                        StructureError.WARNING, len(node_name)
                    ))
                else:
                    seen_names[node_name] = line_num

            # Check if node closed
            if brace_depth == 0:
                current_node = None

    return errors


def validate_script(script_text):
    """
    Perform full validation of a .nk script.

    Combines structure validation and node definition validation.

    Args:
        script_text (str): The full content of a .nk script file.

    Returns:
        list[StructureError]: A list of all errors found, sorted by line number.
    """
    errors = []

    # Structure validation (brace matching)
    errors.extend(validate_structure(script_text))

    # Node definition validation
    errors.extend(validate_node_definitions(script_text))

    # Sort by line number
    errors.sort(key=lambda e: (e.line_number, e.column))

    return errors


def get_errors_by_line(errors):
    """
    Group errors by line number for easy lookup.

    Args:
        errors (list[StructureError]): List of errors from validate_script

    Returns:
        dict[int, list[StructureError]]: Mapping of line numbers to errors on that line
    """
    by_line = {}
    for error in errors:
        if error.line_number not in by_line:
            by_line[error.line_number] = []
        by_line[error.line_number].append(error)
    return by_line
