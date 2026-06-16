import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config
from operator import itemgetter
from typing import List, Dict, Set
import math

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_dimensionWizard'
CMD_NAME = 'Dimension Wizard'
CMD_Description = 'Add horizontal and vertical linear dimensions to all points in the active sketch which are not fully constrained.'
ORIGIN_MODE = 'origin_mode'
POINT_SELECTION = 'point_selection'
LINE_SELECTION = 'line_selection'
DIMENSION_SPACING = 'dimension_spacing'
SCALE_PARAMETER = 'scale_parameter'
SCALE_PARAMETER_VALUE = 'scale_parameter_value'
METHOD = 'method'

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

class PointData:
    def __init__(self, point: adsk.fusion.SketchPoint):
        self.point = point
        self.hx: float | None = None
        self.hy: float | None = None
        self.vx: float | None = None
        self.vy: float | None = None
        self.swapped = False



class PointWrapper:
    def __init__(self, point: adsk.fusion.SketchPoint):
        self.xy = f'{point.geometry.x}x{point.geometry.y}'
        self.x = point.geometry.x
        self.y = point.geometry.y
    
    def __hash__(self):
        return hash(self.xy)
    
    def __str__(self):
        return f'PointWrapper({self.x}, {self.y})'
    
    def __eq__(self, value):
        return self.x == value.x and self.y == value.y

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

    method = inputs.addDropDownCommandInput(METHOD, 'Method',  adsk.core.DropDownStyles.TextListDropDownStyle )
    global METHOD_ORIGINAL_INDEX
    METHOD_ORIGINAL_INDEX = len(method.listItems)
    method.listItems.add('Original', False)
    global METHOD_RECTANGULAR_INDEX
    METHOD_RECTANGULAR_INDEX = len(method.listItems)
    method.listItems.add('Rectangular', False)
    global METHOD_ANGULAR_INDEX
    METHOD_ANGULAR_INDEX = len(method.listItems)
    method.listItems.add('Angular', False)
    global METHOD_POLAR_INDEX
    METHOD_POLAR_INDEX= len(method.listItems)
    method.listItems.add('Polar', True)

    futil.log(f'METHOD_RECTANGULAR_INDEX={METHOD_RECTANGULAR_INDEX}')
    futil.log(f'METHOD_POLAR_INDEX={METHOD_POLAR_INDEX}')

    origin_mode = inputs.addDropDownCommandInput(ORIGIN_MODE, 'Dimension Origin',  adsk.core.DropDownStyles.TextListDropDownStyle )
    global ORIGIN_MODE_MODEL
    ORIGIN_MODE_MODEL = len(origin_mode.listItems)
    origin_mode.listItems.add('Model Origin', True)
    global ORIGIN_MODE_SELECTION
    ORIGIN_MODE_SELECTION = len(origin_mode.listItems)
    origin_mode.listItems.add('Selection', False)
    origin_mode.isVisible = False

    line_selection = inputs.addSelectionInput(LINE_SELECTION, 'Scale Line', 'Select the line from which dimensions will be scaled')
    line_selection.addSelectionFilter('SketchCurves')
    line_selection.setSelectionLimits(0,1)
    line_selection.isVisible = True

    point_selection = inputs.addSelectionInput(POINT_SELECTION, 'Origin Point', 'Select the point from which dimensions will be added')
    point_selection.addSelectionFilter('SketchPoints')
    point_selection.setSelectionLimits(0,1)
    point_selection.isVisible = True

    # Create a simple text box input.
    scale_parameter = inputs.addTextBoxCommandInput(SCALE_PARAMETER, 'Scale Parameter', '', 1, False)
    scale_parameter.isVisible = False
    scale_parameter_value = inputs.addTextBoxCommandInput(SCALE_PARAMETER_VALUE, '', '', 1, True)
    scale_parameter_value.isVisible = False
    
    defaultLengthUnits = app.activeProduct.unitsManager.defaultLengthUnits
    default_value = adsk.core.ValueInput.createByString('2')
    scale_control = inputs.addValueInput(DIMENSION_SPACING, 'Spacing', "mm", default_value)
    scale_control.isMinimumInclusive = False
    scale_control.minimumValue = 0
    scale_control.isMinimumLimited = True
    scale_control.value

    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    # futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


def create_angle_dimension(line: adsk.fusion.SketchLine, scale_line: adsk.fusion.SketchLine, dim: adsk.fusion.SketchDimensions
):
    xLabel = line.startSketchPoint.geometry.x + (line.endSketchPoint.geometry.x - line.startSketchPoint.geometry.x)/2
    yLabel = line.startSketchPoint.geometry.y + (line.endSketchPoint.geometry.y - line.startSketchPoint.geometry.y)/2

    futil.log(f'create_line_dimension ({xLabel}, {yLabel})')

    hText = adsk.core.Point3D.create(xLabel, yLabel, 0)

    try:
        distanceDimension = dim.addAngularDimension(line, scale_line, hText)
    except:
        return None
    
    distanceDimension.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)

    # if scale_value:
    #     value = distanceDimension.value / scale_value
    #     distanceDimension.parameter.expression = f'{parameter_name} * {value}'

    return distanceDimension


