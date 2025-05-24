import bpy
import blf
from bpy.types import ID, UILayout, Context
from bpy.props import EnumProperty
import textwrap

from ..animate.anim_utils import find_slot_by_handle


from .. import __package__ as base_package


def draw_web_link(layout, link, text_ui='', show_always=False):
    '''Draws a Web @link in the given @layout. Optionally with plain @text_ui'''
    if bpy.context.preferences.addons[base_package].preferences.web_links or show_always:
        web = layout.operator('faceit.open_web', text=text_ui, icon='QUESTION')
        web.link = link


def wrap_text(text: str, context: Context, in_operator=False):
    # https://gist.github.com/semagnum/b881b3b4d11c1514dac079af5bda8f7f
    return_text = []
    row_text = ''
    system = context.preferences.system
    ui_scale = system.ui_scale
    if in_operator:
        width = 750 * (ui_scale / 2)
    else:
        width = context.region.width
    width = (4 / (5 * ui_scale)) * width
    # dpi = 72 if system.ui_scale >= 1 else system.dpi
    if bpy.app.version < (3, 6):
        blf.size(0, 11, 72)
    else:
        blf.size(0, 11)
    # text = "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet."
    line_len = 50
    for word in text.split():
        word = f' {word}'
        line_len, _ = blf.dimensions(0, row_text + word)
        if line_len <= (width - 16):
            row_text += word
        else:
            return_text.append(row_text)
            row_text = word
    if row_text:
        return_text.append(row_text)
    return return_text


def draw_text_block(context: Context, layout: UILayout, text='', heading='', heading_icon='ERROR', alert=False, in_operator=False) -> UILayout:
    '''wrap a block of text into multiple lines'''
    box = layout.box()
    col = box.column(align=True)
    if alert:
        col.alert = True
    if heading:
        row = col.row(align=True)
        row.label(text=heading, icon=heading_icon)
    for txt_row in wrap_text(text, context, in_operator=in_operator):
        row = col.row(align=True)
        row.label(text=txt_row)
    return col


def get_slot_items(self, context):
    """
    Get the items for the slot selector.
    """
    action = context.scene.faceit_mocap_action
    if not action:
        return []
    list = []
    for slot in action.slots:
        if slot.target_id_type == self.target_id_type:
            list.append((str(slot.handle), slot.name_display, slot.identifier))
    return list


class FACEIT_OT_SelectSlotMenu(bpy.types.Operator):
    bl_idname = "faceit.select_slot_menu"
    bl_label = "Select Slot"
    bl_description = "Select a slot for the action"
    bl_options = {'REGISTER', 'UNDO'}

    target_id_type: EnumProperty(
        items=[('ACTION', 'ACTION', 'ACTION'),
               ('ARMATURE', 'ARMATURE', 'ARMATURE'),
               ('BRUSH', 'BRUSH', 'BRUSH'),
               ('CACHEFILE', 'CACHEFILE', 'CACHEFILE'),
               ('CAMERA', 'CAMERA', 'CAMERA'),
               ('COLLECTION', 'COLLECTION', 'COLLECTION'),
               ('CURVE', 'CURVE', 'CURVE'),
               ('CURVES', 'CURVES', 'CURVES'),
               ('FONT', 'FONT', 'FONT'),
               ('GREASEPENCIL', 'GREASEPENCIL', 'GREASEPENCIL'),
               ('GREASEPENCIL_V3', 'GREASEPENCIL_V3', 'GREASEPENCIL_V3'),
               ('IMAGE', 'IMAGE', 'IMAGE'),
               ('KEY', 'KEY', 'KEY'),
               ('LATTICE', 'LATTICE', 'LATTICE'),
               ('LIBRARY', 'LIBRARY', 'LIBRARY'),
               ('LIGHT', 'LIGHT', 'LIGHT'),
               ('LIGHT_PROBE', 'LIGHT_PROBE', 'LIGHT_PROBE'),
               ('LINESTYLE', 'LINESTYLE', 'LINESTYLE'),
               ('MASK', 'MASK', 'MASK'),
               ('MATERIAL', 'MATERIAL', 'MATERIAL'),
               ('MESH', 'MESH', 'MESH'),
               ('META', 'META', 'META'),
               ('MOVIECLIP', 'MOVIECLIP', 'MOVIECLIP'),
               ('NODETREE', 'NODETREE', 'NODETREE'),
               ('OBJECT', 'OBJECT', 'OBJECT'),
               ('PAINTCURVE', 'PAINTCURVE', 'PAINTCURVE'),
               ('PALETTE', 'PALETTE', 'PALETTE'),
               ('PARTICLE', 'PARTICLE', 'PARTICLE'),
               ('POINTCLOUD', 'POINTCLOUD', 'POINTCLOUD'),
               ('SCENE', 'SCENE', 'SCENE'),
               ('SCREEN', 'SCREEN', 'SCREEN'),
               ('SOUND', 'SOUND', 'SOUND'),
               ('SPEAKER', 'SPEAKER', 'SPEAKER'),
               ('TEXT', 'TEXT', 'TEXT'),
               ('TEXTURE', 'TEXTURE', 'TEXTURE'),
               ('VOLUME', 'VOLUME', 'VOLUME'),
               ('WINDOWMANAGER', 'WINDOWMANAGER', 'WINDOWMANAGER'),
               ('WORKSPACE', 'WORKSPACE', 'WORKSPACE'),
               ('WORLD', 'WORLD', 'WORLD'),
               ('UNSPECIFIED', 'UNSPECIFIED', 'UNSPECIFIED'),
               ],
        name="Target ID Type",
        description="The type of the target ID",
        default='KEY',
    )  # type: ignore
    slot_handle: EnumProperty(
        items=get_slot_items,
        name="Slot",
        description="Select a slot for the action",
    )

    def execute(self, context):
        action = context.scene.faceit_mocap_action
        if not action:
            return {'CANCELLED'}
        context.scene.faceit_mocap_slot_handle = int(self.slot_handle)
        bpy.ops.faceit.populate_action(
            action_name=action.name,
            set_mocap_action=False,
            activate_slot=True,
        )
        return {'FINISHED'}


