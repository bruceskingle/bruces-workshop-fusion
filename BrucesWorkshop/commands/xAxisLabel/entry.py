import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui  = app.userInterface

CMD_ID          = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_quickSketchText'
CMD_NAME        = 'X Axis Label'
CMD_Description = 'Creates a Simplex.shx text label (6mm high, 15mm tall box) in the active sketch, constrained by its top-centre to a selected sketch point.'

IS_PROMOTED = False

WORKSPACE_ID      = 'FusionSolidEnvironment'
PANEL_ID          = 'SketchCreatePanel'
COMMAND_BESIDE_ID = 'SketchText'

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

TEXT_INPUT_ID  = 'text_input'
POINT_INPUT_ID = 'point_input'

local_handlers = []


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------

def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)
    futil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel     = workspace.toolbarPanels.itemById(PANEL_ID)
    control   = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
    control.isPromoted = IS_PROMOTED


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel     = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control    = panel.controls.itemById(CMD_ID)
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

    # Text input first so it receives focus by default
    inputs.addStringValueInput(TEXT_INPUT_ID, 'Label Text', '')

    # Point selection input
    point_input = inputs.addSelectionInput(POINT_INPUT_ID, 'Anchor Point', 'Select a sketch point for the top-centre of the text')
    point_input.addSelectionFilter('SketchPoints')
    point_input.setSelectionLimits(1, 1)

    # Pre-populate with any already-selected sketch point
    sel = ui.activeSelections
    if sel.count > 0:
        for i in range(sel.count):
            entity = sel.item(i).entity
            if isinstance(entity, adsk.fusion.SketchPoint):
                point_input.addSelection(entity)
                break


    futil.add_handler(args.command.execute,        command_execute,        local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy,        command_destroy,        local_handlers=local_handlers)


def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox('The DESIGN workspace must be active when running this command.', CMD_NAME)
        return

    sketch = adsk.fusion.Sketch.cast(design.activeEditObject)
    if not sketch:
        ui.messageBox('A SKETCH must be active when running this command.', CMD_NAME)
        return

    inputs    = args.command.commandInputs
    inputText = adsk.core.StringValueCommandInput.cast(inputs.itemById(TEXT_INPUT_ID)).value.strip()
    if not inputText:
        return

    point_input   = adsk.core.SelectionCommandInput.cast(inputs.itemById(POINT_INPUT_ID))
    selectedPoint = adsk.fusion.SketchPoint.cast(point_input.selection(0).entity)

    fontName          = 'Simplex.shx'
    textHeight        = 0.6   # 6mm in cm
    boxHeight         = 1.5   # 15mm in cm
    charWidthEstimate = textHeight * 0.65
    estimatedWidth    = max(len(inputText) * charWidthEstimate, textHeight)

    # Place far from origin so the midpoint constraint has work to do
    ptX, ptY = 1000.0, 1000.0

    cornerPoint = adsk.core.Point3D.create(ptX, ptY, 0)
    extentPoint = adsk.core.Point3D.create(ptX + estimatedWidth, ptY + boxHeight, 0)

    texts     = sketch.sketchTexts
    textInput = texts.createInput2(inputText, textHeight)
    textInput.setAsMultiLine(
        cornerPoint, extentPoint,
        adsk.core.HorizontalAlignments.CenterHorizontalAlignment,
        adsk.core.VerticalAlignments.BottomVerticalAlignment,
        0
    )
    textInput.fontName         = fontName
    textInput.isHorizontalFlip = False
    textInput.isVerticalFlip   = False

    sketchText = texts.add(textInput)

    # Ensure the selected point belongs to this sketch; project it in if not
    if selectedPoint.parentSketch != sketch:
        projected = sketch.project(selectedPoint)
        if projected and projected.count > 0:
            selectedPoint = adsk.fusion.SketchPoint.cast(projected.item(0))

    # Find the top boundary line (highest average Y) and constrain
    # the selected point to its midpoint — top-centre of the text box
    definition = sketchText.definition
    rectLines  = definition.rectangleLines

    topLine = None
    maxY    = float('-inf')
    for line in rectLines:
        avgY = (line.startSketchPoint.geometry.y +
                line.endSketchPoint.geometry.y) / 2.0
        if avgY > maxY:
            maxY    = avgY
            topLine = line

    if topLine:
        sketch.geometricConstraints.addMidPoint(selectedPoint, topLine)

    futil.log(f'{CMD_NAME}: created text "{inputText}" in sketch "{sketch.name}".')


def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    futil.log(f'{CMD_NAME} Validate Input Event')

    inputs       = args.inputs
    text_input   = adsk.core.StringValueCommandInput.cast(inputs.itemById(TEXT_INPUT_ID))
    point_input  = adsk.core.SelectionCommandInput.cast(inputs.itemById(POINT_INPUT_ID))

    args.areInputsValid = bool(text_input.value.strip()) and point_input.selectionCount == 1


def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Destroy Event')
    global local_handlers
    local_handlers = []
    futil.log('command destroy complete')