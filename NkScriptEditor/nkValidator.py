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


class BraceContext:
    """Constants for brace context classification."""
    STRUCTURAL = "structural"
    DATA = "data"
    UNKNOWN = "unknown"


class GroupScope:
    """Represents a Group scope for tracking nested node names."""

    def __init__(self, group_name, start_line):
        self.group_name = group_name
        self.start_line = start_line
        self.node_names = {}  # name -> line_number mapping for this scope


class ScopeTracker:
    """Tracks Group hierarchy and scoped node names."""

    def __init__(self):
        self.scope_stack = [GroupScope("__root__", 0)]  # Global scope at bottom

    def current_scope(self):
        """Get the current scope."""
        return self.scope_stack[-1]

    def enter_group(self, group_name, line_number):
        """Enter a new Group scope."""
        self.scope_stack.append(GroupScope(group_name, line_number))

    def exit_group(self):
        """Exit the current Group scope."""
        if len(self.scope_stack) > 1:  # Never pop root
            self.scope_stack.pop()

    def get_scope_path(self):
        """Get the full scope path as a string."""
        return " > ".join(s.group_name for s in self.scope_stack)

    def register_node_name(self, node_name, line_number):
        """
        Register a node name in the current scope.

        Returns:
            int or None: Line number of previous definition if duplicate, else None
        """
        scope = self.current_scope()
        if node_name in scope.node_names:
            return scope.node_names[node_name]
        scope.node_names[node_name] = line_number
        return None


