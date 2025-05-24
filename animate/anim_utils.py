import bpy
from bpy.types import Action, FCurve, ID, ActionFCurves
from bpy_extras import anim_utils


def find_slot_by_handle(action: Action, handle: int):
    """
    Find a slot by its handle in the action.

    params:
        action: bpy.types.Action
        handle: int - the handle of the slot to find

    returns:
        slot: bpy.types.ActionSlot - the slot with the given handle
    """
    for slot in action.slots:
        if slot.handle == handle:
            return slot
    return None


def get_active_animation_fcurves_from_id(id: ID = None) -> list[FCurve]:
    """
    Get the active animation fcurves from the ID, if there are any.

    params:
        id: bpy.types.ID - the ID to get the fcurves from

    returns:
        fcurves: list[bpy.types.FCurve] - the fcurves of the animation
    """
    if id is None:
        return []
    adt = id.animation_data
    if not adt:
        return []
    action = adt.action
    if not action:
        return []
    if bpy.app.version >= (4, 4, 0):
        slot = adt.action_slot
        if slot is None:
            pass
        else:
            channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
            if channelbag:
                fcurves = channelbag.fcurves
    else:
        fcurves = action.fcurves
    return fcurves


def get_slots_of_id_type(action: Action, target_id_type: str) -> list:
    """
    Get the slots of the given ID type from the action.

    params:
        action: bpy.types.Action
        id_type: str - the type of ID to get the slots from

    returns:
        slots: list[bpy.types.ActionSlot] - the slots of the given ID type
    """
    slots = []
    for slot in action.slots:
        if slot.target_id_type == target_id_type:
            slots.append(slot)
    return slots


def get_valid_slots_for_id(action: Action, target_id: ID) -> list:
    """
    Get the valid slots for the given ID from the action.

    params:
        action: bpy.types.Action
        target_id: bpy.types.ID - the ID to get the slots for

    returns:
        slots: list[bpy.types.ActionSlot] - the valid slots for the given ID
    """
    slots = []
    for slot in action.slots:
        if slot.target_id_type == target_id.id_type:
            slots.append(slot)
    return slots


def get_fcurves_from_slot(action: Action, slot=None, ensure=True) -> ActionFCurves:
    """
    Get the fcurves from the given slot.

    params:
        action: bpy.types.Action
        slot: bpy.types.ActionSlot - the slot to get the fcurves from

    returns:
        fcurves: list[bpy.types.FCurve] - the fcurves of the slot
    """
    if bpy.app.version >= (4, 4, 0):
        channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
        if channelbag:
            fcurves = channelbag.fcurves
        elif ensure:
            channelbag = anim_utils._ensure_channelbag_exists(action, slot)
            fcurves = channelbag.fcurves
    else:
        fcurves = action.fcurves
    return fcurves