def create_line_dimension(line: adsk.fusion.SketchLine, dim: adsk.fusion.SketchDimensions, is_driving: bool = True
):
    xLabel = line.startSketchPoint.geometry.x + (line.endSketchPoint.geometry.x - line.startSketchPoint.geometry.x)/2
    yLabel = line.startSketchPoint.geometry.y + (line.endSketchPoint.geometry.y - line.startSketchPoint.geometry.y)/2

    futil.log(f'create_line_dimension ({xLabel}, {yLabel})')

    hText = adsk.core.Point3D.create(xLabel, yLabel, 0)

    try:
        distanceDimension = dim.addDistanceDimension(line.startSketchPoint, line.endSketchPoint, adsk.fusion.DimensionOrientations.AlignedDimensionOrientation, hText, is_driving)
    except:
        return None
    
    distanceDimension.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)

    # if scale_value:
    #     value = distanceDimension.value / scale_value
    #     distanceDimension.parameter.expression = f'{parameter_name} * {value}'

    return distanceDimension


def create_dimension(xLabel: float, yLabel: float, point: adsk.fusion.SketchPoint, origin: adsk.fusion.SketchPoint, horizontal:  adsk.fusion.DimensionOrientations, scale_value: float, parameter_name: str, dim: adsk.fusion.SketchDimensions
):
    if origin == point:
        ui.messageBox(f'ITS THE ORIGIN', CMD_NAME)
        return

    futil.log(f'create_dimension ({xLabel}, {yLabel})')

    hText = adsk.core.Point3D.create(xLabel, yLabel, 0)

    try:
        distanceDimension = dim.addDistanceDimension(origin, point, horizontal, hText)
    except:
        return None
    
    distanceDimension.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)

    if scale_value:
        value = distanceDimension.value / scale_value
        distanceDimension.parameter.expression = f'{parameter_name} * {value}'

    return distanceDimension

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
    origin_mode: adsk.core.DropDownCommandInput = inputs.itemById(ORIGIN_MODE)
    point_selection: adsk.core.SelectionCommandInput = inputs.itemById(POINT_SELECTION)
    line_selection: adsk.core.SelectionCommandInput = inputs.itemById(LINE_SELECTION)
    spacing_control: adsk.core.ValueCommandInput = inputs.itemById(DIMENSION_SPACING)
    label_offset = spacing_control.value
    method_control: adsk.core.DropDownCommandInput = inputs.itemById(METHOD)

    futil.log(f'label_offset="{label_offset}" spacing_control.expression="{spacing_control.expression}" spacing_control.isValidExpression={spacing_control.isValidExpression}')

    if method_control.listItems.item(METHOD_POLAR_INDEX).isSelected or origin_mode.listItems.item(1).isSelected:
        origin: adsk.fusion.SketchPoint = point_selection.selection(0).entity
    else:
        origin = sketch.originPoint

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
    
    if method_control.listItems.item(METHOD_ORIGINAL_INDEX).isSelected:
        execute_original(args, sketch, label_offset, origin, parameter_name, scale_value)
        return
    
    if method_control.listItems.item(METHOD_RECTANGULAR_INDEX).isSelected:
        execute_rectangular(args, sketch, label_offset, origin, parameter_name, scale_value)
        return
    
    if method_control.listItems.item(METHOD_ANGULAR_INDEX).isSelected:
        execute_angular(args, sketch, label_offset, origin, parameter_name, scale_value)
        return
    
    if method_control.listItems.item(METHOD_POLAR_INDEX).isSelected:
        execute_polar(args, sketch, label_offset, origin, line_selection.selection(0).entity)
        return
    
    ui.messageBox('Unknown method!', CMD_NAME)

def get_angle(start_point: PointWrapper, line: adsk.fusion.SketchLine):
    end_point = PointWrapper(line.endSketchPoint)
    if end_point == start_point:
        end_point = PointWrapper(line.startSketchPoint)
    
    return math.atan2(end_point.y - start_point.y, end_point.x - start_point.x)

