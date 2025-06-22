import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config
from operator import itemgetter

app = adsk.core.Application.get()
ui = app.userInterface
palettes = ui.palettes
textPalette = palettes.itemById("TextCommands")
textPalette.isVisible = True

# TODO *** Specify the command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdDialog'
CMD_NAME = 'Dimension Wizard'
CMD_Description = 'Add horizontal and vertical linear dimensions to all points in the active sketch which are not fully constrained.'
ORIGIN_MODE = 'origin_mode'
POINT_SELECTION = 'point_selection'
DIMENSION_SPACING = 'dimension_spacing'
SCALE_PARAMETER = 'scale_parameter'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = False

# TODO *** Define the location where the command button will be created. ***
# This is done by specifying the workspace, the tab, and the panel, and the 
# command it will be inserted beside. Not providing the command to position it
# will insert it at the end.
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SketchModifyPanel' #'SolidScriptsAddinsPanel'
COMMAND_BESIDE_ID = 'FusionMoveCommand' #'ScriptsManagerCommand'

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the target workspace the button will be created in.
    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    # Get the panel the button will be created in.
    panel = workspace.toolbarPanels.itemById(PANEL_ID)

    # Create the button command control in the UI after the specified existing command.
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)

    # Specify if the command is promoted to the main toolbar. 
    control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Created Event')

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # TODO Define the dialog for your command by adding different inputs to the command.

    origin_mode = inputs.addDropDownCommandInput(ORIGIN_MODE, 'Dimension Origin',  adsk.core.DropDownStyles.TextListDropDownStyle )
    origin_mode.listItems.add('Model Origin', True)
    origin_mode.listItems.add('Selection', False)

    point_selection = inputs.addSelectionInput(POINT_SELECTION, 'Origin Point', 'Select the point from which dimensions will be added')
    point_selection.addSelectionFilter('SketchPoints')
    point_selection.setSelectionLimits(0,1)
    point_selection.isVisible = False

    # Create a simple text box input.
    inputs.addTextBoxCommandInput(SCALE_PARAMETER, 'Scale Parameter', '', 1, False)

    
    defaultLengthUnits = app.activeProduct.unitsManager.defaultLengthUnits
    default_value = adsk.core.ValueInput.createByString('2')
    scale_control = inputs.addValueInput(DIMENSION_SPACING, 'Spacing', "mm", default_value)
    scale_control.isMinimumInclusive = False
    scale_control.minimumValue = 0
    scale_control.isMinimumLimited = True
    scale_control.value

    # TODO Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called when the user clicks the OK button in the command dialog or 
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

    # TODO ******************************** Your code here ********************************

    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    if not design:
        ui.messageBox('The DESIGN workspace must be active when running this command.', CMD_NAME)
        return
    


    textPalette.writeText(f'"{app.activeDocument.name}" is the active Document.')
    adsk.doEvents()

    target = app.activeEditObject
    sketch = adsk.fusion.Sketch.cast(target)


    if not sketch:
        ui.messageBox('A SKETCH must be active when running this script.', CMD_NAME)
        return

    # Get a reference to your command's inputs.
    inputs = args.command.commandInputs
    origin_mode: adsk.core.DropDownCommandInput = inputs.itemById(ORIGIN_MODE)
    point_selection: adsk.core.SelectionCommandInput = inputs.itemById(POINT_SELECTION)
    spacing_control: adsk.core.ValueCommandInput = inputs.itemById(DIMENSION_SPACING)
    label_offset = spacing_control.value

    textPalette.writeText(f'label_offset="{label_offset}" spacing_control.expression="{spacing_control.expression}" spacing_control.isValidExpression={spacing_control.isValidExpression}')
    adsk.doEvents()

    if origin_mode.listItems.item(0).isSelected:
        origin = sketch.originPoint
    else:
        origin: adsk.fusion.SketchPoint = point_selection.selection(0).entity

    scale_parameter: adsk.core.TextBoxCommandInput = inputs.itemById(SCALE_PARAMETER)
    
    parameter_name = scale_parameter.text
    if parameter_name.__len__() > 0:
        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)
        if not design:
            ui.messageBox('The DESIGN workspace must be active when running this command.', CMD_NAME)
            args.areInputsValid = False
            return
        parameter = design.allParameters.itemByName(parameter_name)
        scale_value = parameter.value
    else:
        scale_value = None
    

    xLabelBase = sketch.boundingBox.maxPoint.x + label_offset
    yLabelBase = sketch.boundingBox.maxPoint.y + label_offset
    dim = sketch.sketchDimensions

    negXpoints = []
    posXpoints = []
    negYpoints = []
    posYpoints = []
    for point in sketch.sketchPoints:
        if not point.isFullyConstrained:
            hasHorizontal = False
            hasVertical = False

            for dimension in point.sketchDimensions:
                textPalette.writeText(f'Existing dimension at ({dimension.textPosition.x}, {dimension.textPosition.y}) token "{dimension.entityToken}" has classType "{dimension.classType()}" objectType "{dimension.objectType}.')

                ld = adsk.fusion.SketchLinearDimension.cast(dimension)
                if not ld:
                    textPalette.writeText(f'NON linear')
                else:
                    textPalette.writeText(f'Its linear orientation "{ld.orientation}.')
                    if ld.orientation == adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation:
                        hasHorizontal = True
                    elif ld.orientation == adsk.fusion.DimensionOrientations.VerticalDimensionOrientation:
                        hasVertical = True

                adsk.doEvents()
            
            if not hasHorizontal:
                if point.geometry.x < origin.geometry.x:
                    negXpoints.append((point, abs(point.geometry.x)))
                if point.geometry.x > origin.geometry.x:
                    posXpoints.append((point, point.geometry.x))
            
            if not hasVertical:
                if point.geometry.y < origin.geometry.y:
                    negYpoints.append((point, abs(point.geometry.y)))
                if point.geometry.y > origin.geometry.y:
                    posYpoints.append((point, point.geometry.y))


    horizontal = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
    vertical = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation

    yLabel = yLabelBase
    for (point, x) in sorted(negXpoints, key=itemgetter(1)):
        if not point.isFullyConstrained:
            textPalette.writeText(f'negXpoints at ({point.geometry.x}, {point.geometry.y})')
            adsk.doEvents()
            
            hText = adsk.core.Point3D.create(x + (origin.geometry.x - x)/2, yLabel, 0)
            distanceDimension = dim.addDistanceDimension(origin, point, horizontal, hText)

            if scale_value:
                value = distanceDimension.value / scale_value
                distanceDimension.parameter.expression = f'{parameter_name} * {value}'
            yLabel += label_offset
    
    yLabel = yLabelBase
    for (point, x) in sorted(posXpoints, key=itemgetter(1)):
        if not point.isFullyConstrained:
            textPalette.writeText(f'posXpoints at ({point.geometry.x}, {point.geometry.y})')
            adsk.doEvents()
            
            hText = adsk.core.Point3D.create(origin.geometry.x + (x - origin.geometry.x)/2, yLabel, 0)
            distanceDimension = dim.addDistanceDimension(origin, point, horizontal, hText)

            if scale_value:
                value = distanceDimension.value / scale_value
                distanceDimension.parameter.expression = f'{parameter_name} * {value}'
            yLabel += label_offset
    
    xLabel = xLabelBase
    for (point, y) in sorted(negYpoints, key=itemgetter(1)):
        if not point.isFullyConstrained:
            textPalette.writeText(f'negYpoints at ({point.geometry.x}, {point.geometry.y})')
            adsk.doEvents()
            
            hText = adsk.core.Point3D.create(xLabel, y + (origin.geometry.y - y)/2, 0)
            distanceDimension = dim.addDistanceDimension(origin, point, vertical, hText)

            if scale_value:
                value = distanceDimension.value / scale_value
                distanceDimension.parameter.expression = f'{parameter_name} * {value}'
            xLabel += label_offset
    
    xLabel = xLabelBase
    for (point, y) in sorted(posYpoints, key=itemgetter(1)):
        if not point.isFullyConstrained:
            textPalette.writeText(f'posYpoints at ({point.geometry.x}, {point.geometry.y})')
            adsk.doEvents()
            
            hText = adsk.core.Point3D.create(xLabel, origin.geometry.y + (y - origin.geometry.y)/2, 0)
            distanceDimension = dim.addDistanceDimension(origin, point, vertical, hText)

            if scale_value:
                value = distanceDimension.value / scale_value
                distanceDimension.parameter.expression = f'{parameter_name} * {value}'
            xLabel += label_offset
      



# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs


# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')

    if changed_input.id == ORIGIN_MODE:
        dropdown = adsk.core.DropDownCommandInput.cast(changed_input)
        if dropdown:
            point_selection = inputs.itemById(POINT_SELECTION)
            if dropdown.listItems.item(1).isSelected:
                point_selection.isVisible = True
                point_selection.setSelectionLimits(1,1)
            else:
                point_selection.isVisible = False
                point_selection.setSelectionLimits(0,1)

   
# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Validate Input Event')

    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    inputs = args.inputs
    
    # Verify the validity of the input values. This controls if the OK button is enabled or not.
    spacing_control: adsk.core.ValueCommandInput = inputs.itemById(DIMENSION_SPACING)

    textPalette.writeText(f'spacing_control.value="{spacing_control.value}" spacing_control.expression="{spacing_control.expression}" spacing_control.isValidExpression={spacing_control.isValidExpression}')
    adsk.doEvents()



    # spacing_text = spacing_control.expression
    # spacing_error = True

    # unitsMgr = design.unitsManager
    # if unitsMgr.isValidExpression(spacing_text, unitsMgr.defaultLengthUnits):
    #     spacing = unitsMgr.evaluateExpression(spacing_text, unitsMgr.defaultLengthUnits)
    #     if spacing > 0:
    #         spacing_error = False

    # if spacing_error:
    #     args.areInputsValid = False

    #     textPalette.writeText(f'spacing_control.formattedText {spacing_control.formattedText})')
    #     adsk.doEvents()
        
    #     return
    
    scale_parameter: adsk.core.TextBoxCommandInput = inputs.itemById(SCALE_PARAMETER)
    
    parameter_name = scale_parameter.text

    textPalette.writeText(f'parameter_name="{parameter_name}" len={parameter_name.__len__()} formatted={scale_parameter.formattedText}')
    adsk.doEvents()

    if parameter_name.__len__() > 0:
        
        if not design:
            ui.messageBox('The DESIGN workspace must be active when running this command.', CMD_NAME)
            args.areInputsValid = False
            return
        parameter = design.allParameters.itemByName(parameter_name)
        if parameter:
            # check that its a valid length
            args.areInputsValid = True
        else:
            args.areInputsValid = False
            # make it red
            # scale_parameter.formattedText = f'<span style=" color:#ff0000;">{parameter_name}</span>'
            return
        
    args.areInputsValid = True



# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []
