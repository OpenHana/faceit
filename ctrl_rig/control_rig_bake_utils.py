from typing import Iterable

import bpy
import numpy as np
from bpy.types import Action, Context, Object, ActionFCurves

from ..animate.anim_utils import get_fcurves_from_slot
from ..core.shape_key_utils import has_shape_keys
from ..core import faceit_utils as futils
from ..core import fc_dr_utils
from . import control_rig_utils
from .control_rig_data import get_bone_animation_data


def resample_fcurves(fc, start, end):
    fc.convert_to_samples(start, end)
    fc.convert_to_keyframes(start, end)


def scale_to_new_range(
        kf_data, min_range, max_range, sk_max, sk_min, range, main_dir=1, is_scale=False,
        amplify_compensation=1.0):
    '''Scale the keyframe values from shapekeys min/max to the bone range min/max
    @kf_data: the keyframes on shapekey fcurve
    @min_range: new minimum - the minimum range of motion for the bone
    @max_range: new maximum - the max range of motion for the bone
    @sk_max: old maximum - shape_key.slider_max
    @sk_min: old minimum - shape_key.slider_min
    @main_dir: the direction of movement for the target bone. Needed to negate the values
    @amplify_compensation (float): Compensate Amplify values that are baked into the shape key animation
    '''
    # Split the frames from animation values
    # col 0 holds the frames
    frames = kf_data[:, 0]
    # col 1 holds the values
    data = kf_data[:, 1]
    data /= amplify_compensation
    # pos, neg, all bone direction
    if range == 'pos':
        pass
    elif range == 'neg':
        max_range = min_range
    # negative and positive values for shape keys alloud.
    if range == 'all':
        if main_dir == -1:
            max_range = min_range
    if is_scale:
        min_range = 1
    else:
        min_range = 0
    # bring the keframe values from the max/min shape key values into the max/min bone range
    scaled_data = ((max_range - min_range) * ((data - sk_min)) / (sk_max - sk_min)) + min_range
    recombined_data = np.vstack((frames, scaled_data)).T
    return recombined_data


def populate_motion_data_dict(dp, array_index, new_kf_data, is_scale=False, bone_motion_data=None):
    if bone_motion_data is None:
        bone_motion_data = {}

    # When the target bone uses scale then it needs to receive 3 FCurves (1 for each channel)
    if is_scale:
        array_index = range(3)
    if not isinstance(array_index, Iterable):
        array_index = [array_index]
    for i in array_index:
        # Used to find the fcurve
        fcurve_identifier = '{}_{}'.format(dp, i)
        # Store the motion data for every fcurve in bone_motion_data:
        motion_data = bone_motion_data.get(fcurve_identifier)
        # If there is an entry in the list, then the fcurve controls multiple shapes (e.g pos and neg range)
        if motion_data and 'scale' not in dp:
            # add the keyframe data to the existing motion
            try:
                motion_data['kf_data'][:, 1] += new_kf_data[:, 1]
            except ValueError:
                print('motion data on dp {} cant get added...'.format(dp))
        else:
            # create a new entry
            bone_motion_data[fcurve_identifier] = {
                'data_path': dp,
                'array_index': i,
                'kf_data': new_kf_data,
            }


def bake_shape_keys_to_ctrl_rig(
        context: Context,
        c_rig: Object = None,
        source_action: Action = None,
        source_slot=None,
        target_action: Action = None,
        target_slot=None,
        resample_fcurves: bool = False,
        mix_method: str = 'REPLACE',
        compensate_amplify_values: bool = False,
        compensate_arkit_amplify_values: bool = False,
        frame_start: int = 0,):
    """
    Bake the shape key animation to the control rig.
    """

    crig_targets = c_rig.faceit_crig_targets
    crig_version = c_rig.get('ctrl_rig_version', 1.0)

    # collect all existing fcurves that are relevant.
    arkit_curves_values = {}
    missing_animation = []

    if not source_action:
        return
    if not target_action:
        return

    frame_range = futils.get_action_frame_range(source_action)
    source_fcurves: ActionFCurves = get_fcurves_from_slot(source_action, source_slot)

    for shape_item in crig_targets:
        if crig_version > 1.2 and shape_item.name in ('eyeLookUpRight', 'eyeLookDownRight', 'eyeLookInRight', 'eyeLookOutRight'):
            continue
        for target_shape in shape_item.target_shapes:
            dp = 'key_blocks["{}"].value'.format(target_shape.name)
            fc = source_fcurves.find(dp)
            if fc:
                if not fc.is_empty:
                    if resample_fcurves:
                        resample_fcurves(fc, int(frame_range[0]), int(frame_range[1]))
                    arkit_curves_values[shape_item.name] = {
                        'fcurve': fc,
                    }
            else:
                missing_animation.append(target_shape.name)
    bone_motion_data = {}

    # Create the new fcurves for the control rig action
    for sk_name, curve_values in arkit_curves_values.items():
        fc = curve_values['fcurve']
        # Get keyframe_data from the shape key fcurve
        kf_data = fc_dr_utils.kf_data_to_numpy_array(fc)
        # Get the bone data for the new fcurve
        dp, array_index, max_range, min_range, value_range, main_dir, _bone_name = get_bone_animation_data(
            sk_name, c_rig)
        # The shape key min and max slider value
        sk_max = 1
        sk_min = 0
        is_scale = False
        if 'scale' in dp:
            is_scale = True
        # Scale by Amp factor
        amp_factor = 1.0
        if compensate_amplify_values:
            amp_factor *= getattr(crig_targets.get(sk_name, None), 'amplify')
        if compensate_arkit_amplify_values:
            shape_item = context.scene.faceit_arkit_retarget_shapes.get(sk_name, None)
            if shape_item:
                amp_factor *= shape_item.amplify
        # Scale the range of motion of the values to the range of motion of the bone
        scaled_kf_data = scale_to_new_range(
            kf_data,
            min_range,
            max_range,
            sk_max,
            sk_min,
            value_range,
            main_dir,
            is_scale=is_scale,
            amplify_compensation=amp_factor
        )
        populate_motion_data_dict(dp, array_index, scaled_kf_data, is_scale=is_scale, bone_motion_data=bone_motion_data)

    target_fcurves = get_fcurves_from_slot(target_action, target_slot)
    for _bone_name, motion_data in bone_motion_data.items():
        data = motion_data['kf_data']
        # Add offset to the motion data
        data_copy = np.copy(data)
        data_copy[:, 0] += frame_start
        dp = motion_data['data_path']
        array_index = motion_data['array_index']
        fc = fc_dr_utils.get_fcurve_from_bpy_struct(target_fcurves, dp=dp, array_index=array_index, replace=False)
        fc_dr_utils.populate_keyframe_points_from_np_array(
            fc,
            data_copy,
            add=True,
            join_with_existing=mix_method == 'MIX'
        )


def bake_ctrl_rig_animation_to_shape_keys(
        context: Context,
        source_action: Action = None,
        source_slot=None,
        target_action: Action = None,
        target_slot=None,
        target_objects: list[Object] = None,
        resample_fcurves: bool = False,
        mix_method: str = 'REPLACE',
        start_frame: int = 0,):
    """
    Bake the shape key animation to the control rig.

    """
    # Get all animation frames in source action
    all_frames = set()

    source_fcurves = get_fcurves_from_slot(source_action, source_slot)
    if not resample_fcurves:
        for fc in source_fcurves:
            anim_data = fc_dr_utils.kf_data_to_numpy_array(fc)
            frames = anim_data[:, 0]
            all_frames.update(frames)
    else:
        # Resample the fcurves to get all frames
        start, end = [int(x) for x in source_action.curve_frame_range]
        all_frames.update(range(start, end + 1))
    # store the animation data per driver fcurve data_path = ((fr, value),)
    anim_data_dict = {}
    for fr in all_frames:
        frame = int(fr // 1)
        subframe = fr % 1
        context.scene.frame_set(frame=frame, subframe=subframe)
        processed_data_paths = []
        for obj in target_objects:
            if has_shape_keys(obj):
                sk_id = obj.data.shape_keys
                if adt := sk_id.animation_data:
                    for driver_fc in adt.drivers:
                        dp = driver_fc.data_path
                        if dp in processed_data_paths:
                            continue
                        processed_data_paths.append(dp)
                        anim_data_dict.setdefault(dp, []).append((fr, sk_id.path_resolve(dp)))
    # populate the target action
    target_fcurves = get_fcurves_from_slot(target_action, target_slot)
    for dp, anim_data in anim_data_dict.items():
        data = np.array(anim_data)
        data[:, 0] += start_frame
        fc = fc_dr_utils.get_fcurve_from_bpy_struct(
            target_fcurves,
            dp=dp
        )
        fc_dr_utils.populate_keyframe_points_from_np_array(
            fc,
            data,
            add=True,
            join_with_existing=mix_method == 'MIX'
        )