def execute_angular(args: adsk.core.CommandEventArgs, sketch: adsk.fusion.Sketch, label_offset: float, origin: adsk.fusion.SketchPoint, parameter_name: str, scale_value: float | None):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

    right_angle = math.atan(0)
    point_dict: Dict[PointWrapper, List[adsk.fusion.SketchLine]] = {}

    for curve in sketch.sketchCurves:
        line = adsk.fusion.SketchLine.cast(curve)
        if line:
            # line_angle = math.atan2(line.endSketchPoint.geometry.y - line.startSketchPoint.geometry.y, line.endSketchPoint.geometry.x - line.startSketchPoint.geometry.x)
            # orthogonal_angle = line_angle + right_angle
            # xLabel = line.startSketchPoint.geometry.x + (line.endSketchPoint.geometry.x - line.startSketchPoint.geometry.x)/2 - label_offset * math.sin(orthogonal_angle)
            # yLabel = line.startSketchPoint.geometry.y + (line.endSketchPoint.geometry.y - line.startSketchPoint.geometry.y)/2 - label_offset * math.cos(orthogonal_angle)
            # futil.log(f'Linear dimension {xLabel} {yLabel} orth {orthogonal_angle}')
            # text_point = adsk.core.Point3D.create(xLabel, yLabel, 0)
            # try:
            #     dimension = sketch.sketchDimensions.addDistanceDimension(line.startSketchPoint, line.endSketchPoint, adsk.fusion.DimensionOrientations.AlignedDimensionOrientation, text_point)
            #     dimension.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)
            # except:
            #     futil.log(f'FAILED DIMENSION')

            xy = PointWrapper(line.startSketchPoint) #f'{line.startSketchPoint.geometry.x}x{line.startSketchPoint.geometry.y}'
            futil.log(f'xy={xy} line={line}')
            try:
                set = point_dict[xy]
                set.append(line)
            except:
                set: List[adsk.fusion.SketchLine] = [line]
                point_dict[xy] = set

            xy = PointWrapper(line.endSketchPoint) #xy = f'{line.startSketchPoint.geometry.x}x{line.startSketchPoint.geometry.y}'
            futil.log(f'xy={xy} line={line}')
            try:
                set = point_dict[xy]
                set.append(line)
            except:
                set: List[adsk.fusion.SketchLine] = [line]
                point_dict[xy] = set

    for xy, lines in point_dict.items():
        futil.log(f'Point ({xy})')
        for line in lines:
            futil.log(f'Line ({line.startSketchPoint.geometry.x}, {line.startSketchPoint.geometry.y}) -> ({line.endSketchPoint.geometry.x}, {line.endSketchPoint.geometry.y})')
        theta1 = get_angle(xy, lines[0])
        i=1
        while i<len(lines):
            theta2 = get_angle(xy, lines[i])
            theta = theta1 + (theta2 - theta1)/2
            xLabel = xy.x - label_offset * math.sin(theta)
            yLabel = xy.y - label_offset * math.cos(theta)
            try:
                text_point = adsk.core.Point3D.create(xLabel, yLabel, 0)
                dimension = sketch.sketchDimensions.addAngularDimension(lines[0], lines[i], text_point)
                dimension.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)
            except:
                futil.log(f'FAILED ANGULAR DIMENSION')
            i += 1
    
    for curve in sketch.sketchCurves:
        line = adsk.fusion.SketchLine.cast(curve)
        if line:
            line_angle = math.atan2(line.endSketchPoint.geometry.y - line.startSketchPoint.geometry.y, line.endSketchPoint.geometry.x - line.startSketchPoint.geometry.x)
            orthogonal_angle = line_angle + right_angle
            xLabel = line.startSketchPoint.geometry.x + (line.endSketchPoint.geometry.x - line.startSketchPoint.geometry.x)/2 - label_offset * math.sin(orthogonal_angle)
            yLabel = line.startSketchPoint.geometry.y + (line.endSketchPoint.geometry.y - line.startSketchPoint.geometry.y)/2 - label_offset * math.cos(orthogonal_angle)
            futil.log(f'Linear dimension {xLabel} {yLabel} orth {orthogonal_angle}')
            text_point = adsk.core.Point3D.create(xLabel, yLabel, 0)
            try:
                dimension = sketch.sketchDimensions.addDistanceDimension(line.startSketchPoint, line.endSketchPoint, adsk.fusion.DimensionOrientations.AlignedDimensionOrientation, text_point)
                dimension.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)
            except:
                futil.log(f'FAILED DIMENSION')

    futil.log(f'Command execution complete')

def is_angular_dimension_of(dimenion: adsk.fusion.SketchAngularDimension, line1: adsk.fusion.SketchLine, line2: adsk.fusion.SketchLine) -> bool:
    if dimenion.lineOne == line1 and dimenion.lineTwo == line2:
        return True
    
    if dimenion.lineTwo == line1 and dimenion.lineOne == line2:
        return True
    
    return False

def is_dimension_of_line(dimenion: adsk.fusion.SketchLinearDimension, line: adsk.fusion.SketchLine) -> bool:
    if dimenion.entityOne == line.startSketchPoint and dimenion.entityTwo == line.endSketchPoint:
        return True
    
    if dimenion.entityTwo == line.startSketchPoint and dimenion.entityOne == line.endSketchPoint:
        return True
    
    return False

def point_dimension_line(point: adsk.fusion.SketchPoint, origin: adsk.fusion.SketchPoint, sketch_lines: adsk.fusion.SketchLines) -> adsk.fusion.SketchLine:
    if point.connectedEntities:
        for entity in point.connectedEntities:
            line = adsk.fusion.SketchLine.cast(entity)
            if line:
                if line.startSketchPoint == origin or line.endSketchPoint == origin:
                    return line
    line = sketch_lines.addByTwoPoints(origin, point)
    line.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)
    line.isConstruction = True

    return line

def get_line_length_dimension(line: adsk.fusion.SketchLine) -> adsk.fusion.SketchLinearDimension:

    for dimension in line.startSketchPoint.sketchDimensions:
        ld = adsk.fusion.SketchLinearDimension.cast(dimension)
        if ld:
            if ld.orientation == adsk.fusion.DimensionOrientations.AlignedDimensionOrientation:
                if is_dimension_of_line(ld, line):
                    return ld
    
    return None

def get_line_angle_dimension(line: adsk.fusion.SketchLine, scale_line: adsk.fusion.SketchLine) -> adsk.fusion.SketchLinearDimension:

    for dimension in line.sketchDimensions:
        ad = adsk.fusion.SketchAngularDimension.cast(dimension)
        if ad:
            if is_angular_dimension_of(ad, scale_line, line):
                    return ad
    
    return None

def point_not_excluded(point: adsk.fusion.SketchPoint, scale_line: adsk.fusion.SketchLine) -> bool:
    if point.isFullyConstrained:
        return False
    
    if point == scale_line.startSketchPoint or point == scale_line.endSketchPoint:
        return False
    
    return True

