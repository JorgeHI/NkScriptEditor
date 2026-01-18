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
# Note: Callbacks are hardcoded as there's no Nuke API to retrieve them dynamically
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
# TODO: Make this dynamic in the future by querying knobs from a base node type
#       via Nuke API (e.g., create temp NoOp node and get its knobs)
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

# =============================================================================
# Node Types
# =============================================================================

# Default node types list - comprehensive list of standard Nuke nodes
# This can be refreshed from Nuke API via refresh_node_types() but that call
# is slow (nuke.nodeTypes(force_plugin_load=True) takes several seconds)
DEFAULT_NODE_TYPES = [
    'Add', 'AddChannels', 'AddMix', 'AddSTMap', 'AddTimeCode', 'AdjBBox', 'AmbientOcclusion',
    'Anaglyph', 'Annotations', 'AppendClip', 'ApplyLUT', 'ApplyMaterial', 'Assert', 'AttribGeo',
    'AudioRead', 'Axis', 'Axis2', 'Axis3', 'Axis4', 'BackdropNode', 'BakedPointCloud',
    'BakedPointCloudMesh', 'BasicMaterial', 'BasicSurface', 'Bezier', 'BigCat', 'Bilateral',
    'Bilateral2', 'Black', 'BlackOutside', 'Blend', 'BlendMat', 'BlinkBlur', 'BlinkFilterErode',
    'BlinkScript', 'BlockGPU', 'Blocky', 'Blur', 'Bokeh', 'BumpBoss', 'BumpMat', 'BurnIn',
    'CCorrect', 'CCrosstalk', 'CMSTestPattern', 'C_AlphaGenerator2_1', 'C_Bilateral2_1',
    'C_Blender2_1', 'C_Blur2_1', 'C_CameraIngest2_1', 'C_CameraSolver2_1', 'C_ColourMatcher2_1',
    'C_DisparityGenerator2_1', 'C_GenerateMap2_1', 'C_GlobalWarp2_1', 'C_RayRender2_1',
    'C_STMap2_1', 'C_SphericalTransform2_1', 'C_Stitcher2_1', 'C_Tracker2_1', 'Camera',
    'Camera2', 'Camera3', 'Camera4', 'CameraShake', 'CameraShake2', 'CameraShake3',
    'CameraTracker', 'CameraTracker1_0', 'CameraTrackerPointCloud', 'CameraTrackerPointCloud1_0',
    'Card', 'Card2', 'Card3D', 'CardObj', 'CatFileCreator', 'ChannelMerge', 'ChannelSelector',
    'Checker', 'CheckerBoard', 'CheckerBoard2', 'ChromaKeyer', 'Clamp', 'ClipTest', 'ColorBars',
    'ColorCorrect', 'ColorLookup', 'ColorMatrix', 'ColorTransfer', 'ColorTransferWrapper',
    'ColorWheel', 'Colorspace', 'Compare', 'CompareMetaData', 'Constant', 'ConstantShader',
    'ContactSheet', 'Convolve', 'Convolve2', 'Copy', 'CopyBBox', 'CopyCat', 'CopyMetaData',
    'CopyRectangle', 'CornerPin2D', 'Crop', 'CrosstalkGeo', 'Cryptomatte', 'Cube', 'CubeObj',
    'CurveTool', 'Cylinder', 'CylinderObj', 'DeInterlace', 'Deblur', 'DeepChannelBlanker',
    'DeepClip', 'DeepClipZ', 'DeepColorCorrect', 'DeepColorCorrect2', 'DeepCompare', 'DeepCrop',
    'DeepDeOverlap', 'DeepExpression', 'DeepFromFrames', 'DeepFromImage', 'DeepHoldout',
    'DeepHoldout2', 'DeepMask', 'DeepMerge', 'DeepMerge2', 'DeepOmit', 'DeepRead', 'DeepRecolor',
    'DeepReformat', 'DeepSample', 'DeepShift', 'DeepToImage', 'DeepToImage2', 'DeepToPoints',
    'DeepTransform', 'DeepVolumeMaker', 'DeepWrite', 'Defocus', 'DegrainBlue', 'DegrainSimple',
    'Denoise2', 'DepthGenerator', 'DepthGenerator1_0', 'DepthToPoints', 'DepthToPosition',
    'Difference', 'Diffuse', 'Dilate', 'DirBlur', 'DirBlurWrapper', 'DirectLight', 'DirectLight1',
    'DiskCache', 'DisplaceGeo', 'Displacement', 'Dissolve', 'Dither', 'Dot', 'DrawCursorShaderOp',
    'DropShadow', 'DualBlend', 'DustBust', 'EXPTool', 'EdgeBlur', 'EdgeDetect', 'EdgeDetectWrapper',
    'EdgeExtend', 'EdgeScatter', 'EditGeo', 'Emboss', 'Emission', 'Encryptomatte', 'Environment',
    'EnvironmentLight', 'Erode', 'ErrorIop', 'ExecuteTreeMT', 'Expression', 'FFT', 'FFTMultiply',
    'F_Align', 'F_DeFlicker2', 'F_DeGrain', 'F_DeNoise', 'F_Kronos', 'F_MatchGrade', 'F_MotionBlur',
    'F_ReGrain', 'F_RigRemoval', 'F_Steadiness', 'F_VectorGenerator', 'F_WireRemoval',
    'FieldAttract', 'FieldCellNoise', 'FieldConstant', 'FieldCrop', 'FieldCurves', 'FieldDeform',
    'FieldFractal', 'FieldGrid', 'FieldImage', 'FieldInvert', 'FieldLookAt', 'FieldMath',
    'FieldMerge', 'FieldMix', 'FieldNoise', 'FieldPosition', 'FieldRadial', 'FieldRamp',
    'FieldRender', 'FieldSelect', 'FieldShape', 'FieldShapeModify', 'FieldShapeToDensity',
    'FieldShapeToPosition', 'FieldTransform', 'FieldTrilinearWarp', 'FieldVolume',
    'FieldVolumeWrite', 'FieldVortex', 'FieldVortexRing', 'Fill', 'FillMat', 'FillShader',
    'FilterErode', 'FishEye', 'Flare', 'FloodFill', 'FnNukeMultiTypeOpDeepOp',
    'FnNukeMultiTypeOpGeoOp', 'FnNukeMultiTypeOpGeomOp', 'FnNukeMultiTypeOpIop',
    'FnNukeMultiTypeOpParticleOp', 'Fog', 'FrameBlend', 'FrameHold', 'FrameRange', 'FromDeep',
    'GPUFileShader', 'GPUOp', 'Gamma', 'GenerateLUT', 'GenerateLUTGeo', 'GeoActivation',
    'GeoBakedMesh', 'GeoBakedPointCloud', 'GeoBakedPointCloudMesh', 'GeoBakedPoints',
    'GeoBindMaterial', 'GeoCamera', 'GeoCameraTrackerPoints', 'GeoCameraTrackerPoints1_0',
    'GeoCard', 'GeoClearMask', 'GeoCollection', 'GeoColorSpace', 'GeoCompare', 'GeoConstrain',
    'GeoCube', 'GeoCylinder', 'GeoDeletePoints', 'GeoDiskLight', 'GeoDisplace', 'GeoDistantLight',
    'GeoDomeLight', 'GeoDrawMode', 'GeoDuplicate', 'GeoEditLight', 'GeoExport', 'GeoFieldMesh',
    'GeoFieldSet', 'GeoFieldWarp', 'GeoGeneratePoints', 'GeoGrade', 'GeoImport', 'GeoInstance',
    'GeoMask', 'GeoMerge', 'GeoNoise', 'GeoNormals', 'GeoPointInstancer', 'GeoPoints',
    'GeoPointsToMesh', 'GeoProjectUV', 'GeoPython', 'GeoRadialWarp', 'GeoReference', 'GeoScene',
    'GeoScope', 'GeoScript', 'GeoSelect', 'GeoSelection', 'GeoSetVariant', 'GeoSphere',
    'GeoSphereLight', 'GeoSplat', 'GeoStageEdit', 'GeoTransform', 'GeoTriangle',
    'GeoTrilinearWarp', 'GeoTwist', 'GeoViewScene', 'GeoVisibility', 'GeoXform', 'GeomNode',
    'GeomOpTester', 'Gizmo', 'Glint', 'Glow', 'Glow2', 'GodRays', 'Grade', 'Grain', 'Grain2',
    'Grid', 'GridWarp', 'GridWarp2', 'GridWarp3', 'GridWarpTracker', 'Group', 'HSVTool',
    'HistEQ', 'Histogram', 'HueCorrect', 'HueKeyer', 'HueShift', 'IBK', 'IBK2Gizmo', 'IBKColour',
    'IBKColourV3', 'IBKEdge', 'IBKGizmo', 'IBKGizmoV3', 'IBKSFill', 'IBKSplit', 'IDistort',
    'IT8_Reader', 'IT8_Writer', 'ImageField', 'Inference', 'Inpaint', 'Inpaint2', 'Input',
    'InternalTimelineDefaultInput', 'InvFFT', 'Invert', 'JoinViews', 'Keyer', 'Keylight',
    'Keymix', 'Kronos', 'Laplacian', 'LayerContactSheet', 'LensDistortion', 'LensDistortion1_0',
    'LensDistortion2', 'LevelSet', 'Light', 'Light2', 'Light3', 'Light4', 'LightWrap',
    'LiveGroup', 'LiveInput', 'Log2Lin', 'LogGeo', 'LookupGeo', 'MakeLatLongMap', 'MarkerRemoval',
    'MatchGrade', 'Matrix', 'Median', 'Merge', 'Merge2', 'MergeExpression', 'MergeGeo',
    'MergeLayerShader', 'MergeMat', 'MeshGeo', 'MinColor', 'MindRead', 'Mirror', 'Mirror2',
    'MixViews', 'ModelBuilder', 'ModelBuilderGeo', 'Modeler', 'Modeler1_0', 'ModifyMetaData',
    'ModifyRIB', 'MotionBlur', 'MotionBlur2D', 'MotionBlur3D', 'MtlXStandardSurface',
    'MultiTexture', 'Multiply', 'NoOp', 'NoProxy', 'NoTimeBlur', 'NodeWrapper', 'Noise',
    'Normals', 'OCIOCDLTransform', 'OCIOColorSpace', 'OCIODisplay', 'OCIOFileTransform',
    'OCIOLogConvert', 'OCIOLookTransform', 'OCIONamedTransform', 'OFlow2', 'OneView',
    'OpStatisticsOp', 'Output', 'PLogLin', 'PSDMerge', 'Paint', 'PanelNode',
    'ParticleAttractToSphere', 'ParticleBlinkScript', 'ParticleBlinkScriptRender',
    'ParticleBounce', 'ParticleCache', 'ParticleColorByAge', 'ParticleConstrainToSphere',
    'ParticleCurve', 'ParticleCylinderFlow', 'ParticleDirection', 'ParticleDirectionalForce',
    'ParticleDistributeSphere', 'ParticleDrag', 'ParticleDrag2', 'ParticleEmitter',
    'ParticleExpression', 'ParticleFieldForce', 'ParticleFlock', 'ParticleFuse',
    'ParticleGravity', 'ParticleGrid', 'ParticleHelixFlow', 'ParticleInfo', 'ParticleKill',
    'ParticleLookAt', 'ParticleMerge', 'ParticleMotionAlign', 'ParticleMove',
    'ParticlePointForce', 'ParticleProjectDisplace', 'ParticleProjectImage', 'ParticleRender',
    'ParticleSettings', 'ParticleShockWave', 'ParticleSpawn', 'ParticleSpeedLimit',
    'ParticleSystem', 'ParticleToGeo', 'ParticleToImage', 'ParticleTurbulence', 'ParticleVortex',
    'ParticleWind', 'PerspDistort', 'Phong', 'PixelStat', 'PixelSum', 'PlanarTracker',
    'PlanarTracker1_0', 'PointCloudGenerator', 'PointCloudGenerator1_0', 'PointLight',
    'PointsTo3D', 'PoissonMesh', 'Position', 'PositionToPoints', 'PositionToPoints2',
    'PostageStamp', 'Posterize', 'Precomp', 'Preferences', 'Premult', 'PreviewSurface',
    'Primatte', 'Primatte3', 'PrimatteAdjustLighting', 'PrintHash', 'PrintMetaData', 'ProcGeo',
    'Profile', 'Project3D', 'Project3D2', 'Project3DShader', 'ProjectionSolver',
    'ProjectionSolver1_0', 'PythonGeo', 'Radial', 'RadialDistort', 'Ramp', 'RayRender',
    'ReConverge', 'ReLight', 'Read', 'ReadGeo', 'ReadGeo2', 'Reconcile3D', 'Rectangle',
    'Reflection', 'ReflectiveSurface', 'Reformat', 'Refraction', 'Remove', 'RendermanShader',
    'Retime', 'RolloffContrast', 'Roto', 'RotoPaint', 'STMap', 'Sampler', 'Saturation',
    'ScanlineRender', 'ScanlineRender2', 'ScannedGrain', 'Scene', 'SceneOpNode', 'Sharpen',
    'Shuffle', 'Shuffle1', 'Shuffle2', 'ShuffleCopy', 'ShuffleViews', 'SideBySide', 'SimpleAxis',
    'SmartVector', 'SoftClip', 'Soften', 'Sparkles', 'Specular', 'Sphere', 'SphereObj',
    'SphereToLatLongMap', 'SphericalMap', 'SphericalTransform', 'SphericalTransform2',
    'SplatRender', 'SplineWarp', 'SplineWarp2', 'SplineWarp3', 'SpotLight1', 'Spotlight',
    'StabTrack', 'Stabilize2D', 'StarField', 'StickyNote', 'SurfaceOptions', 'Switch',
    'TVIscale', 'TVIscale2', 'TemporalMedian', 'Text', 'Text2', 'TextureFile', 'TextureMap',
    'TextureSampler', 'Tile', 'TimeBlend', 'TimeBlur', 'TimeClip', 'TimeDissolve', 'TimeEcho',
    'TimeOffset', 'TimeShift', 'TimeToDepth', 'TimeWarp', 'ToDeep', 'Toe2', 'Tracker',
    'Tracker3', 'Tracker4', 'Transform', 'Transform3D', 'TransformGeo', 'TransformMasked',
    'Transmission', 'Trilinear', 'Twist', 'TwistGeo', 'UVProject', 'UVTile2', 'Ultimatte',
    'UnmultColor', 'Unpremult', 'UnrealReader', 'Unwrap', 'UpRez', 'Upscale', 'VariableGroup',
    'VariableSwitch', 'VectorBlur', 'VectorBlur2', 'VectorCornerPin', 'VectorDistort',
    'VectorGenerator', 'VectorToMotion', 'Vectorfield', 'ViewMetaData', 'Viewer',
    'ViewerCaptureOp', 'ViewerChannelSelector', 'ViewerClipTest', 'ViewerDitherDisable',
    'ViewerDitherHighFrequency', 'ViewerDitherLowFrequency', 'ViewerGain', 'ViewerGamma',
    'ViewerInterlacedStereo', 'ViewerLUT', 'ViewerProcess_1DLUT', 'ViewerProcess_None',
    'ViewerSaturation', 'ViewerScopeOp', 'ViewerWipe', 'VolumeRays', 'Wireframe',
    'WireframeShader', 'Write', 'WriteGeo', 'ZBlur', 'ZComp', 'ZDefocus', 'ZDefocus2',
    'ZFDefocus', 'ZMerge', 'ZRMerge', 'ZSlice', 'add32p', 'objReaderObj', 'remove32p',
]

# Active node types list - starts with defaults, can be refreshed from Nuke API
_node_types_cache = None


def get_node_types():
    """
    Get available node types for autocomplete.

    Returns the cached list if available, otherwise returns the default list.
    Use refresh_node_types() to update from Nuke API.

    Returns:
        list[str]: List of node type names
    """
    global _node_types_cache
    if _node_types_cache is not None:
        return _node_types_cache
    return DEFAULT_NODE_TYPES


def refresh_node_types():
    """
    Refresh node types list from Nuke API.

    This calls nuke.nodeTypes(force_plugin_load=True) which can take several
    seconds as it loads all plugins. Should be called explicitly by user action,
    not automatically on startup.

    Returns:
        int: Number of node types loaded, or -1 on error
    """
    global _node_types_cache
    try:
        _node_types_cache = nuke.nodeTypes(force_plugin_load=True)
        logger.info(f"Refreshed node types from Nuke API: {len(_node_types_cache)} types loaded")
        return len(_node_types_cache)
    except Exception as e:
        logger.warning(f"Failed to refresh node types from Nuke API: {e}")
        return -1


def reset_node_types_to_default():
    """Reset node types to the default list."""
    global _node_types_cache
    _node_types_cache = None
    logger.debug("Node types reset to default list")


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
        # Use Qt.Tool with Qt.WindowDoesNotAcceptFocus to prevent stealing focus from editor
        # This ensures keyboard events stay with the editor while popup is visible
        self.setWindowFlags(
            QtCore.Qt.Tool |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.WindowDoesNotAcceptFocus
        )
        # NoFocus policy prevents popup from taking focus on any interaction
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setMouseTracking(True)
        # Prevent the widget from activating (taking focus)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)

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

        self.setMaximumHeight(200)
        self.setMinimumWidth(250)

    def mousePressEvent(self, event):
        """Handle mouse press to select completion without taking focus."""
        item = self.itemAt(event.pos())
        if item:
            completion_text = item.data(QtCore.Qt.UserRole) or item.text()
            logger.debug(f"Autocomplete item clicked: {completion_text}")
            self.completionSelected.emit(completion_text)
            self.hide()
        else:
            # Click outside items - hide popup
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
        self._current_context = None  # Store context for completion insertion

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

        # If at root level, suggest node types (loaded dynamically from Nuke API)
        elif not context['in_node']:
            for node_type in get_node_types():
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
            self._current_context = None
            return

        # Store context for use in completion insertion
        self._current_context = context

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

        # Check if this is a node type completion (at root level, not inside a node)
        is_node_type = (
            self._current_context is not None and
            not self._current_context.get('in_node', True) and
            text in get_node_types()
        )

        if is_node_type:
            # Insert full node definition structure:
            # NodeType {
            #     <cursor here>
            # }
            indent = " "  # Single space indent for .nk files
            node_text = f"{text} {{\n{indent}\n}}"
            cursor.insertText(node_text)
            # Move cursor to end of indent on the middle line (2 chars back: \n and })
            cursor.movePosition(QtGui.QTextCursor.Left)  # before }
            cursor.movePosition(QtGui.QTextCursor.Left)  # before \n (now at end of indent line)
            self.editor.setTextCursor(cursor)
            logger.debug(f"Inserted node type with brackets: {text}")
        else:
            # Regular completion - just insert the text
            cursor.insertText(text)
            self.editor.setTextCursor(cursor)
            logger.debug(f"Inserted completion text: {text}")

        # Clear stored context
        self._current_context = None

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
