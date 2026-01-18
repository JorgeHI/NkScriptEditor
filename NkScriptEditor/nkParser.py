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
Parser utilities for .nk (Nuke script) files.

This module provides functions to parse .nk scripts and extract node information
including node types, names, and their line positions. This is useful for error
detection when loading scripts fails partway through.
"""
import re
from NkScriptEditor import nkUtils

logger = nkUtils.getLogger(__name__)


class NodeInfo:
    """Represents information about a node parsed from a .nk script."""

    def __init__(self, node_type, name, start_line, end_line):
        """
        Args:
            node_type (str): The type of node (e.g., 'Grade', 'Merge', 'Root')
            name (str): The node's name as defined by the 'name' knob
            start_line (int): The 1-based line number where the node definition starts
            end_line (int): The 1-based line number where the node definition ends
        """
        self.node_type = node_type
        self.name = name
        self.start_line = start_line
        self.end_line = end_line

    def __repr__(self):
        return f"NodeInfo({self.node_type}, '{self.name}', lines {self.start_line}-{self.end_line})"


def parse_nk_script(script_text):
    """
    Parse a .nk script and extract information about all nodes.

    This parser handles the TCL-based .nk format used by Nuke, tracking
    nested braces to properly identify node boundaries.

    Args:
        script_text (str): The full content of a .nk script file.

    Returns:
        list[NodeInfo]: A list of NodeInfo objects for each node found,
                        ordered by their position in the script.
    """
    lines = script_text.splitlines()
    nodes = []

    # Regex to match node definition start: "NodeType {" or "NodeType {"
    node_start_pattern = re.compile(r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*\{\s*$')
    # Regex to match name knob: "name NodeName"
    name_pattern = re.compile(r'^\s*name\s+(\S+)')

    i = 0
    while i < len(lines):
        line = lines[i]
        match = node_start_pattern.match(line)

        if match:
            node_type = match.group(1)
            start_line = i + 1  # 1-based line number
            node_name = None
            brace_count = 1

            # Find the matching closing brace and extract the name
            j = i + 1
            while j < len(lines) and brace_count > 0:
                inner_line = lines[j]

                # Track brace nesting (simplified - doesn't handle braces in strings)
                brace_count += inner_line.count('{') - inner_line.count('}')

                # Look for name knob (only at top level of this node)
                if node_name is None and brace_count == 1:
                    name_match = name_pattern.match(inner_line)
                    if name_match:
                        node_name = name_match.group(1)

                j += 1

            end_line = j  # 1-based line number (j is already past the closing brace)

            # Use node_type as fallback if no name found
            if node_name is None:
                node_name = node_type

            nodes.append(NodeInfo(node_type, node_name, start_line, end_line))
            i = j
        else:
            i += 1

    return nodes


def find_node_by_name(nodes, name):
    """
    Find a node by its name in a list of NodeInfo objects.

    Args:
        nodes (list[NodeInfo]): List of parsed nodes
        name (str): The node name to search for

    Returns:
        NodeInfo or None: The matching NodeInfo, or None if not found
    """
    for node in nodes:
        if node.name == name:
            return node
    return None


def find_last_matching_node(nodes, existing_node_names):
    """
    Find the last node in the script that exists in the given set of names.

    This is used to determine where a script load failed: we compare the nodes
    that were successfully loaded in Nuke against the nodes defined in the script,
    and find the last one that was loaded.

    Args:
        nodes (list[NodeInfo]): List of all nodes parsed from the script
        existing_node_names (set[str]): Names of nodes that actually exist in Nuke

    Returns:
        NodeInfo or None: The last node from the script that exists in Nuke,
                          or None if no match found.
    """
    last_match = None
    for node in nodes:
        if node.name in existing_node_names:
            last_match = node
    return last_match


def find_first_missing_node(nodes, existing_node_names):
    """
    Find the first node in the script that does NOT exist in Nuke.

    This identifies the node that likely failed to load.

    Args:
        nodes (list[NodeInfo]): List of all nodes parsed from the script
        existing_node_names (set[str]): Names of nodes that actually exist in Nuke

    Returns:
        NodeInfo or None: The first node from the script that doesn't exist,
                          or None if all nodes exist.
    """
    for node in nodes:
        # Skip Root node as it's handled specially
        if node.node_type == 'Root':
            continue
        if node.name not in existing_node_names:
            return node
    return None


def parse_error_line_from_message(error_message):
    """
    Attempt to extract a line number from a Nuke error message.

    Nuke error messages sometimes include line information in various formats:
    - "line 42: error message"
    - "Line 42: error message"
    - "Error at line 42"
    - "(line 42)"

    Args:
        error_message (str): The error message from a Nuke exception

    Returns:
        int or None: The extracted line number (1-based), or None if not found
    """
    if not error_message:
        return None

    # Try various patterns
    patterns = [
        r'[Ll]ine\s+(\d+)',  # "line 42" or "Line 42"
        r'at line\s+(\d+)',  # "at line 42"
        r'\(line\s+(\d+)\)', # "(line 42)"
        r':(\d+):',          # ":42:" style
    ]

    for pattern in patterns:
        match = re.search(pattern, error_message)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue

    return None


def get_nodes_in_order(script_text):
    """
    Get a list of (node_name, start_line, end_line) tuples in script order.

    This is a convenience function that returns just the essential info
    for error detection.

    Args:
        script_text (str): The full content of a .nk script file.

    Returns:
        list[tuple]: List of (name, start_line, end_line) tuples
    """
    nodes = parse_nk_script(script_text)
    return [(n.name, n.start_line, n.end_line) for n in nodes]