def execute_polar(args: adsk.core.CommandEventArgs, sketch: adsk.fusion.Sketch, label_offset: float, origin: adsk.fusion.SketchPoint, scale_line: adsk.fusion.SketchLine):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event execute_polar')

    # fisrt ensure that the scale line is constr

    # scale_line.isFixed = True



    scale_dimension = None

    futil.log(f'scale_line = {scale_line}')

    scale_dimension = get_line_length_dimension(scale_line)
    futil.log(f'existing scale_dimension = {scale_dimension}')

    if not scale_dimension:
        scale_dimension = create_line_dimension(scale_line, sketch.sketchDimensions, False)
    

    param = scale_dimension.parameter
    scale_name = param.name
    scale_value = param.value

    # futil.log(f'param = {param}')
    # futil.log(f'param.name = {param.name}')

    x = max(sketch.boundingBox.maxPoint.x - origin.geometry.x, origin.geometry.x - sketch.boundingBox.minPoint.x)
    y = max(sketch.boundingBox.maxPoint.y - origin.geometry.y, origin.geometry.y - sketch.boundingBox.minPoint.y)
    labelDistance = math.sqrt(x*x+y*y) + label_offset


    # length_lines: List[adsk.fusion.SketchLine] = []
    # angle_lines: List[adsk.fusion.SketchLine] = []

    for point in sketch.sketchPoints:
        if point_not_excluded(point, scale_line):
            dimension_line = point_dimension_line(point, origin, sketch.sketchCurves.sketchLines)
            length_dimension = get_line_length_dimension(dimension_line)



            angle_dimension = get_line_angle_dimension(dimension_line, scale_line)

            if length_dimension == None:
                # length_lines.append(dimension_line)
                length_dimension = create_line_dimension(dimension_line, sketch.sketchDimensions)

                if length_dimension:
                    value = length_dimension.value / scale_value
                    length_dimension.parameter.expression = f'{scale_name} * {value}'

            if angle_dimension == None:
                # index = points.__len__()
                # angle_lines.append(dimension_line)
                create_angle_dimension(dimension_line, scale_line, sketch.sketchDimensions)
    
   


            #futil.log(f'new PointData[{index}] {points[index]}.')
        
    #         hasHorizontal = False
    #         hasVertical = False

    #         for dimension in point.sketchDimensions:
    #             #futil.log(f'Existing dimension at ({dimension.textPosition.x}, {dimension.textPosition.y}) token "{dimension.entityToken}" has classType "{dimension.classType()}" objectType "{dimension.objectType}.')

    #             ld = adsk.fusion.SketchLinearDimension.cast(dimension)
    #             if ld:
    #             #     textPalette.writeText(f'NON linear')
    #             # else:
    #                 if ld.entityOne == origin or ld.entityTwo == origin:
    #                     #futil.log(f'Its linear orientation "{ld.orientation}.')
    #                     if ld.orientation == adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation:
    #                         hasHorizontal = True
    #                     elif ld.orientation == adsk.fusion.DimensionOrientations.VerticalDimensionOrientation:
    #                         hasVertical = True

                
            
    #         if not hasHorizontal:
    #             if point.geometry.x < origin.geometry.x:
    #                 negXpoints.append((index, origin.geometry.x - point.geometry.x))
    #             if point.geometry.x > origin.geometry.x:
    #                 posXpoints.append((index, point.geometry.x - origin.geometry.x))
            
    #         if not hasVertical:
    #             if point.geometry.y < origin.geometry.y:
    #                 posYpoints.append((index, origin.geometry.y - point.geometry.y))
    #             if point.geometry.y > origin.geometry.y:
    #                 negYpoints.append((index, point.geometry.y - origin.geometry.y))



    # yLabel = yLabelBase
    # for (i, x) in sorted(negXpoints, key=itemgetter(1)):
    #     point_data: PointData = points[i]
    #     point_data.hx = origin.geometry.x - x/2
    #     point_data.hy = yLabel
    #     yLabel += label_offset
    
    # yLabel = yLabelBase
    # for (i, x) in sorted(posXpoints, key=itemgetter(1)):
    #     point_data: PointData = points[i]
    #     point_data.hx = origin.geometry.x + x/2
    #     point_data.hy = yLabel
    #     yLabel += label_offset
    
    # xLabel = xLabelBase
    # for (i, y) in sorted(negYpoints, key=itemgetter(1)):
    #     point_data: PointData = points[i]
    #     point_data.vx = xLabel
    #     point_data.vy = origin.geometry.y + y/2
    #     point_data.swapped = True
    #     xLabel += label_offset
    
    # xLabel = xLabelBase
    # for (i, y) in sorted(posYpoints, key=itemgetter(1)):
    #     point_data: PointData = points[i]
    #     point_data.vx = xLabel
    #     point_data.vy = origin.geometry.y - y/2
    #     xLabel += label_offset
    
    # for point_data in points:
    #     if point_data.hx and point_data.hy:
    #         h = create_dimension(point_data.hx, point_data.hy, origin, point_data.point, adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, scale_value, parameter_name, dim)
            
    #     if point_data.vx and point_data.vy:
    #         if point_data.swapped:
    #             v = create_dimension(point_data.vx, point_data.vy, point_data.point, origin, adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, scale_value, parameter_name, dim)
    #         else:
    #             v = create_dimension(point_data.vx, point_data.vy, origin, point_data.point, adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, scale_value, parameter_name, dim)
            
    
    # for curve in sketch.sketchCurves:
    #     if not curve.isFullyConstrained:
    #         textPoint = adsk.core.Point3D.create(
    #             curve.boundingBox.minPoint.x + (curve.boundingBox.maxPoint.x - curve.boundingBox.minPoint.x)/2,
    #             curve.boundingBox.minPoint.y + (curve.boundingBox.maxPoint.y - curve.boundingBox.minPoint.y)/2, 0)
    #         try:
    #             diameterDimension = dim.addDiameterDimension(curve, textPoint)
    #             diameterDimension.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)
    #         except:
    #             futil.log(f'FAILED DIMENSION')
    #         else:
    #             if scale_value:
    #                 value = diameterDimension.value / scale_value
    #                 diameterDimension.parameter.expression = f'{parameter_name} * {value}'
    
    # if not origin.isFullyConstrained:
    #     hasHorizontal = False
    #     hasVertical = False
    #     for dimension in origin.sketchDimensions:
    #             #futil.log(f'Existing dimension at ({dimension.textPosition.x}, {dimension.textPosition.y}) token "{dimension.entityToken}" has classType "{dimension.classType()}" objectType "{dimension.objectType}.')

    #             ld = adsk.fusion.SketchLinearDimension.cast(dimension)
    #             if ld:
    #             #     textPalette.writeText(f'NON linear')
    #             # else:
    #                 if ld.entityOne == sketch.originPoint or ld.entityTwo == sketch.originPoint:
    #                     #futil.log(f'Its linear orientation "{ld.orientation}.')
    #                     if ld.orientation == adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation:
    #                         hasHorizontal = True
    #                     elif ld.orientation == adsk.fusion.DimensionOrientations.VerticalDimensionOrientation:
    #                         hasVertical = True

                
            
    #     xLabelBase = sketch.boundingBox.minPoint.x - label_offset
    #     yLabelBase = sketch.boundingBox.minPoint.y - label_offset

    #     futil.log(f'Origin {hasHorizontal} {hasVertical}')

    #     if not hasHorizontal:
    #         create_dimension(origin.geometry.x / 2, yLabelBase, origin, sketch.originPoint, adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, None, parameter_name, dim)
        
    #     if not hasVertical:
    #         create_dimension(xLabelBase, origin.geometry.y / 2, origin, sketch.originPoint, adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, None, parameter_name, dim)
        
    # else:
    #     futil.log(f'Origin fully constrained')
    futil.log(f'Command execution complete')

