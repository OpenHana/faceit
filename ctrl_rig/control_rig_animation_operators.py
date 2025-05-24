import time
from typing import Iterable

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty


from ..animate.anim_utils import find_slot_by_handle, get_fcurves_from_slot
from ..core import faceit_utils as futils
from ..core import retarget_list_utils, shape_key_utils
from ..panels.draw_utils import (draw_ctrl_rig_action_layout,
                                 draw_shapes_action_layout)
from . import control_rig_data as ctrl_data
from . import control_rig_utils
from .control_rig_bake_utils import bake_shape_keys_to_ctrl_rig, bake_ctrl_rig_animation_to_shape_keys

CRIG_ACTION_SUFFIX = '_control_rig'


def update_enum(self, context):
    if self.action_source:
        new_action_name = self.action_source + CRIG_ACTION_SUFFIX
        self.new_action_name = new_action_name


def update_new_action_name(self, context):
    self.new_action_exists = bool(bpy.data.actions.get(self.new_action_name))


class FACEIT_OT_BakeShapeKeysToControlRig(bpy.types.Operator):
    '''Bake a Shape Key Action to the Control Rig'''
    bl_idname = 'faceit.bake_shape_keys_to_control_rig'
    bl_label = 'Bake Shape Key Action to Control Rig'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    resample_fcurves: bpy.props.BoolProperty(
        name='Resample Keyframes',
        default=False,
        description='Resampling the keyframes will result in better results for some sparse fcurves. The framerate of the animation will change to the scene framerate'
    )
    new_action_name: StringProperty(
        name='New Action Name',
        default="",
        options={'SKIP_SAVE', }
    )
    compensate_amplify_values: bpy.props.BoolProperty(
        name='Compensate Amplify Values',
        default=False,
        description='If this is enabled the amplify values will be inverted during bake, resulting in a one to one bake, even though amplify values are set to non-default values.'
    )
    compensate_arkit_amplify_values: bpy.props.BoolProperty(
        name='Compensate ARKit (Scene) Amplify Values',
        default=True,
        description='If this is enabled the amplify values will be inverted during bake, resulting in a one to one bake, even though amplify values are set to non-default values.'
    )
    ignore_use_animation: BoolProperty(
        name='Ignore Mute Property',
        description='Bake all Animation, regardless of the use_animation property in the arkit expressions list',
        default=False,
    )
    show_advanced_settings: BoolProperty(
        name='Show Advanced Settings',
        default=False,
        description='Blend in the advanced settings for this operator'
    )
    use_mocap_action: BoolProperty(
        name="Use Mocap Action",
        description="use the mocap action if True; Else: use the set bake action",
        default=True
    )
    frame_start: IntProperty(
        name='Start Frame',
        description='Start frame for the new keyframes. If append method is selected, the specified frame will present an offset to existing keyframes in the given action.',
        default=0,
        soft_min=0,
        soft_max=50000,
    )
    overwrite_method: EnumProperty(
        name='Overwrite Method',
        items=(
            ('REPLACE', 'Replace', 'Replace the entire Action. All existing keyframes will be removed.'),
            ('MIX', 'Mix', 'Mix with existing keyframes, replacing only the new range.'),
        ),
        options={'SKIP_SAVE', }
    )

    @classmethod
    def poll(cls, context):
        if context.mode in ('OBJECT', 'POSE'):
            c_rig = futils.get_faceit_control_armature()
            if c_rig:
                return c_rig.faceit_crig_objects

    def invoke(self, context, event):
        c_rig = futils.get_faceit_control_armature()
        if not c_rig.animation_data:
            c_rig.animation_data_create()
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def draw(self, context):
        c_rig = futils.get_faceit_control_armature()
        layout = self.layout
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False

        # row = col.row(align=True)
        # row.prop(context.scene, "faceit_mocap_action", icon='ACTION')
        draw_shapes_action_layout(col, context)
        col.separator()
        # row = col.row(align=True)
        source_action = context.scene.faceit_mocap_action
        if source_action:
            self.new_action_name = source_action.name + CRIG_ACTION_SUFFIX
        draw_ctrl_rig_action_layout(col, c_rig)
        col.separator()
        row = col.row()
        row.prop(self, 'overwrite_method', expand=True)
        row = col.row()
        row.prop(self, 'frame_start', icon='CON_TRANSFORM')
        col.use_property_split = False
        row = col.row(align=True)
        row.prop(self, 'show_advanced_settings', icon='COLLAPSEMENU')
        if self.show_advanced_settings:
            row = col.row(align=True)
            row.label(text='Options')
            row = col.row(align=True)
            row.prop(self, 'resample_fcurves')
            row = col.row(align=True)
            row.prop(self, 'compensate_amplify_values')
            row = col.row(align=True)
            row.prop(self, 'compensate_arkit_amplify_values')

    def execute(self, context):
        scene = context.scene
        c_rig = futils.get_faceit_control_armature()
        futils.set_hide_obj(c_rig, False)
        target_objects = control_rig_utils.get_crig_objects_list(c_rig)
        all_shapes_on_target_objects = shape_key_utils.get_shape_key_names_from_objects(target_objects)
        if not all_shapes_on_target_objects:
            self.report({'ERROR'}, 'The target objects have no shape keys. Did you register the correct object(s)?')
            return {'CANCELLED'}
        # The shape key action
        source_action = scene.faceit_mocap_action
        source_slot = None
        if bpy.app.version >= (4, 4, 0):
            source_slot = find_slot_by_handle(source_action, scene.faceit_mocap_slot_handle)
            if not source_slot:
                self.report({'ERROR'}, 'No source action slot specified. Cancelled')
                return {'CANCELLED'}
        source_fcurves = get_fcurves_from_slot(source_action, source_slot)

        if not source_action:
            self.report({'ERROR'}, 'Couldn\'t find a suitable action.')
            return {'CANCELLED'}
        if not any(['key_block' in fc.data_path for fc in source_action.fcurves]):
            self.report(
                {'WARNING'},
                'You can only retarget Shape Key Actions to the control rig. The result may not be expected')
        if not source_fcurves:
            self.report({'ERROR'}, 'There is no animation data in the source Action. Cancelled')
            return {'CANCELLED'}

        if self.resample_fcurves:
            source_action = source_action.copy()
        # Get ctrl rig action
        anim_data = c_rig.animation_data
        target_action = anim_data.action
        target_slot = None
        if not target_action:
            target_action = bpy.data.actions.new(self.new_action_name)
            self.report({'INFO'}, f"Created new Action with name {self.new_action_name}")
            c_rig.animation_data.action = target_action
        if bpy.app.version >= (4, 4, 0):
            target_slot = anim_data.action_slot
            if not target_slot:
                target_slot = target_action.slots.new('OBJECT', c_rig.name)
                anim_data.action_slot = target_slot

        bake_shape_keys_to_ctrl_rig(
            context=context,
            c_rig=c_rig,
            source_action=source_action,
            source_slot=source_slot,
            target_action=target_action,
            target_slot=target_slot,
            resample_fcurves=self.resample_fcurves,
            mix_method=self.overwrite_method,
            compensate_amplify_values=self.compensate_amplify_values,
            compensate_arkit_amplify_values=self.compensate_arkit_amplify_values,
            frame_start=self.frame_start,
        )
        frame_range = futils.get_action_frame_range(target_action)
        if frame_range.length == 0:
            self.report({'ERROR'}, 'The action has no keyframes.')
            return {'CANCELLED'}
        scene.frame_start = int(frame_range[0])
        scene.frame_end = int(frame_range[1])

        self.report({'INFO'}, 'Shape Key Animation baked to Control Rig.')
        # if not self.use_mocap_action:
        #     bpy.data.actions.remove(source_action, do_unlink=True, do_ui_user=True)
        return {'FINISHED'}


