import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config
from operator import itemgetter

app = adsk.core.Application.get()
ui = app.userInterface

# TODO *** Specify the command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_deleteDimensions'
CMD_NAME = 'Delete Dimensions'
CMD_Description = 'Delete some or all dimensions in the current sketch.'
MODE = 'mode'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = False

# Define the location where the command button will be created. ***
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

    mode = inputs.addDropDownCommandInput(MODE, 'Mode',  adsk.core.DropDownStyles.TextListDropDownStyle )
    mode.listItems.add('Created by Bruce', True)
    mode.listItems.add('All Diemnsions', False)

    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    # futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    # futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    # futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called when the user clicks the OK button in the command dialog or 
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')
    
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    if not design:
        ui.messageBox('The DESIGN workspace must be active when running this command.', CMD_NAME)
        return
    


    futil.log(f'"{app.activeDocument.name}" is the active Document.')
    

    target = app.activeEditObject
    sketch = adsk.fusion.Sketch.cast(target)


    if not sketch:
        ui.messageBox('A SKETCH must be active when running this script.', CMD_NAME)
        return

    # Get a reference to your command's inputs.
    inputs = args.command.commandInputs
    mode: adsk.core.DropDownCommandInput = inputs.itemById(MODE)

    delete_all = mode.listItems.item(1).isSelected

    found_undeletable = True
    deleted_anything = True
    while deleted_anything:
        #futil.log(f'Trace 1')
        found_undeletable = False
        deleted_anything = False

        for dimension in sketch.sketchDimensions:
        # for point in sketch.sketchPoints:
        #     futil.log(f'Trace 2')
        #     for dimension in point.sketchDimensions:
                #futil.log(f'Trace 3')
                created_by = None
                attr_group = dimension.attributes.itemsByGroup(config.COMPANY_NAME)
                if attr_group:
                    for attr in attr_group:
                        if attr.name == config.ATTR_CREATEDBY:
                            created_by = attr.value

                if delete_all or created_by:
                    #futil.log(f'Trace 4')
                    #futil.log(f'Delete dimension at ({dimension.textPosition.x}, {dimension.textPosition.y}).')
                    if dimension.isDeletable:
                        #futil.log(f'Do it!')
                        if dimension.deleteMe():
                            deleted_anything = True
                        else:
                            ui.messageBox('Failed to delete a deletable dimension.', CMD_NAME)
                    # else:
                        #futil.log(f'Undeletable')
                        # found_undeletable = True
     

    futil.log(f'Command execution complete')
    


# # This event handler is called when the command needs to compute a new preview in the graphics window.
# def command_preview(args: adsk.core.CommandEventArgs):
#     # General logging for debug.
#     futil.log(f'{CMD_NAME} Command Preview Event')
#     inputs = args.command.commandInputs


# # This event handler is called when the user changes anything in the command dialog
# # allowing you to modify values of other inputs based on that change.
# def command_input_changed(args: adsk.core.InputChangedEventArgs):
#     changed_input = args.input
#     inputs = args.inputs

#     # General logging for debug.
#     futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')

#     if changed_input.id == MODE:
#         dropdown = adsk.core.DropDownCommandInput.cast(changed_input)
#         if dropdown:
#             point_selection = inputs.itemById(POINT_SELECTION)
#             if dropdown.listItems.item(1).isSelected:
#                 point_selection.isVisible = True
#                 point_selection.setSelectionLimits(1,1)
#             else:
#                 point_selection.isVisible = False
#                 point_selection.setSelectionLimits(0,1)

   
# # This event handler is called when the user interacts with any of the inputs in the dialog
# # which allows you to verify that all of the inputs are valid and enables the OK button.
# def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
#     # General logging for debug.
#     futil.log(f'{CMD_NAME} Validate Input Event')

#     product = app.activeProduct
#     design = adsk.fusion.Design.cast(product)
#     inputs = args.inputs
    
#     # Verify the validity of the input values. This controls if the OK button is enabled or not.
#     spacing_control: adsk.core.ValueCommandInput = inputs.itemById(DIMENSION_SPACING)

#     futil.log(f'spacing_control.value="{spacing_control.value}" spacing_control.expression="{spacing_control.expression}" spacing_control.isValidExpression={spacing_control.isValidExpression}')
    



#     # spacing_text = spacing_control.expression
#     # spacing_error = True

#     # unitsMgr = design.unitsManager
#     # if unitsMgr.isValidExpression(spacing_text, unitsMgr.defaultLengthUnits):
#     #     spacing = unitsMgr.evaluateExpression(spacing_text, unitsMgr.defaultLengthUnits)
#     #     if spacing > 0:
#     #         spacing_error = False

#     # if spacing_error:
#     #     args.areInputsValid = False

#     #     futil.log(f'spacing_control.formattedText {spacing_control.formattedText})')
#     #     
        
#     #     return
    
#     scale_parameter: adsk.core.TextBoxCommandInput = inputs.itemById(SCALE_PARAMETER)
#     scale_parameter_value: adsk.core.TextBoxCommandInput = inputs.itemById(SCALE_PARAMETER_VALUE)
    
#     parameter_name = scale_parameter.text

#     futil.log(f'parameter_name="{parameter_name}" len={parameter_name.__len__()} formatted={scale_parameter.formattedText}')
    

#     if parameter_name.__len__() > 0:
        
#         if not design:
#             ui.messageBox('The DESIGN workspace must be active when running this command.', CMD_NAME)
#             args.areInputsValid = False
#             return
#         parameter = design.allParameters.itemByName(parameter_name)
#         if parameter:
#             # check that its a valid length
#             scale_parameter_value.formattedText = f'<span style=" color:#000000;">{parameter.value}</span>'
#             args.areInputsValid = True
#         else:
#             args.areInputsValid = False
#             # make it red
#             # scale_parameter.formattedText = f'<span style=" color:#ff0000;">{parameter_name}</span>'
#             scale_parameter_value.formattedText = f'<span style=" color:#ff0000;">Parameter not found</span>'
#             return
#     else:
#         scale_parameter_value.formattedText = ''
        
#     args.areInputsValid = True



# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []

    futil.log(f'command destroy complete')
    
