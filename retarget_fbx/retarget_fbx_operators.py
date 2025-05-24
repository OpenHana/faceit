
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Action, Object

from ..animate.anim_utils import find_slot_by_handle
from ..core import faceit_utils as futils
from ..core import fc_dr_utils
from ..core import shape_key_utils as sk_utils
from ..ctrl_rig import control_rig_utils as ctrl_utils
from ..ctrl_rig.control_rig_animation_operators import CRIG_ACTION_SUFFIX


def get_enum_sk_actions(self, context):
    global actions
    actions = []
    for a in bpy.data.actions:
        if any(['key_block' in fc.data_path for fc in a.fcurves]):
            actions.append((a.name,) * 3)
    return actions


def update_action_name(self, context):
    self.new_name = self.retarget_action + self.suffix


class FACEIT_OT_RetargetFBXAction(bpy.types.Operator):
    '''Retarget the Source Action to the populated target Shapes '''
    bl_idname = 'faceit.retarget_fbx_action'
    bl_label = 'Initialize Retargeting'
    bl_options = {'UNDO', 'INTERNAL', 'REGISTER'}

    retarget_action: EnumProperty(
        name='Source Action',
        items=get_enum_sk_actions,
        description='the Shape Key Action to Retarget',
        update=update_action_name,
    )
    suffix: StringProperty(
        name='Add Suffix',
        default='_retargeted',
        update=update_action_name,
    )
    new_name: StringProperty(
        name='New Action Name',
        description='Specify Name of the New Action'
    )
    populate_faceit: BoolProperty(
        name='Populate to all Faceit Objects',
        description='Activate the retargeted Action on all Faceit Objects.',
        default=True,
    )
    keep_undetected_shapes: BoolProperty(
        name='Keep undetected Fcurves',
        default=False,
    )
    bake_to_control_rig: BoolProperty(
        name='Bake to Control Rig',
        default=False,
        description='Loads the mocap action directly on the control rig. Creates a temp Action with the 52 Shape Keys.',
    )
    show_advanced_settings: BoolProperty(
        name='Show Advanced Settings',
        default=False,
        description='Blend in the advanced settings for this operator'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.can_bake_to_control_rig = False

    @classmethod
    def poll(cls, context):

        retarget_fbx_props = context.scene.faceit_retarget_fbx_mapping

        return retarget_fbx_props.mapping_list

    def invoke(self, context, event):
        retarget_fbx_props = context.scene.faceit_retarget_fbx_mapping
        source_action = None
        if retarget_fbx_props.mapping_source == 'OBJECT':
            source_obj = retarget_fbx_props.source_obj
            if sk_utils.has_shape_keys(source_obj):
                if source_obj.data.shape_keys.animation_data:
                    source_action = source_obj.data.shape_keys.animation_data.action
                    if source_action is None:
                        self.report({'ERROR'}, f'The object {source_obj.name} has no shape key action to retarget.')
                        return {'CANCELLED'}
        else:
            source_action = retarget_fbx_props.source_action
            if source_action is None:
                self.report({'You need to register a source action that contains shape key data.'})
                return {'CANCELLED'}
        if any(['key_block' in fc.data_path for fc in source_action.fcurves]):
            self.new_name = source_action.name + '_retargeted'
            self.retarget_action = source_action.name
        else:
            self.report({f'The source action {source_action.name} contains no shape key data.'})
            return {'CANCELLED'}
        if retarget_fbx_props.mapping_target == 'CRIG':
            self.can_bake_to_control_rig = bool(futils.get_faceit_control_armature())
            if self.can_bake_to_control_rig:
                self.bake_to_control_rig = True

        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.prop(self, 'retarget_action', icon='ACTION')
        # row = layout.row()
        # row.prop(self, 'suffix')

        row = layout.row()
        row.prop(self, 'new_name', icon='ACTION')

        if self.can_bake_to_control_rig:
            row = layout.row()
            row.prop(self, 'bake_to_control_rig', icon='CON_ARMATURE')
        if self.bake_to_control_rig:
            row = layout.row()
            row.label(text='Only works for ARKit recordings.')
        else:
            # row = layout.row()
            row = layout.row(align=True)
            row.prop(self, 'show_advanced_settings', icon='COLLAPSEMENU')
            if self.show_advanced_settings:
                row = layout.row()
                row.prop(self, 'keep_undetected_shapes', icon='ACTION')

    def execute(self, context):
        scene = context.scene
        retarget_fbx_props = scene.faceit_retarget_fbx_mapping
        retarget_list = retarget_fbx_props.mapping_list
        source_action = None
        source_action = bpy.data.actions.get(self.retarget_action)
        if not source_action:
            self.report(
                {'ERROR'},
                'No source Action found. choose a valid Shape Keys Action! ')
            return {'CANCELLED'}

        if self.bake_to_control_rig:
            c_rig = futils.get_faceit_control_armature()
            if not c_rig:
                self.report(
                    {'ERROR'},
                    'Can\'t find the active control rig. Please create/choose control rig first or import directly to the meshes.')
                return {'CANCELLED'}

            a_remove = bpy.data.actions.get('mocap_import')
            if a_remove:
                bpy.data.actions.remove(a_remove)

            target_action = source_action.copy()
            target_action.name = 'mocap_import'
            # target_action = bpy.data.actions.new('mocap_import')
        else:
            target_action = bpy.data.actions.get(self.new_name)
            if target_action:
                bpy.data.actions.remove(target_action)
            target_action = source_action.copy()
            target_action.name = self.new_name

        all_fcurve_data_paths = [fc.data_path for fc in source_action.fcurves]
        retargeted_any = False
        for item in retarget_list:
            if item.use_animation is False:
                continue
            target_shapes = item.target_shapes
            target_shapes_list = [t.name for t in target_shapes]
            source_shape = item.name
            data_paths = [
                'key_blocks["{}"].value'.format(source_shape),
                'key_blocks["{}"].slider_min'.format(source_shape),
                'key_blocks["{}"].slider_max'.format(source_shape)
            ]
            for dp in data_paths:
                fc = target_action.fcurves.find(dp)
                if fc:
                    source_is_target_shape = False
                    for target_shape in target_shapes_list:
                        fc_data_copy = fc_dr_utils.copy_fcurve_data(fc)
                        new_dp = dp.replace(source_shape, target_shape)
                        # Check if Source and Target Shape have the same data path
                        if not source_is_target_shape:
                            source_is_target_shape = bool(dp != new_dp)
                        fc_dr_utils.populate_stored_fcurve_data(
                            fc_data_copy, dp=new_dp, action=target_action, join_with_existing_data=False)
                        retargeted_any = True

                    if source_is_target_shape:
                        target_action.fcurves.remove(fc)
                    all_fcurve_data_paths.remove(dp)

        if all_fcurve_data_paths:
            for dp in all_fcurve_data_paths:
                self.report({'WARNING'}, 'Did not retarget fcurve with data_path {} '.format(dp))
                if not self.keep_undetected_shapes:
                    fc = target_action.fcurves.find(dp)
                    if fc:
                        target_action.fcurves.remove(fc)
        if not target_action.fcurves or not retargeted_any:
            self.report(
                {'ERROR'},
                'The animation data could not be retargeted. Probably there is something wrong with the mapping or data.')
            bpy.data.actions.remove(target_action)
            return {'CANCELLED'}
        mapping_target = retarget_fbx_props.mapping_target

        if self.bake_to_control_rig:
            if target_action.fcurves:
                current_shape_action: Action = scene.faceit_mocap_action
                current_shape_slot = None
                if bpy.app.version >= (4, 4, 0):
                    current_shape_slot = find_slot_by_handle(target_action, scene.faceit_mocap_slot_handle)
                scene.faceit_mocap_action = target_action
                try:
                    bpy.ops.faceit.bake_shape_keys_to_control_rig(
                        'EXEC_DEFAULT',
                        use_mocap_action=False,
                        overwrite_method='REPLACE',
                        new_action_name=target_action.name + CRIG_ACTION_SUFFIX,
                        compensate_amplify_values=True,
                    )
                except RuntimeError:
                    self.report({'ERROR'}, "Failed to bake shape keys to control rig.")
                if current_shape_action:
                    if current_shape_slot:
                        scene.faceit_mocap_slot_handle = current_shape_slot.handle
                    scene.faceit_mocap_action = current_shape_action
                bpy.data.actions.remove(target_action, do_unlink=True)
        else:
            if mapping_target == 'TARGET':
                obj: Object = retarget_fbx_props.target_obj
                adt = obj.data.shape_keys.animation_data
                if adt is None:
                    adt = obj.data.shape_keys.animation_data_create()
                adt.action = target_action
                if adt.action_suitable_slots:
                    adt.action_slot = adt.action_suitable_slots[0]
            else:
                scene.faceit_mocap_action = target_action
        self.report({'INFO'}, "Succesfully retargeted the animation data.")
        for region in context.area.regions:
            region.tag_redraw()
        return {'FINISHED'}
