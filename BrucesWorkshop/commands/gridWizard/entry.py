import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_circleGrid'
CMD_NAME = 'Grid Wizard'
CMD_Description = 'Create a construction grid in the current sketch from a selected origin point.'

IS_PROMOTED = False

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SketchModifyPanel'
COMMAND_BESIDE_ID = 'FusionMoveCommand'

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

POINT_SELECTION = 'point_selection'
X_OFFSETS      = 'x_offsets'
Y_OFFSETS      = 'y_offsets'

DEFAULT_OFFSETS = [0, 20, 120, 150, 180, 210, 320]

local_handlers = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def offsets_to_str(offsets):
    """Convert list of mm values to a comma-separated string."""
    return ', '.join(str(v) for v in offsets)


def parse_offsets(text):
    """
    Parse a comma- or space-separated string of numbers into a sorted list of
    unique floats.  Returns (list, error_string).  error_string is None on success.
    """
    import re
    tokens = re.split(r'[\s,]+', text.strip())
    values = []
    for tok in tokens:
        if not tok:
            continue
        try:
            values.append(float(tok))
        except ValueError:
            return None, f'"{tok}" is not a valid number'
    if len(values) < 2:
        return None, 'At least 2 offset values are required'
    values = sorted(set(values))
    if values[0] < 0:
        return None, 'Offset values must be >= 0'
    return values, None


def mm_to_cm(mm):
    return mm / 10.0


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------

def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)
    futil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
    control.isPromoted = IS_PROMOTED


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_control:
        command_control.deleteMe()
    if command_definition:
        command_definition.deleteMe()


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f'{CMD_NAME} Command Created Event')

    inputs = args.command.commandInputs

    # Origin point selection
    point_sel = inputs.addSelectionInput(
        POINT_SELECTION,
        'Origin Point',
        'Select the sketch point to use as the grid origin'
    )
    point_sel.addSelectionFilter('SketchPoints')
    point_sel.setSelectionLimits(1, 1)

    # X offsets text box
    inputs.addStringValueInput(
        X_OFFSETS,
        'X Offsets (mm)',
        offsets_to_str(DEFAULT_OFFSETS)
    )

    # Y offsets text box
    inputs.addStringValueInput(
        Y_OFFSETS,
        'Y Offsets (mm)',
        offsets_to_str(DEFAULT_OFFSETS)
    )

    futil.add_handler(args.command.execute,        command_execute,        local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy,        command_destroy,        local_handlers=local_handlers)