def get_enum_non_sk_actions(self, context):
    global actions
    actions = []
    for a in bpy.data.actions:
        if any(['bone' in fc.data_path for fc in a.fcurves]):
            # if not any(['key_block' in fc.data_path for fc in a.fcurves]):
            actions.append((a.name,) * 3)

    return actions


def update_enum_non_sk(self, context):
    if self.action_source:
        new_action_name = self.action_source
        if new_action_name.endswith(CRIG_ACTION_SUFFIX):
            # new_action_name = new_action_name.strip(CRIG_ACTION_SUFFIX)
            new_action_name = new_action_name[:-len(CRIG_ACTION_SUFFIX)]

        self.new_action_name = new_action_name


def after_bake_crig_operation(op, c_rig):
    if op == 'REMOVE':
        bpy.data.objects.remove(c_rig)
    elif op == 'HIDE':
        c_rig.hide_set(state=True)
    else:
        pass


class FACEIT_OT_BakeControlRigToShapeKeys(bpy.types.Operator):
    '''Bake the animation from the control rig to the target shapes'''
    bl_idname = 'faceit.bake_control_rig_to_shape_keys'
    bl_label = 'Bake Control Rig Action to Shape Keys'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    c_rig_operation: EnumProperty(
        name='Operation after Baking',
        items=(
            ('REMOVE', 'Remove Control Rig', 'Remove the Control Rig from the Scene. Can result in data loss'),
            ('HIDE', 'Hide Control Rig', 'Hide the Control Rig in the Scene. Unhide through the Outliner'),
            ('DISCONNECT', 'Disconnect Drivers', 'Only disconnect the drivers. Keep the rig visible.'),
        ),
        default='DISCONNECT'
    )

    # bake_method: EnumProperty(
    #     name='Bake Method',
    #     items=[('FAST', 'Fast Method',
    #             'This method is very fast. It normalizes the existing fcurves into the shape key ranges. Does not work for animation layers.'),
    #            ('SLOW', 'Slow Method',
    #             'This method is very slow. Evaluates the values directly from the drivers. Works for animation layers too.')],
    #     default='FAST',)

    action_source: EnumProperty(
        name='Action',
        items=get_enum_non_sk_actions,
        update=update_enum_non_sk,
    )

    action_target: EnumProperty(
        name='Action',
        items=(
            ('NEW', 'Create New Action', 'Create a new action on the control rig'),
            ('ACTIVE', 'Active Action', 'Use the current action from the control rig'),
        )
    )

    new_action_name: StringProperty(
        name='Action',
        default='controls_action',
        update=update_new_action_name,
    )

    new_action_exists: BoolProperty(
        name='Action Exists',
        default=False,
    )

    active_action_name: StringProperty(
        name='Action',
        default=''
    )

    overwrite_method: EnumProperty(
        name='Overwrite Method',
        items=(
            ('REPLACE', 'Replace', 'Replace the entire Action. All existing keyframes will be removed.'),
            ('MIX', 'Mix', 'Mix with existing keyframes, replacing only the new range.'),
        ),
        options={'SKIP_SAVE', }
    )

    resample_fcurves: BoolProperty(
        name='Resample Keyframes',
        default=False,
        description='Resampling the keyframes will result in better results for some sparse fcurves.'
    )

    copy_fcurve_properties: BoolProperty(
        name='Copy Fcurve Data',
        default=False,
        description='Try to copy all fcurve properties, including keyframe handles and modifiers.'
    )
    copy_fcurve_modifiers: BoolProperty(
        name='Copy Modifiers',
        default=False,
        description='Try to copy all fcurve properties, including keyframe handles and modifiers.'
    )

    copy_fcurve_handles: BoolProperty(
        name='Copy Handles',
        default=False,
        description='Try to copy all fcurve properties, including keyframe handles and modifiers.'
    )

    compensate_amplify_values: BoolProperty(
        name='Bake Amplify Values',
        default=True,
        description='Disabling this can disturb the baked motion.'
    )

    ignore_use_animation: BoolProperty(
        name='Ignore Mute Property',
        description='Bake all Animation, regardless of the use_animation property in the arkit expressions list',
        default=False,
    )

    show_advanced_settings: BoolProperty(
        name='Show Advanced Settings',
        description='Blend in the advanced settings for this operator',
        default=False,
    )

    frame_start: IntProperty(
        name='Start Frame',
        default=0,
        options={'SKIP_SAVE', }
    )

    @classmethod
    def poll(cls, context):
        if context.mode in ('OBJECT', 'POSE'):
            c_rig = futils.get_faceit_control_armature()
            if c_rig:
                return c_rig.faceit_crig_objects

    def invoke(self, context, event):

        # Get current Control Rig action
        rig = futils.get_faceit_control_armature()
        if not rig.animation_data:
            rig.animation_data_create()

        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        c_rig = futils.get_faceit_control_armature()
        col.use_property_split = True
        col.use_property_decorate = False

        draw_ctrl_rig_action_layout(col, c_rig)
        col.separator()
        draw_shapes_action_layout(col, context)

        col.separator()
        row = col.row()
        row.prop(self, 'overwrite_method', expand=True)
        row = col.row()
        row.prop(self, 'frame_start', icon='CON_TRANSFORM')
        col.use_property_split = False
        row = col.row(align=True)
        row.prop(self, 'show_advanced_settings', icon='COLLAPSEMENU')
        if self.show_advanced_settings:
            row = col.row(align=True)
            row.prop(self, 'resample_fcurves')

    def execute(self, context):

        scene = context.scene

        ctrl_rig = futils.get_faceit_control_armature()

        target_objects = control_rig_utils.get_crig_objects_list(ctrl_rig)
        if not target_objects:
            target_objects = futils.get_faceit_objects_list()

        crig_targets = ctrl_rig.faceit_crig_targets
        if not crig_targets:
            crig_targets = scene.faceit_arkit_retarget_shapes

        all_shapes_on_target_objects = shape_key_utils.get_shape_key_names_from_objects(target_objects)
        if not all_shapes_on_target_objects:
            self.report({'ERROR'}, 'The target objects have no shape keys. Did you register the correct object(s)?')
            return {'CANCELLED'}
        if not control_rig_utils.is_control_rig_connected(ctrl_rig):
            self.report({'ERROR'}, 'The Control Rig is not connected to the target objects.')
            return {'CANCELLED'}
        # The rig action
        source_action = ctrl_rig.animation_data.action
        source_slot = None
        if not source_action:
            self.report({'ERROR'}, 'You need to choose a valid source action.')
            return {'CANCELLED'}
        if not source_action.fcurves:
            self.report({'ERROR'}, f'There is no animation data in the source Action {source_action.name}.')
            return {'CANCELLED'}
        if source_action.name.endswith(CRIG_ACTION_SUFFIX):
            self.new_action_name = source_action.name.strip(CRIG_ACTION_SUFFIX)
        else:
            self.new_action_name = source_action.name + "_retarget"
        if bpy.app.version >= (4, 4, 0):
            source_slot = ctrl_rig.animation_data.action_slot
            if not source_slot:
                self.report({'ERROR'}, 'No source action slot specified. Cancelled')
                return {'CANCELLED'}
        target_shapes_dict = retarget_list_utils.get_target_shapes_dict(crig_targets)
        if not target_shapes_dict:
            self.report({'ERROR'}, 'No retarget shapes found. Initialize in Shapes panel.')
            return {'CANCELLED'}
        target_action = scene.faceit_mocap_action
        target_slot = None
        if not target_action:
            # Get target action
            target_action = bpy.data.actions.new(name=self.new_action_name)
            target_action.use_fake_user = True
            # Get target objects and shapes
        if bpy.app.version >= (4, 4, 0):
            # get the mocap slot
            if target_action is scene.faceit_mocap_action:
                slot_handle = scene.faceit_mocap_slot_handle
                if slot_handle:
                    for slot in target_action.slots:
                        if slot.handle == slot_handle:
                            target_slot = slot
                            break
            if target_slot is None:
                target_slot = target_action.slots.get("KEShapeKeys")
                if target_slot is None:
                    target_slot = target_action.slots.new(id_type='KEY', name="ShapeKeys")
            scene.faceit_mocap_slot_handle = target_slot.handle
        scene.faceit_mocap_action = target_action

        bake_ctrl_rig_animation_to_shape_keys(
            context=context,
            source_action=source_action,
            source_slot=source_slot,
            target_action=target_action,
            target_slot=target_slot,
            target_objects=target_objects,
            resample_fcurves=self.resample_fcurves,
            mix_method=self.overwrite_method,
            start_frame=self.frame_start,
        )
        bpy.ops.faceit.remove_control_drivers()
        after_bake_crig_operation(self.c_rig_operation, ctrl_rig)

        self.report({'INFO'}, 'Animation baked to Shape Keys. Removed the drivers.')

        return {'FINISHED'}
