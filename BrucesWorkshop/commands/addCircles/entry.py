import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_projectAndCircle'
CMD_NAME = 'Project Points and Draw Circles'
CMD_Description = 'Project all points from visible sketches into the current sketch and draw a dimensioned circle on each.'

IS_PROMOTED = False

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SketchModifyPanel'
COMMAND_BESIDE_ID = 'FusionMoveCommand'

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

DIAMETER = 'diameter'

local_handlers = []


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

    design = adsk.fusion.Design.cast(app.activeProduct)
    units = design.unitsManager.defaultLengthUnits if design else 'mm'
    inputs.addValueInput(
        DIAMETER,
        'Circle Diameter',
        units,
        adsk.core.ValueInput.createByString('10 mm')
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

    current_sketch = adsk.fusion.Sketch.cast(app.activeEditObject)
    if not current_sketch:
        ui.messageBox('A SKETCH must be active when running this command.', CMD_NAME)
        return

    inputs = args.command.commandInputs
    diameter_input = adsk.core.ValueCommandInput.cast(inputs.itemById(DIAMETER))
    radius_cm = diameter_input.value / 2.0   # value is always in cm internally

    circles    = current_sketch.sketchCurves.sketchCircles
    dimensions = current_sketch.sketchDimensions

    projected_count = 0
    circle_count    = 0

    # ------------------------------------------------------------------
    # Walk only sketches in the current component, skip the active one
    # and any that are not visible.
    # ------------------------------------------------------------------
    current_component = current_sketch.parentComponent

    for sketch in current_component.sketches:
            # Skip the sketch we are currently editing
            if sketch == current_sketch:
                continue

            # Skip invisible sketches
            if not sketch.isVisible:
                continue

            for sketch_pt in sketch.sketchPoints:
                # Skip the origin point that every sketch has at (0,0)
                if sketch_pt.geometry.x == 0.0 and sketch_pt.geometry.y == 0.0 and sketch_pt.geometry.z == 0.0:
                    # Only skip if it genuinely is the sketch-origin placeholder
                    if sketch_pt == sketch.originPoint:
                        continue

                # Project the point into the current sketch.
                # projectToSketch takes a SketchEntity and returns the projected entity.
                try:
                    projected = current_sketch.project(sketch_pt)
                except Exception as e:
                    futil.log(f'Failed to project point: {e}')
                    continue

                if not projected or projected.count == 0:
                    continue

                projected_count += 1

                # The projected entity is a SketchPoint; use its geometry for the circle centre.
                proj_pt = adsk.fusion.SketchPoint.cast(projected.item(0))
                if not proj_pt:
                    continue

                centre = proj_pt.geometry

                # Draw the circle
                circle = circles.addByCenterRadius(centre, radius_cm)
                circle_count += 1

                # Add a coincident constraint between the circle centre and the projected point
                current_sketch.geometricConstraints.addCoincident(
                    circle.centerSketchPoint, proj_pt
                )

                # Place the diameter dimension text slightly to the right of the circle
                dim_pt = adsk.core.Point3D.create(
                    centre.x + radius_cm * 1.5,
                    centre.y + radius_cm * 1.5,
                    0
                )
                dimensions.addDiameterDimension(circle, dim_pt, True)

    futil.log(
        f'{CMD_NAME}: projected {projected_count} points, '
        f'created {circle_count} circles in sketch "{current_sketch.name}".'
    )

    if circle_count == 0:
        ui.messageBox(
            'No points were found in any visible sketch to project.\n'
            'Make sure at least one other sketch is visible.',
            CMD_NAME
        )


def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    futil.log(f'{CMD_NAME} Validate Input Event')

    inputs = args.inputs
    diameter_input = adsk.core.ValueCommandInput.cast(inputs.itemById(DIAMETER))

    if not diameter_input.isValidExpression or diameter_input.value <= 0:
        args.areInputsValid = False
        return

    args.areInputsValid = True


def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Destroy Event')
    global local_handlers
    local_handlers = []
    futil.log('command destroy complete')