def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')

    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    if not design:
        ui.messageBox('The DESIGN workspace must be active when running this command.', CMD_NAME)
        return

    sketch = adsk.fusion.Sketch.cast(app.activeEditObject)
    if not sketch:
        ui.messageBox('A SKETCH must be active when running this command.', CMD_NAME)
        return

    inputs = args.command.commandInputs

    sel_input  = adsk.core.SelectionCommandInput.cast(inputs.itemById(POINT_SELECTION))
    x_input    = adsk.core.StringValueCommandInput.cast(inputs.itemById(X_OFFSETS))
    y_input    = adsk.core.StringValueCommandInput.cast(inputs.itemById(Y_OFFSETS))

    x_offsets, _ = parse_offsets(x_input.value)
    y_offsets, _ = parse_offsets(y_input.value)

    # Origin in cm (Fusion internal units)
    origin_pt   = adsk.fusion.SketchPoint.cast(sel_input.selection(0).entity)
    ox          = origin_pt.geometry.x
    oy          = origin_pt.geometry.y

    # Derived extents
    max_x_cm = ox + mm_to_cm(x_offsets[-1])
    max_y_cm = oy + mm_to_cm(y_offsets[-1])

    constraints  = sketch.geometricConstraints
    dimensions   = sketch.sketchDimensions
    lines        = sketch.sketchCurves.sketchLines
    points_col   = sketch.sketchPoints

    # ------------------------------------------------------------------
    # 1. Outer rectangle (construction geometry)
    #    Corners: origin -> (max_x, origin_y) -> (max_x, max_y) -> (origin_x, max_y)
    # ------------------------------------------------------------------
    p_bl = adsk.core.Point3D.create(ox,       oy,       0)   # bottom-left
    p_br = adsk.core.Point3D.create(max_x_cm, oy,       0)   # bottom-right
    p_tr = adsk.core.Point3D.create(max_x_cm, max_y_cm, 0)   # top-right
    p_tl = adsk.core.Point3D.create(ox,       max_y_cm, 0)   # top-left

    bottom = lines.addByTwoPoints(p_bl, p_br)
    right  = lines.addByTwoPoints(p_br, p_tr)
    top    = lines.addByTwoPoints(p_tr, p_tl)
    left   = lines.addByTwoPoints(p_tl, p_bl)

    for edge in (bottom, right, top, left):
        edge.isConstruction = True

    # Horizontal constraint on bottom edge only (no vertical on left)
    constraints.addHorizontal(bottom)

    # Coincident constraints joining adjacent rectangle edges at each corner
    # (bottom-left is the free/origin corner — no constraint added there)
    constraints.addCoincident(bottom.endSketchPoint,  right.startSketchPoint)   # bottom-right
    constraints.addCoincident(right.endSketchPoint,   top.startSketchPoint)     # top-right
    constraints.addCoincident(top.endSketchPoint,     left.startSketchPoint)    # top-left
    constraints.addCoincident(left.endSketchPoint,    bottom.startSketchPoint)  # closes back to bottom-left

    # Perpendicular constraints at all corners except bottom-left
    constraints.addPerpendicular(bottom, right)   # bottom-right corner
    constraints.addPerpendicular(right,  top)     # top-right corner
    constraints.addPerpendicular(top,    left)    # top-left corner

    # Driving dimensions for the width (bottom) and height (left) edges
    dim_width_pt  = adsk.core.Point3D.create(
        ox + mm_to_cm(x_offsets[-1] / 2.0), oy - mm_to_cm(15), 0
    )
    dim_height_pt = adsk.core.Point3D.create(
        ox - mm_to_cm(15), oy + mm_to_cm(y_offsets[-1] / 2.0), 0
    )
    dimensions.addDistanceDimension(
        bottom.startSketchPoint, bottom.endSketchPoint,
        adsk.fusion.DimensionOrientations.AlignedDimensionOrientation,
        dim_width_pt, True
    )
    dimensions.addDistanceDimension(
        left.endSketchPoint, left.startSketchPoint,
        adsk.fusion.DimensionOrientations.AlignedDimensionOrientation,
        dim_height_pt, True
    )

    # ------------------------------------------------------------------
    # 2. Vertical construction lines for interior X offsets (skip first & last)
    # ------------------------------------------------------------------
    x_interior = x_offsets[1:-1]   # drop 0 and max_x

    x_lines = []   # store for intersection use
    for dx_mm in x_interior:
        x_cm = ox + mm_to_cm(dx_mm)
        pt_bot = adsk.core.Point3D.create(x_cm, oy,       0)
        pt_top = adsk.core.Point3D.create(x_cm, max_y_cm, 0)
        vline  = lines.addByTwoPoints(pt_bot, pt_top)
        vline.isConstruction = True

        # Coincident: bottom end on bottom edge, top end on top edge
        constraints.addCoincident(vline.startSketchPoint, bottom)
        constraints.addCoincident(vline.endSketchPoint,   top)

        # Vertical constraint on the line itself
        # no constraints.addVertical(vline)

        # Horizontal dimension from left edge to this line (measured at bottom)
        dim_pt = adsk.core.Point3D.create(
            ox + mm_to_cm(dx_mm / 2.0), oy - mm_to_cm(10), 0
        )
        dimensions.addOffsetDimension(
            left,
            vline,
            dim_pt,
            True   # isDriving
        )

        x_lines.append((dx_mm, vline))

    # ------------------------------------------------------------------
    # 3. Horizontal construction lines for interior Y offsets (skip first & last)
    # ------------------------------------------------------------------
    y_interior = y_offsets[1:-1]

    y_lines = []
    for dy_mm in y_interior:
        y_cm = oy + mm_to_cm(dy_mm)
        pt_lft = adsk.core.Point3D.create(ox,       y_cm, 0)
        pt_rgt = adsk.core.Point3D.create(max_x_cm, y_cm, 0)
        hline  = lines.addByTwoPoints(pt_lft, pt_rgt)
        hline.isConstruction = True

        # Coincident: left end on left edge, right end on right edge
        constraints.addCoincident(hline.startSketchPoint, left)
        constraints.addCoincident(hline.endSketchPoint,   right)

        # Horizontal constraint on the line itself
        # no constraints.addHorizontal(hline)

        # Vertical dimension from bottom edge to this line (measured at left)
        dim_pt = adsk.core.Point3D.create(
            ox - mm_to_cm(10), oy + mm_to_cm(dy_mm / 2.0), 0
        )
        dimensions.addOffsetDimension(
            bottom,
            hline,
            dim_pt,
            True   # isDriving
        )

        y_lines.append((dy_mm, hline))

    # ------------------------------------------------------------------
    # 4. Construction points at every grid intersection
    #
    #    Intersections occur at:
    #      - all x_offsets  x  all y_offsets
    #    The corners (0,0), (0,max_y), (max_x,0), (max_x,max_y) are already
    #    created as rectangle corner points, so we reuse those.
    #    Other edge points land on rectangle edges.
    #    Interior points land on two crossing construction lines.
    # ------------------------------------------------------------------

    # Helper: find a SketchLine in our sets by offset value
    def get_x_line(dx_mm):
        for v, l in x_lines:
            if v == dx_mm:
                return l
        return None

    def get_y_line(dy_mm):
        for v, l in y_lines:
            if v == dy_mm:
                return l
        return None

    for dx_mm in x_offsets:
        for dy_mm in y_offsets:
            x_cm = ox + mm_to_cm(dx_mm)
            y_cm = oy + mm_to_cm(dy_mm)
            pt   = points_col.add(adsk.core.Point3D.create(x_cm, y_cm, 0))

            # Determine which geometry to pin the point to
            is_left   = (dx_mm == x_offsets[0])
            is_right  = (dx_mm == x_offsets[-1])
            is_bottom = (dy_mm == y_offsets[0])
            is_top    = (dy_mm == y_offsets[-1])

            if is_left and is_bottom:
                constraints.addCoincident(pt, bottom.startSketchPoint)

            elif is_right and is_bottom:
                constraints.addCoincident(pt, bottom.endSketchPoint)

            elif is_right and is_top:
                constraints.addCoincident(pt, top.startSketchPoint)

            elif is_left and is_top:
                constraints.addCoincident(pt, top.endSketchPoint)

            elif is_bottom:
                vl = get_x_line(dx_mm)
                if vl:
                    constraints.addCoincident(pt, vl.startSketchPoint)

            elif is_top:
                vl = get_x_line(dx_mm)
                if vl:
                    constraints.addCoincident(pt, vl.endSketchPoint)

            elif is_left:
                hl = get_y_line(dy_mm)
                if hl:
                    constraints.addCoincident(pt, hl.startSketchPoint)

            elif is_right:
                hl = get_y_line(dy_mm)
                if hl:
                    constraints.addCoincident(pt, hl.endSketchPoint)

            else:
                # Interior: coincident with both crossing construction lines
                vl = get_x_line(dx_mm)
                hl = get_y_line(dy_mm)
                if vl:
                    constraints.addCoincident(pt, vl)
                if hl:
                    constraints.addCoincident(pt, hl)

    futil.log(f'{CMD_NAME}: grid complete in sketch "{sketch.name}".')


def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    futil.log(f'{CMD_NAME} Validate Input Event')

    inputs = args.inputs

    sel_input = adsk.core.SelectionCommandInput.cast(inputs.itemById(POINT_SELECTION))
    x_input   = adsk.core.StringValueCommandInput.cast(inputs.itemById(X_OFFSETS))
    y_input   = adsk.core.StringValueCommandInput.cast(inputs.itemById(Y_OFFSETS))

    if sel_input.selectionCount < 1:
        args.areInputsValid = False
        return

    _, x_err = parse_offsets(x_input.value)
    if x_err:
        args.areInputsValid = False
        return

    _, y_err = parse_offsets(y_input.value)
    if y_err:
        args.areInputsValid = False
        return

    args.areInputsValid = True


def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Destroy Event')
    global local_handlers
    local_handlers = []
    futil.log('command destroy complete')