def draw_shapes_action_layout(layout, context, split=True):
    """
    Draw the mocap shapes action layout and slot selector.
    """
    if split:
        row = layout.row(align=True)
        sub = row.split(factor=0.4, align=True)
        sub.alignment = 'RIGHT'
        sub.label(text="Shapes Action")
    else:
        sub = layout
    col = sub.column(align=True)
    row = col.row(align=True)
    row.template_ID(
        context.scene,
        "faceit_mocap_action",
        new='faceit.new_action',
        unlink='faceit.unlink_shapes_action'
    )
    if bpy.app.version >= (4, 4, 0):
        action = context.scene.faceit_mocap_action
        if not action:
            return
        row = col.row(align=True)
        slot_handle = bpy.context.scene.faceit_mocap_slot_handle
        slot = find_slot_by_handle(action, slot_handle)
        # if slot:
        #     text = slot.name_display
        # else:
        #     text = ""
        row.operator_menu_enum("faceit.select_slot_menu", property="slot_handle", text="", icon='ACTION_SLOT',)
        if slot:
            row.prop(slot, "name_display", text="")
            row.operator("faceit.new_mocap_action_slot", text="", icon='DUPLICATE')
            row.operator("faceit.unlink_active_shapes_slot", text="", icon='X')
        else:
            row.operator("faceit.new_mocap_action_slot", text="New", icon='ADD')


def draw_head_targets_layout(layout: UILayout, scene=None, show_head_action=True):
    if scene is None:
        scene = bpy.context.scene

    split_layout = layout.use_property_split
    layout.use_property_split = True
    layout.use_property_decorate = False
    head_obj = scene.faceit_head_target_object
    row = layout.row(align=True)
    row.prop(scene, "faceit_head_target_object")
    if head_obj:
        row = layout.row(align=True)
        if head_obj.type == "ARMATURE":
            row.prop_search(
                scene,
                "faceit_head_sub_target",
                head_obj.data,
                "bones"
            )
        if show_head_action:
            draw_head_action_layout(layout, head_obj)
    layout.use_property_split = split_layout


def draw_action_and_slot_selector_for_id(layout: UILayout, animated_id: ID, new="action.new", unlink="faceit.unlink_action"):
    """
    Draw the action and slot selector for an ID, using the given layout.

    The ID must be an animatable ID.

    Note that the slot selector is only drawn when the ID has an assigned
    Action.
    """
    layout.context_pointer_set("animated_id", animated_id)
    layout.template_action(animated_id, new=new, unlink=unlink)
    if bpy.app.version >= (4, 4, 0):
        adt = animated_id.animation_data
        if not adt or not adt.action:
            return

        # Only show the slot selector when a layered Action is assigned.
        if adt.action.is_action_layered:
            # layout.context_pointer_set("animated_id", animated_id)
            layout.template_search(
                adt, "action_slot",
                adt, "action_suitable_slots",
                new="anim.slot_new_for_id",
                unlink="anim.slot_unassign_from_id",
            )


def draw_head_action_layout(layout, head_obj):
    row = layout.row()
    sub = row.split(factor=0.4)
    sub.alignment = 'RIGHT'
    sub.label(text="Head Action")
    col = sub.column(align=True)
    draw_action_and_slot_selector_for_id(col, head_obj, new='faceit.new_head_action')


def draw_eye_targets_layout(layout: UILayout, context, show_eye_action=True):
    scene = context.scene
    split_layout = layout.use_property_split
    layout.use_property_split = True
    layout.use_property_decorate = False
    row = layout.row(align=True)
    row.prop(scene, "faceit_eye_target_rig")
    eye_rig = scene.faceit_eye_target_rig
    if eye_rig:
        row = layout.row(align=True)
        row.prop_search(
            scene,
            "faceit_eye_L_sub_target",
            eye_rig.data,
            "bones"
        )
        row = layout.row(align=True)
        row.prop_search(
            scene,
            "faceit_eye_R_sub_target",
            eye_rig.data,
            "bones"
        )
        if show_eye_action:
            draw_eye_action_layout(layout, eye_rig)
    layout.use_property_split = split_layout


def draw_eye_action_layout(layout: UILayout, eye_rig):
    row = layout.row()
    sub = row.split(factor=0.4)
    sub.alignment = 'RIGHT'
    sub.label(text="Eyes Action")
    col = sub.column(align=True)
    draw_action_and_slot_selector_for_id(col, eye_rig, new='faceit.new_eye_action')


def draw_ctrl_rig_action_layout(layout: UILayout, ctrl_rig, use_split=True):
    row = layout.row()
    if use_split:
        sub = row.split(factor=0.4)
        sub.alignment = 'RIGHT'
        sub.label(text="Ctrl Rig Action")
        col = sub.column(align=True)
    else:
        col = row.column(align=True)
    draw_action_and_slot_selector_for_id(col, ctrl_rig, new='faceit.new_ctrl_rig_action')
    # sub.template_ID(ctrl_rig.animation_data, "action", new='faceit.new_ctrl_rig_action')