def execute_rectangular(args: adsk.core.CommandEventArgs, sketch: adsk.fusion.Sketch, label_offset: float, origin: adsk.fusion.SketchPoint, parameter_name: str, scale_value: float | None):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

    xLabelBase = sketch.boundingBox.maxPoint.x + label_offset
    yLabelBase = sketch.boundingBox.maxPoint.y + label_offset
    dim = sketch.sketchDimensions

    points: List[PointData] = []
    negXpoints = []
    posXpoints = []
    negYpoints = []
    posYpoints = []
    for point in sketch.sketchPoints:
        if not point.isFullyConstrained:
            index = points.__len__()
            points.append(PointData(point))
            #futil.log(f'new PointData[{index}] {points[index]}.')
        
            hasHorizontal = False
            hasVertical = False

            for dimension in point.sketchDimensions:
                #futil.log(f'Existing dimension at ({dimension.textPosition.x}, {dimension.textPosition.y}) token "{dimension.entityToken}" has classType "{dimension.classType()}" objectType "{dimension.objectType}.')

                ld = adsk.fusion.SketchLinearDimension.cast(dimension)
                if ld:
                #     textPalette.writeText(f'NON linear')
                # else:
                    if ld.entityOne == origin or ld.entityTwo == origin:
                        #futil.log(f'Its linear orientation "{ld.orientation}.')
                        if ld.orientation == adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation:
                            hasHorizontal = True
                        elif ld.orientation == adsk.fusion.DimensionOrientations.VerticalDimensionOrientation:
                            hasVertical = True

                
            
            if not hasHorizontal:
                if point.geometry.x < origin.geometry.x:
                    negXpoints.append((index, origin.geometry.x - point.geometry.x))
                if point.geometry.x > origin.geometry.x:
                    posXpoints.append((index, point.geometry.x - origin.geometry.x))
            
            if not hasVertical:
                if point.geometry.y < origin.geometry.y:
                    posYpoints.append((index, origin.geometry.y - point.geometry.y))
                if point.geometry.y > origin.geometry.y:
                    negYpoints.append((index, point.geometry.y - origin.geometry.y))



    yLabel = yLabelBase
    for (i, x) in sorted(negXpoints, key=itemgetter(1)):
        point_data: PointData = points[i]
        point_data.hx = origin.geometry.x - x/2
        point_data.hy = yLabel
        yLabel += label_offset
    
    yLabel = yLabelBase
    for (i, x) in sorted(posXpoints, key=itemgetter(1)):
        point_data: PointData = points[i]
        point_data.hx = origin.geometry.x + x/2
        point_data.hy = yLabel
        yLabel += label_offset
    
    xLabel = xLabelBase
    for (i, y) in sorted(negYpoints, key=itemgetter(1)):
        point_data: PointData = points[i]
        point_data.vx = xLabel
        point_data.vy = origin.geometry.y + y/2
        point_data.swapped = True
        xLabel += label_offset
    
    xLabel = xLabelBase
    for (i, y) in sorted(posYpoints, key=itemgetter(1)):
        point_data: PointData = points[i]
        point_data.vx = xLabel
        point_data.vy = origin.geometry.y - y/2
        xLabel += label_offset
    
    for point_data in points:
        if point_data.hx and point_data.hy:
            h = create_dimension(point_data.hx, point_data.hy, origin, point_data.point, adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, scale_value, parameter_name, dim)
            
        if point_data.vx and point_data.vy:
            if point_data.swapped:
                v = create_dimension(point_data.vx, point_data.vy, point_data.point, origin, adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, scale_value, parameter_name, dim)
            else:
                v = create_dimension(point_data.vx, point_data.vy, origin, point_data.point, adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, scale_value, parameter_name, dim)
            
    
    for curve in sketch.sketchCurves:
        if not curve.isFullyConstrained:
            textPoint = adsk.core.Point3D.create(
                curve.boundingBox.minPoint.x + (curve.boundingBox.maxPoint.x - curve.boundingBox.minPoint.x)/2,
                curve.boundingBox.minPoint.y + (curve.boundingBox.maxPoint.y - curve.boundingBox.minPoint.y)/2, 0)
            try:
                diameterDimension = dim.addDiameterDimension(curve, textPoint)
                diameterDimension.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)
            except:
                futil.log(f'FAILED DIMENSION')
            else:
                if scale_value:
                    value = diameterDimension.value / scale_value
                    diameterDimension.parameter.expression = f'{parameter_name} * {value}'
    
    if not origin.isFullyConstrained:
        hasHorizontal = False
        hasVertical = False
        for dimension in origin.sketchDimensions:
                #futil.log(f'Existing dimension at ({dimension.textPosition.x}, {dimension.textPosition.y}) token "{dimension.entityToken}" has classType "{dimension.classType()}" objectType "{dimension.objectType}.')

                ld = adsk.fusion.SketchLinearDimension.cast(dimension)
                if ld:
                #     textPalette.writeText(f'NON linear')
                # else:
                    if ld.entityOne == sketch.originPoint or ld.entityTwo == sketch.originPoint:
                        #futil.log(f'Its linear orientation "{ld.orientation}.')
                        if ld.orientation == adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation:
                            hasHorizontal = True
                        elif ld.orientation == adsk.fusion.DimensionOrientations.VerticalDimensionOrientation:
                            hasVertical = True

                
            
        xLabelBase = sketch.boundingBox.minPoint.x - label_offset
        yLabelBase = sketch.boundingBox.minPoint.y - label_offset

        futil.log(f'Origin {hasHorizontal} {hasVertical}')

        if not hasHorizontal:
            create_dimension(origin.geometry.x / 2, yLabelBase, origin, sketch.originPoint, adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, None, parameter_name, dim)
        
        if not hasVertical:
            create_dimension(xLabelBase, origin.geometry.y / 2, origin, sketch.originPoint, adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, None, parameter_name, dim)
        
    else:
        futil.log(f'Origin fully constrained')
    futil.log(f'Command execution complete')
    