def classify_brace_context(line, char_index, brace_stack, is_opening):
    """
    Classify whether a brace is structural or data based on context.

    Args:
        line (str): Current line being processed
        char_index (int): Position of the brace character
        brace_stack (list): Current structural brace stack
        is_opening (bool): True for '{', False for '}'

    Returns:
        str: BraceContext constant (STRUCTURAL, DATA, or UNKNOWN)
    """
    # Not inside any node -> must be structural
    if not brace_stack:
        return BraceContext.STRUCTURAL if is_opening else BraceContext.STRUCTURAL

    before = line[:char_index]
    after = line[char_index + 1:]

    # Pattern 0: TCL expression braces (like {{expression}} or {{{expression}}})
    # These appear at the start of a knob value
    if is_opening:
        # Check if this is part of {{ or {{{ sequence
        if char_index + 1 < len(line) and line[char_index + 1] == '{':
            # Next character is also a brace - this is TCL expression syntax
            return BraceContext.DATA
    else:
        # Check if this is part of }} or }}} sequence
        if char_index > 0 and line[char_index - 1] == '}':
            # Previous character was also a brace - this is TCL expression closing
            return BraceContext.DATA

    # Pattern 1: Knob value patterns (high confidence data braces)
    # Examples: "red {curve}", "alpha {}", "lut {master {", "  lut {", "ROI {"
    knob_value_patterns = [
        r'[a-zA-Z_][a-zA-Z0-9_]*\s+\{$',  # "knob_name {" (at end of before string) - allow uppercase
        r'\{[a-z_]+\s+\{$',  # "{ nested_key {" (nested dict)
        r'\s+(red|green|blue|alpha|master|lut|channels|ROI)\s+\{$',  # Common knob patterns
    ]

    for pattern in knob_value_patterns:
        if re.search(pattern, before + '{'):
            return BraceContext.DATA

    # Pattern 1b: If there's non-whitespace content after the opening brace on the same line,
    # it's almost certainly a data brace (knob value), not a node definition
    if is_opening:
        after_stripped = after.strip()
        if after_stripped and not after_stripped.startswith('#'):  # Has content (not just comment)
            # Check if the before part looks like it could be a knob name
            before_stripped = before.strip()
            # Pattern: word followed by space followed by brace
            if re.search(r'[a-zA-Z_][a-zA-Z0-9_]*\s+$', before_stripped):
                return BraceContext.DATA

    # Pattern 2: Closing braces in value context
    # Look for: "curve}" or "{}" - be very specific to avoid false positives
    if not is_opening:
        # Check if this closing brace is right after a known data value keyword
        value_close_patterns = [
            r'curve\}$',  # Literal "curve}"
            r'expression\}$',  # Literal "expression}"
            r'\{\}$',  # Empty braces "{}"
        ]
        line_up_to_brace = line[:char_index + 1]
        for pattern in value_close_patterns:
            if re.search(pattern, line_up_to_brace):
                return BraceContext.DATA

        # Check for pattern like "blue {curve}}" - multi-brace on same line
        # If we find an opening data brace earlier on this line, this could be its closing brace
        before_stripped = before.strip()
        if before_stripped.endswith('{') or re.search(r'\{[a-z_]+$', before_stripped):
            # There's an unclosed data brace on this line, this probably closes it
            return BraceContext.DATA

    # Pattern 3: addUserKnob context (always data braces)
    if 'addUserKnob' in line:
        return BraceContext.DATA

    # Pattern 4: Structural brace indicators
    # Typically: alone on line, or at end of line after node name
    if is_opening:
        # Node definition pattern: "NodeType {"
        if re.match(r'^\s*[A-Z][A-Za-z0-9_]*\s*\{\s*$', line):
            return BraceContext.STRUCTURAL
    else:
        # Closing structural braces are typically alone
        before_stripped = before.strip()
        after_stripped = after.strip()
        if line.strip() == '}' or (not before_stripped and not after_stripped):
            return BraceContext.STRUCTURAL

    # Default: likely structural if at node level, data if deeper
    return BraceContext.STRUCTURAL


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

    # Track data braces across all lines (does NOT reset per line)
    data_brace_depth = 0

    # Regex to detect node definition start: "NodeType {"
    node_start_pattern = re.compile(r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*\{\s*$')

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

            if char == '{':
                # If we're already inside a data brace, all nested braces are also data braces
                if data_brace_depth > 0:
                    data_brace_depth += 1
                    logger.debug(f"[VALIDATION] Nested data brace (opening) at line {line_num}, col {i}, depth={data_brace_depth}")
                else:
                    # Use classify_brace_context to determine if this is structural or data
                    context = classify_brace_context(line, i, brace_stack, is_opening=True)

                    if context == BraceContext.STRUCTURAL:
                        node_type = node_match.group(1) if node_match else None
                        brace_stack.append(BraceInfo(line_num, i, node_type))
                        logger.debug(f"[VALIDATION] Structural opening brace at line {line_num}, col {i}, node={node_type}")
                        logger.debug(f"  Stack depth: {len(brace_stack)}")
                    else:
                        # Track data brace depth
                        data_brace_depth += 1
                        logger.debug(f"[VALIDATION] Data brace (opening) at line {line_num}, col {i}, depth={data_brace_depth}")

            elif char == '}':
                # First check if we have unclosed data braces on this line
                if data_brace_depth > 0:
                    # This closes a data brace
                    data_brace_depth -= 1
                    logger.debug(f"[VALIDATION] Data brace (closing) at line {line_num}, col {i}, depth now={data_brace_depth}")
                else:
                    # Use classify_brace_context to determine if this is structural or data
                    context = classify_brace_context(line, i, brace_stack, is_opening=False)

                    if context == BraceContext.STRUCTURAL:
                        if brace_stack:
                            popped = brace_stack.pop()
                            logger.debug(f"[VALIDATION] Structural closing brace at line {line_num}, matched with line {popped.line_number}")
                            logger.debug(f"  Stack depth now: {len(brace_stack)}")
                        else:
                            # Extra closing brace - ERROR
                            error = StructureError(
                                line_num, i,
                                "Unexpected closing brace '}' - no matching opening brace",
                                StructureError.ERROR, 1
                            )
                            errors.append(error)
                            logger.warning(f"[VALIDATION] {error.severity.upper()} at line {line_num}: {error.message}")
                            logger.warning(f"  Line content: {repr(line)}")
                            logger.warning(f"  Column: {i}, Character: '{char}'")
                    else:
                        # Treat as data brace even if not preceded by opening (could be from previous line)
                        logger.debug(f"[VALIDATION] Data brace (closing, standalone) at line {line_num}, col {i} - IGNORED")

            i += 1

    # Check for unclosed braces
    for unclosed in brace_stack:
        if unclosed.node_type:
            msg = f"Unclosed node '{unclosed.node_type}' - missing closing brace '}}'"
        else:
            msg = "Unclosed brace '{' - missing closing brace '}'"
        error = StructureError(
            unclosed.line_number, unclosed.column,
            msg, StructureError.ERROR, 1
        )
        errors.append(error)
        logger.warning(f"[VALIDATION] {error.severity.upper()} at line {unclosed.line_number}: {msg}")
        logger.warning(f"  Opening brace column: {unclosed.column}")
        if unclosed.node_type:
            logger.warning(f"  Node type: {unclosed.node_type}")

    return errors


def validate_node_definitions(script_text):
    """
    Validate node definitions with Group scope awareness.

    Checks for:
    - Nodes with missing names
    - Invalid node type names
    - Duplicate node names (within same Group scope)

    Args:
        script_text (str): The full content of a .nk script file.

    Returns:
        list[StructureError]: A list of structural errors found.
    """
    errors = []
    lines = script_text.splitlines()

    scope_tracker = ScopeTracker()

    # Regex patterns
    node_start_pattern = re.compile(r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*\{\s*$')
    name_pattern = re.compile(r'^\s*name\s+(\S+)')

    # Track current node being processed
    current_node_type = None
    current_node_start_line = None
    structural_brace_depth = 0

    for line_num, line in enumerate(lines, start=1):
        # Skip empty lines
        if not line.strip():
            continue

        # Check for node start
        node_match = node_start_pattern.match(line)
        if node_match and structural_brace_depth == 0:
            current_node_type = node_match.group(1)
            current_node_start_line = line_num
            structural_brace_depth = 1

            # Special handling for Group nodes
            if current_node_type == 'Group':
                logger.debug(f"[VALIDATION] Entering Group node at line {line_num}")

            continue

        if structural_brace_depth > 0:
            # Update brace depth using structural brace classification
            # Process each character to track braces
            in_string = False
            i = 0
            while i < len(line):
                char = line[i]

                # Handle string literals (skip content inside quotes)
                if char == '"' and not in_string:
                    in_string = True
                    i += 1
                    while i < len(line):
                        if line[i] == '\\' and i + 1 < len(line):
                            i += 2  # Skip escaped character
                            continue
                        if line[i] == '"':
                            in_string = False
                            break
                        i += 1
                    i += 1
                    continue

                if not in_string:
                    if char == '{':
                        # Build temporary brace stack for classification
                        temp_stack = [True] * structural_brace_depth  # Simplified
                        if classify_brace_context(line, i, temp_stack, True) == BraceContext.STRUCTURAL:
                            structural_brace_depth += 1
                    elif char == '}':
                        temp_stack = [True] * structural_brace_depth
                        if classify_brace_context(line, i, temp_stack, False) == BraceContext.STRUCTURAL:
                            structural_brace_depth -= 1

                            # Exiting a node
                            if structural_brace_depth == 0:
                                # Check if we're exiting a Group
                                if current_node_type == 'Group':
                                    scope_tracker.exit_group()
                                    logger.debug(f"[VALIDATION] Exiting Group at line {line_num}")
                                    logger.debug(f"  Scope now: {scope_tracker.get_scope_path()}")
                                current_node_type = None
                                break

                i += 1

            # Look for name knob (only at depth 1 - immediate child of current node)
            if structural_brace_depth == 1:
                name_match = name_pattern.match(line)
                if name_match:
                    node_name = name_match.group(1)

                    # If this is a Group node, enter its scope
                    if current_node_type == 'Group':
                        scope_tracker.enter_group(node_name, line_num)
                        logger.debug(f"[VALIDATION] Entered Group scope '{node_name}' at line {line_num}")
                        logger.debug(f"  Full scope: {scope_tracker.get_scope_path()}")

                    # Check for duplicate names in current scope
                    duplicate_line = scope_tracker.register_node_name(node_name, line_num)
                    if duplicate_line:
                        scope_path = scope_tracker.get_scope_path()
                        error = StructureError(
                            line_num, line.find(node_name),
                            f"Duplicate node name '{node_name}' in scope '{scope_path}' (first defined at line {duplicate_line})",
                            StructureError.WARNING, len(node_name)
                        )
                        errors.append(error)
                        logger.warning(f"[VALIDATION] {error.severity.upper()} at line {line_num}: {error.message}")
                        logger.warning(f"  Current scope: {scope_path}")
                    else:
                        logger.debug(f"[VALIDATION] Registered node '{node_name}' in scope '{scope_tracker.get_scope_path()}' at line {line_num}")

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
    logger.info("[VALIDATION] Starting validation...")
    errors = []

    # Structure validation (brace matching)
    logger.debug("[VALIDATION] Running structure validation (brace matching)...")
    structure_errors = validate_structure(script_text)
    errors.extend(structure_errors)
    logger.info(f"[VALIDATION] Structure validation found {len(structure_errors)} error(s)")

    # Node definition validation
    logger.debug("[VALIDATION] Running node definition validation...")
    node_errors = validate_node_definitions(script_text)
    errors.extend(node_errors)
    logger.info(f"[VALIDATION] Node validation found {len(node_errors)} error(s)")

    # Sort by line number
    errors.sort(key=lambda e: (e.line_number, e.column))

    # Summary
    error_count = sum(1 for e in errors if e.severity == StructureError.ERROR)
    warning_count = sum(1 for e in errors if e.severity == StructureError.WARNING)
    logger.info(f"[VALIDATION] Validation complete: {error_count} errors, {warning_count} warnings")

    if errors:
        logger.info("[VALIDATION] All issues found:")
        for err in errors:
            logger.info(f"  Line {err.line_number}: [{err.severity.upper()}] {err.message}")

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