def execute_original(args: adsk.core.CommandEventArgs, sketch: adsk.fusion.Sketch, label_offset: float, origin: adsk.fusion.SketchPoint, parameter_name: str, scale_value: float | None):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

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
                futil.log(f'Existing dimension at ({dimension.textPosition.x}, {dimension.textPosition.y}) token "{dimension.entityToken}" has classType "{dimension.classType()}" objectType "{dimension.objectType}.')

                ld = adsk.fusion.SketchLinearDimension.cast(dimension)
                if ld:
                #     textPalette.writeText(f'NON linear')
                # else:
                    futil.log(f'Its linear orientation "{ld.orientation}.')
                    if ld.orientation == adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation:
                        hasHorizontal = True
                    elif ld.orientation == adsk.fusion.DimensionOrientations.VerticalDimensionOrientation:
                        hasVertical = True

                
            
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
            futil.log(f'negXpoints at ({point.geometry.x}, {point.geometry.y}) origin ({origin.geometry.x}, {origin.geometry.y})')
            futil.log(f'hText = adsk.core.Point3D.create({origin.geometry.x - (x - origin.geometry.x)/2}, yLabel, 0)')
            
            create_dimension(origin.geometry.x - (x - origin.geometry.x)/2, yLabel, point, origin, horizontal, scale_value, parameter_name, dim)

            # if sketch.originPoint == point:
            #     ui.messageBox(f'ITS THE ORIGIN', CMD_NAME)
            #     continue
                        
            # hText = adsk.core.Point3D.create(origin.geometry.x - (x - origin.geometry.x)/2, yLabel, 0)
            # distanceDimension = dim.addDistanceDimension(origin, point, horizontal, hText)
            # distanceDimension.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)

            # if scale_value:
            #     value = distanceDimension.value / scale_value
            #     distanceDimension.parameter.expression = f'{parameter_name} * {value}'
            yLabel += label_offset
    
    yLabel = yLabelBase
    for (point, x) in sorted(posXpoints, key=itemgetter(1)):
        if not point.isFullyConstrained:
            futil.log(f'posXpoints at ({point.geometry.x}, {point.geometry.y})')
            

            create_dimension(origin.geometry.x + (x - origin.geometry.x)/2, yLabel, point, origin, horizontal, scale_value, parameter_name, dim)

            # if sketch.originPoint == point:
            #     ui.messageBox(f'ITS THE ORIGIN', CMD_NAME)
            #     continue

            
            # hText = adsk.core.Point3D.create(origin.geometry.x + (x - origin.geometry.x)/2, yLabel, 0)
            # distanceDimension = dim.addDistanceDimension(origin, point, horizontal, hText)
            # distanceDimension.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)

            # if scale_value:
            #     value = distanceDimension.value / scale_value
            #     distanceDimension.parameter.expression = f'{parameter_name} * {value}'
            yLabel += label_offset
    
    xLabel = xLabelBase
    for (point, y) in sorted(negYpoints, key=itemgetter(1)):
        if not point.isFullyConstrained:
            futil.log(f'negYpoints at ({point.geometry.x}, {point.geometry.y})')

            create_dimension(xLabel, origin.geometry.y - (y -origin.geometry.y)/2, origin, point, vertical, scale_value, parameter_name, dim)
            

            # if sketch.originPoint == point:
            #     ui.messageBox(f'ITS THE ORIGIN', CMD_NAME)
            #     continue

            
            # hText = adsk.core.Point3D.create(xLabel, origin.geometry.y - (y -origin.geometry.y)/2, 0)
            # distanceDimension = dim.addDistanceDimension(origin, point, vertical, hText)
            # distanceDimension.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)

            # if scale_value:
            #     value = distanceDimension.value / scale_value
            #     distanceDimension.parameter.expression = f'{parameter_name} * {value}'
            xLabel += label_offset
    
    xLabel = xLabelBase
    for (point, y) in sorted(posYpoints, key=itemgetter(1)):
        if not point.isFullyConstrained:
            futil.log(f'posYpoints at ({point.geometry.x}, {point.geometry.y})')

            create_dimension(xLabel, origin.geometry.y + (y - origin.geometry.y)/2, point, origin, vertical, scale_value, parameter_name, dim)
            

            # if sketch.originPoint == point:
            #     ui.messageBox(f'ITS THE ORIGIN', CMD_NAME)
            #     continue

            
            # hText = adsk.core.Point3D.create(xLabel, origin.geometry.y + (y - origin.geometry.y)/2, 0)
            # distanceDimension = dim.addDistanceDimension(origin, point, vertical, hText)
            # distanceDimension.attributes.add(config.COMPANY_NAME, config.ATTR_CREATEDBY, CMD_NAME)

            # if scale_value:
            #     value = distanceDimension.value / scale_value
            #     distanceDimension.parameter.expression = f'{parameter_name} * {value}'
            xLabel += label_offset
    
    for curve in sketch.sketchCurves:
        if not curve.isFullyConstrained:
            textPoint = adsk.core.Point3D.create(
                curve.boundingBox.minPoint.x + (curve.boundingBox.maxPoint.x - curve.boundingBox.minPoint.x)/2,
                curve.boundingBox.minPoint.y + (curve.boundingBox.maxPoint.y - curve.boundingBox.minPoint.y)/2, 0)
            try:
                diameterDimension = dim.addDiameterDimension(curve, textPoint)
            except:
                continue
            else:
                if scale_value:
                    value = diameterDimension.value / scale_value
                    diameterDimension.parameter.expression = f'{parameter_name} * {value}'
    futil.log(f'Command execution complete')

# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs


def check_valid_point(selected_point: adsk.fusion.SketchPoint, selected_line: adsk.fusion.SketchLine) -> bool:
    return True
    # futil.log(f'selected_point = {selected_point} ({selected_point.geometry.x}, {selected_point.geometry.y})')
    # if selected_point == selected_line.startSketchPoint:
    #     futil.log(f'start point is valid')
    #     return True
    # if selected_point == selected_line.endSketchPoint:
    #     futil.log(f'end point is valid')
    #     return True
    
    # for constraint in selected_line.geometricConstraints:
    #     coincident = adsk.fusion.CoincidentConstraint.cast(constraint)
    #     futil.log(f'constraint = {constraint}')
    #     futil.log(f'coincident = {coincident}')
    #     if coincident:
    #         if coincident.point == selected_point:
    #             futil.log(f'coincident point is valid')
    #             return True
        
    #     midpoint = adsk.fusion.MidPointConstraint.cast(constraint)
    #     futil.log(f'midpoint = {midpoint}')
    #     if midpoint:
    #         futil.log(f'midpoint.point = {midpoint.point} ({midpoint.point.geometry.x}, {midpoint.point.geometry.y})')
    #         if midpoint.point == selected_point:
    #             futil.log(f'mid point is valid')
    #             return True
    
    # futil.log(f'point is not valid')
    # return False

# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    # futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')

    point_selection: adsk.core.SelectionCommandInput = inputs.itemById(POINT_SELECTION)
    line_selection: adsk.core.SelectionCommandInput = inputs.itemById(LINE_SELECTION)
    origin_mode: adsk.core.DropDownCommandInput = inputs.itemById(ORIGIN_MODE)
    scale_parameter: adsk.core.TextBoxCommandInput = inputs.itemById(SCALE_PARAMETER)
    scale_parameter_value: adsk.core.TextBoxCommandInput = inputs.itemById(SCALE_PARAMETER_VALUE)

    if changed_input.id == METHOD:
        dropdown = adsk.core.DropDownCommandInput.cast(changed_input)
        if dropdown:
            if dropdown.listItems.item(METHOD_POLAR_INDEX).isSelected:
                line_selection.isVisible = True
                line_selection.setSelectionLimits(1,1)
                point_selection.isVisible = True
                point_selection.setSelectionLimits(1,1)
                origin_mode.isVisible = False
                scale_parameter.isVisible = False
                scale_parameter_value.isVisible = False
            else:
                origin_mode.isVisible = True
                if origin_mode.listItems.item(ORIGIN_MODE_SELECTION).isSelected:
                    point_selection.isVisible = True
                    point_selection.setSelectionLimits(1,1)
                else:
                    point_selection.isVisible = False
                    point_selection.setSelectionLimits(0,1)
                line_selection.isVisible = False
                line_selection.setSelectionLimits(0,1)
                scale_parameter.isVisible = True
                scale_parameter_value.isVisible = True

    if changed_input.id == ORIGIN_MODE:
        if origin_mode.listItems.item(ORIGIN_MODE_SELECTION).isSelected:
            point_selection.isVisible = True
            point_selection.setSelectionLimits(1,1)
        else:
            point_selection.isVisible = False
            point_selection.setSelectionLimits(0,1)

    if changed_input.id == LINE_SELECTION:
        point_selection.clearSelection()
        selected_curve = line_selection.selection(0).entity
        futil.log(f'selected_curve = {selected_curve}')
        selected_line = adsk.fusion.SketchLine.cast(selected_curve)
        if selected_line:
            point_selection.hasFocus = True
        else:
            line_selection.clearSelection()
    
    if changed_input.id == POINT_SELECTION:
        selected_point: adsk.fusion.SketchPoint = point_selection.selection(0).entity
        if line_selection.selectionCount > 0:
            selected_curve = line_selection.selection(0).entity
            futil.log(f'selected_curve = {selected_curve}')
            selected_line = adsk.fusion.SketchLine.cast(selected_curve)
            if selected_line:
                if not check_valid_point(selected_point, selected_line):
                    point_selection.clearSelection()

   
# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    # General logging for debug.
    # futil.log(f'{CMD_NAME} Validate Input Event')

    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    inputs = args.inputs
    
    # Verify the validity of the input values. This controls if the OK button is enabled or not.
    # spacing_control: adsk.core.ValueCommandInput = inputs.itemById(DIMENSION_SPACING)

    # futil.log(f'spacing_control.value="{spacing_control.value}" spacing_control.expression="{spacing_control.expression}" spacing_control.isValidExpression={spacing_control.isValidExpression}')
    



    # spacing_text = spacing_control.expression
    # spacing_error = True

    # unitsMgr = design.unitsManager
    # if unitsMgr.isValidExpression(spacing_text, unitsMgr.defaultLengthUnits):
    #     spacing = unitsMgr.evaluateExpression(spacing_text, unitsMgr.defaultLengthUnits)
    #     if spacing > 0:
    #         spacing_error = False

    # if spacing_error:
    #     args.areInputsValid = False

    #     futil.log(f'spacing_control.formattedText {spacing_control.formattedText})')
    #     
        
    #     return
    
    scale_parameter: adsk.core.TextBoxCommandInput = inputs.itemById(SCALE_PARAMETER)
    scale_parameter_value: adsk.core.TextBoxCommandInput = inputs.itemById(SCALE_PARAMETER_VALUE)
    method_control: adsk.core.DropDownCommandInput = inputs.itemById(METHOD)
    origin_mode: adsk.core.DropDownCommandInput = inputs.itemById(ORIGIN_MODE)
    point_selection: adsk.core.SelectionCommandInput = inputs.itemById(POINT_SELECTION)
    line_selection: adsk.core.SelectionCommandInput = inputs.itemById(LINE_SELECTION)
    parameter_name = scale_parameter.text

    # futil.log(f'parameter_name="{parameter_name}" len={parameter_name.__len__()} formatted={scale_parameter.formattedText}')
    

    if parameter_name.__len__() > 0:
        
        if not design:
            ui.messageBox('The DESIGN workspace must be active when running this command.', CMD_NAME)
            args.areInputsValid = False
            return
        parameter = design.allParameters.itemByName(parameter_name)
        if parameter:
            # check that its a valid length
            scale_parameter_value.formattedText = f'<span style=" color:#000000;">{parameter.value}</span>'
            args.areInputsValid = True
        else:
            args.areInputsValid = False
            # make it red
            # scale_parameter.formattedText = f'<span style=" color:#ff0000;">{parameter_name}</span>'
            scale_parameter_value.formattedText = f'<span style=" color:#ff0000;">Parameter not found</span>'
            return
    else:
        scale_parameter_value.formattedText = ''
    

    futil.log(f'trace 1')
    if method_control.listItems.item(METHOD_POLAR_INDEX).isSelected or origin_mode.listItems.item(1).isSelected:
        futil.log(f'trace 2')
        if point_selection.selectionCount == 0:
            futil.log(f'trace 3')
            args.areInputsValid = False
            return

    if method_control.listItems.item(METHOD_POLAR_INDEX).isSelected and line_selection.selectionCount == 0:
            futil.log(f'trace 4')
            args.areInputsValid = False
            return
        
    args.areInputsValid = True



# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []

    futil.log(f'command destroy complete')
    
