import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from bpy.props import StringProperty, BoolProperty, IntProperty, FloatProperty, EnumProperty, CollectionProperty, FloatVectorProperty

try:
    import bgl
except ImportError:
    bgl = None

from ..io.xpck_settings import *

##########################################
# CONST
##########################################

LANE_NAMES = {
    'armature': "Bone Animation",
    'uv': "UV Animation",
    'material': "Material Animation",
}

LANE_SHORT_NAMES = {
    'armature': "Bone",
    'uv': "UV",
    'material': "Material",
}

LANE_COLORS = {
    'armature': (0.50, 0.47, 0.87),
    'uv': (0.36, 0.79, 0.65),
    'material': (0.83, 0.33, 0.49),
}

# Draw and keymap handles, kept to remove them when the addon is disabled
draw_handlers = []
addon_keymaps = []

# Items of the action list of New Animation, Blender needs them kept alive while the dialog is open
action_items = []

# Copied splits (name, speed, frame_start, frame_end), kept when the active armature changes
split_clipboard = []

##########################################
# Timeline Function
##########################################

def get_object_armature(obj):
    if obj.type == 'ARMATURE':
        return obj

    if obj.parent and obj.parent.type == 'ARMATURE':
        return obj.parent

    return None

def get_timeline_armature(context):
    """Armature the timeline shows: the active armature, or the armature of the active mesh."""
    obj = context.active_object
    if obj is None:
        return None

    # In pose and edit mode an object picked in the outliner is only selected, the active object stays and is deselected
    if obj.mode != 'OBJECT' and not obj.select_get():
        for selected in context.selected_objects:
            armature = get_object_armature(selected)

            if armature is not None:
                return armature

    return get_object_armature(obj)

def is_timeline(context):
    space = context.space_data
    if space is None or space.type != 'DOPESHEET_EDITOR' or space.mode != 'TIMELINE':
        return False

    return context.scene.level5_timeline_show_splits

def get_track_name(track_index):
    if track_index == 0:
        return "Main Track"

    if track_index == 1:
        return "Second Track"

    return f"Track {track_index + 1}"

def get_timeline_layout(context, armature):
    """Rectangles (x, y, width, height) of the lanes of the tracks and of their splits, in pixels of the region."""
    region = context.region
    scene = context.scene
    scale = context.preferences.system.ui_scale

    lane_height = round(18 * scale)
    lane_gap = round(3 * scale)
    track_gap = round(8 * scale)
    # Above the scrollbar of the region
    bottom = round(18 * scale)

    # Rows from the top: the three lanes of each track
    rows = []
    for track_index in range(get_track_count(armature)):
        for animation_type in ANIMATION_TYPES:
            rows.append((track_index, animation_type))

    height = len(rows) * (lane_height + lane_gap) + (get_track_count(armature) - 1) * track_gap
    y = bottom + height

    layout = {
        "scale": scale,
        "bottom": bottom,
        "top": y,
        "lanes": [],
    }

    for track_index, animation_type in rows:
        if animation_type == 'armature' and track_index > 0:
            y -= track_gap

        y -= lane_height

        lane = {
            "track": track_index,
            "type": animation_type,
            "y": y,
            "height": lane_height,
            "animation": get_track_animation(armature, track_index),
            "has_splits": False,
            "splits": [],
        }

        splits = get_track_splits(armature, track_index, animation_type)

        if splits is not None:
            lane["has_splits"] = True
            offset = get_solo_offset(scene, armature, track_index)
            active_index = get_track_split_index(armature, track_index)

            # The selection is kept on the splits of the first type, the other types show it too
            source_splits = get_track_splits(armature, track_index)

            for index, split in enumerate(splits):
                x1 = region.view2d.view_to_region(split.frame_start + offset, 0, clip=False)[0]
                x2 = region.view2d.view_to_region(split.frame_end + offset, 0, clip=False)[0]

                selected = False
                if track_index == 0 and index < len(source_splits):
                    selected = source_splits[index].select

                lane["splits"].append({
                    "index": index,
                    "split": split,
                    "x1": x1,
                    "x2": max(x2, x1 + 2),
                    "active": index == active_index,
                    "selected": selected,
                })

        layout["lanes"].append(lane)
        y -= lane_gap

    return layout

def hit_timeline(layout, x, y):
    """What is under the mouse: a split and the part of it (start, end, move), a lane, or None."""
    for lane in layout["lanes"]:
        if y < lane["y"] or y > lane["y"] + lane["height"]:
            continue

        # The last split drawn is on top
        for item in reversed(lane["splits"]):
            edge = min(6 * layout["scale"], (item["x2"] - item["x1"]) / 3)

            if item["x1"] - edge <= x <= item["x2"] + edge:
                part = 'MOVE'

                if abs(x - item["x1"]) <= edge:
                    part = 'START'
                elif abs(x - item["x2"]) <= edge:
                    part = 'END'

                return {"kind": "split", "lane": lane, "item": item, "part": part}

        return {"kind": "lane", "lane": lane}

    return None

def get_timeline_hit(context, event):
    if not is_timeline(context):
        return None, None

    armature = get_timeline_armature(context)
    if armature is None:
        return None, None

    layout = get_timeline_layout(context, armature)

    return armature, hit_timeline(layout, event.mouse_region_x, event.mouse_region_y)

def redraw_timelines(context):
    for area in context.screen.areas:
        if area.type == 'DOPESHEET_EDITOR':
            area.tag_redraw()

def prepare_main_track(armature, animation_name=""):
    """The main track gets an animation with a type to put the splits on, return an error message or None."""
    settings = armature.level5_archive

    # A custom animation gets its export animation with its first split
    if len(settings.animations) == 0:
        action = get_default_action(armature)
        if action is None:
            return "The armature has no action to make an animation from"

        if animation_name == "":
            add_default_animation(armature)
        else:
            make_animation(armature, animation_name, action)

        apply_track_actions(armature)

    animation = get_track_animation(armature, 0)
    if animation is None:
        return "Choose the animation of the main track first"

    if get_source_type(animation) is None:
        animation.armature_animation.include = True

    return None

def get_new_split(armature):
    """Name and speed Insert Split proposes: the next free name, the speed of the other splits."""
    splits = get_track_splits(armature, 0)
    index = 0
    speed = 1.0

    if splits is not None:
        used_indexes = []
        for split in splits:
            used_indexes.append(split.private_index)

        index = find_unused_index(used_indexes)

        if len(splits) > 0:
            speed = splits[0].speed

    return {
        "name": "splitted_animation_" + str(index),
        "speed": speed,
    }

def add_track_split(scene, armature, name, frame_start, frame_end, speed, animation_name=""):
    """Add a split to the main track, animation_name names the animation made when the armature has none, return an error message or None."""
    settings = armature.level5_archive

    error = prepare_main_track(armature, animation_name)
    if error is not None:
        return error

    splits = get_track_splits(armature, 0)

    used_indexes = []
    for split in splits:
        used_indexes.append(split.private_index)

    split = splits.add()
    split.private_index = find_unused_index(used_indexes)
    split.name = get_split_name(splits, name)
    split.speed = speed
    split.frame_start = max(0, frame_start)
    split.frame_end = max(split.frame_start + 1, frame_end)

    settings.timeline_split_index = len(splits) - 1

    sync_animation_splits(get_track_animation(armature, 0))
    refresh_solo(scene, armature)

    return None

def update_track_actions(scene, armature):
    if scene.level5_timeline_solo.armature_name == armature.name:
        refresh_solo(scene, armature)
    else:
        apply_track_actions(armature)

def add_second_track(scene, armature):
    """A second track plays the first animation that isn't the one of the main track."""
    settings = armature.level5_archive
    main_animation = get_track_animation(armature, 0)

    track = settings.timeline_tracks.add()

    for animation in settings.animations:
        if main_animation is None or animation.name != main_animation.name:
            track.animation_name = animation.name
            break

    update_track_actions(scene, armature)

def remove_second_track(scene, armature, track_index):
    armature.level5_archive.timeline_tracks.remove(track_index - 1)
    update_track_actions(scene, armature)

def remove_track_split(scene, armature, index):
    """Delete a split of the main track, return False when there is none at this index."""
    splits = get_track_splits(armature, 0)

    if splits is None or index < 0 or index >= len(splits):
        return False

    splits.remove(index)
    armature.level5_archive.timeline_split_index = max(0, min(index, len(splits) - 1))

    sync_animation_splits(get_track_animation(armature, 0))
    refresh_solo(scene, armature)

    return True

def get_split_name(splits, name):
    names = get_names(splits)
    new_name = name
    index = 1

    while new_name in names:
        new_name = f"{name}.{str(index).rjust(3, '0')}"
        index += 1

    return new_name

def get_copy_animation_name(armature):
    """Animation that gets the copied splits by default: the one the main track plays, or the action of the armature."""
    animation = armature.level5_archive.get_active_animation()
    if animation is not None:
        return animation.name

    action = get_default_action(armature)
    if action is not None:
        return action.name

    return ""

def select_track_split(armature, index, extend=False):
    """Select a split of the main track, extend adds it to the selection or removes it."""
    splits = get_track_splits(armature, 0)
    if splits is None or index < 0 or index >= len(splits):
        return

    if extend:
        splits[index].select = not splits[index].select
    else:
        for split in splits:
            split.select = False

        splits[index].select = True

def get_copied_splits(armature, track_index, index):
    """The selected splits of the main track when the split is one of them, the split alone otherwise."""
    splits = get_track_splits(armature, track_index)
    if splits is None or index < 0 or index >= len(splits):
        return []

    if track_index == 0 and splits[index].select:
        return [split for split in splits if split.select]

    return [splits[index]]

def copy_to_clipboard(splits):
    split_clipboard.clear()

    for split in sorted(splits, key=lambda split: split.frame_start):
        split_clipboard.append({
            "name": split.name,
            "speed": split.speed,
            "frame_start": split.frame_start,
            "frame_end": split.frame_end,
        })

def paste_track_splits(scene, armature, frame):
    """Paste the copied splits in the main track, the first one starts at the frame, return an error message or None."""
    if len(split_clipboard) == 0:
        return "No split copied"

    error = prepare_main_track(armature)
    if error is not None:
        return error

    splits = get_track_splits(armature, 0)
    first_frame = split_clipboard[0]["frame_start"]
    frame = max(0, frame)

    used_indexes = []
    for split in splits:
        used_indexes.append(split.private_index)
        split.select = False

    # The pasted splits are selected, a copy right after takes them all
    for item in split_clipboard:
        split = splits.add()
        split.private_index = find_unused_index(used_indexes)
        used_indexes.append(split.private_index)
        split.name = get_split_name(splits, item["name"])
        split.speed = item["speed"]
        split.frame_start = frame + item["frame_start"] - first_frame
        split.frame_end = frame + item["frame_end"] - first_frame
        split.select = True

    armature.level5_archive.timeline_split_index = len(splits) - 1

    sync_animation_splits(get_track_animation(armature, 0))
    refresh_solo(scene, armature)

    return None

def copy_splits_to_armature(scene, armature, target, animation_name):
    """Give the splits of the main track to an animation of another armature, the splits it had are replaced."""
    settings = target.level5_archive
    index = find_animation_index(target, animation_name)

    if index >= 0:
        animation = settings.animations[index]
    else:
        animation_index = settings.animation_index
        animation = make_animation(target, animation_name, get_default_action(target))

        # The main track of the armature keeps its animation
        if len(settings.animations) > 1:
            settings.animation_index = animation_index

    source_type = get_source_type(animation)
    if source_type is None:
        source_type = 'armature'
        animation.armature_animation.include = True

    copy_splits(get_track_splits(armature, 0), animation.get_animation(source_type).splits)
    sync_animation_splits(animation)

    if scene.level5_timeline_solo.armature_name == target.name:
        refresh_solo(scene, target)

def get_solo_text(armature):
    names = []

    for track_index in range(get_track_count(armature)):
        split = get_track_split(armature, track_index)

        if split is not None:
            names.append(split.name)

    return "Solo: " + " + ".join(names)

##########################################
# Timeline Draw Function
##########################################

def get_shader():
    # The builtin shaders lost their 2D_ prefix in Blender 4.0
    if bpy.app.version >= (4, 0, 0):
        return gpu.shader.from_builtin('UNIFORM_COLOR')

    return gpu.shader.from_builtin('2D_UNIFORM_COLOR')

def set_blend(enabled):
    # gpu.state exists since Blender 2.93
    if hasattr(gpu, "state"):
        if enabled:
            gpu.state.blend_set('ALPHA')
        else:
            gpu.state.blend_set('NONE')
    elif bgl is not None:
        if enabled:
            bgl.glEnable(bgl.GL_BLEND)
        else:
            bgl.glDisable(bgl.GL_BLEND)

def set_font_size(size):
    # The dpi argument is optional since Blender 3.4 and removed in 4.0
    if bpy.app.version >= (3, 4, 0):
        blf.size(0, size)
    else:
        blf.size(0, size, 72)

def draw_shape(shader, shape_type, vertices, color, indices=None):
    if indices is None:
        batch = batch_for_shader(shader, shape_type, {"pos": vertices})
    else:
        batch = batch_for_shader(shader, shape_type, {"pos": vertices}, indices=indices)

    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

def draw_rect(shader, rect, color):
    x = rect[0]
    y = rect[1]
    width = rect[2]
    height = rect[3]

    vertices = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
    draw_shape(shader, 'TRIS', vertices, color, ((0, 1, 2), (0, 2, 3)))

def draw_outline(shader, rect, color):
    x = rect[0]
    y = rect[1]
    width = rect[2]
    height = rect[3]

    vertices = (
        (x, y), (x + width, y),
        (x + width, y), (x + width, y + height),
        (x + width, y + height), (x, y + height),
        (x, y + height), (x, y),
    )
    draw_shape(shader, 'LINES', vertices, color)

def draw_text(x, y, text, color, clip=None):
    blf.color(0, color[0], color[1], color[2], color[3])

    if clip is not None:
        blf.enable(0, blf.CLIPPING)
        blf.clipping(0, clip[0], clip[1], clip[2], clip[3])

    blf.position(0, x, y, 0)
    blf.draw(0, text)

    if clip is not None:
        blf.disable(0, blf.CLIPPING)

def draw_lane_splits(shader, layout, lane, region_width):
    scale = layout["scale"]
    color = LANE_COLORS[lane["type"]]
    y = lane["y"]
    height = lane["height"]
    text_y = y + round(5 * scale)
    read_only = lane["track"] > 0

    for item in lane["splits"]:
        x1 = item["x1"]
        x2 = item["x2"]

        if x2 < 0 or x1 > region_width:
            continue

        rect = (x1, y, x2 - x1, height)
        text_color = (0.08, 0.08, 0.08, 1.0)

        # A second track is only played: its splits are hollow, without the grips of the main track
        if read_only:
            draw_rect(shader, rect, (color[0], color[1], color[2], 0.25))
            draw_outline(shader, rect, (color[0], color[1], color[2], 1.0))
            text_color = (0.85, 0.85, 0.85, 1.0)

            if item["active"]:
                draw_outline(shader, (x1 + 1, y + 1, x2 - x1 - 2, height - 2), (1.0, 1.0, 1.0, 1.0))
        else:
            if item["active"]:
                draw_rect(shader, rect, (color[0], color[1], color[2], 1.0))
                draw_outline(shader, rect, (1.0, 1.0, 1.0, 1.0))
            else:
                draw_rect(shader, rect, (color[0], color[1], color[2], 0.85))

                # Orange like the selected keyframes of Blender
                if item["selected"]:
                    draw_outline(shader, rect, (1.0, 0.6, 0.2, 1.0))

            # Grips of the start and the end, they are dragged to change the frames
            if x2 - x1 > 12 * scale:
                grip_width = max(2, round(2 * scale))
                grip_margin = round(4 * scale)
                draw_rect(shader, (x1 + 2, y + grip_margin, grip_width, height - 2 * grip_margin), (0.0, 0.0, 0.0, 0.35))
                draw_rect(shader, (x2 - 2 - grip_width, y + grip_margin, grip_width, height - 2 * grip_margin), (0.0, 0.0, 0.0, 0.35))

        split = item["split"]
        text = split.name
        if abs(split.speed - 1.0) > 0.0001:
            text += f"  x{split.speed:g}"

        draw_text(x1 + round(7 * scale), text_y, text, text_color, (x1 + 2, y, x2 - 2, y + height))

def get_reference_name(armature):
    animation = get_track_animation(armature, 0)
    if animation is None:
        return "None"

    return animation.name

def draw_timeline_splits():
    context = bpy.context
    if not is_timeline(context):
        return

    armature = get_timeline_armature(context)
    if armature is None:
        return

    layout = get_timeline_layout(context, armature)
    region = context.region
    scale = layout["scale"]
    shader = get_shader()

    set_blend(True)
    set_font_size(round(11 * scale))

    for lane in layout["lanes"]:
        background = (0.0, 0.0, 0.0, 0.25)
        if lane["track"] > 0:
            background = (0.25, 0.3, 0.5, 0.2)

        draw_rect(shader, (0, lane["y"], region.width, lane["height"]), background)

        if lane["has_splits"]:
            draw_lane_splits(shader, layout, lane, region.width)
        elif lane["type"] == 'armature' or lane["animation"] is not None:
            if lane["animation"] is None and lane["track"] == 0:
                message = "No animation, right click > Insert Split makes one from the action of the armature"
            elif lane["animation"] is None:
                message = f"Choose the animation of the {get_track_name(lane['track']).lower()} in the header"
            else:
                message = f"No {LANE_SHORT_NAMES[lane['type']]} animation in {lane['animation'].name}"

            draw_text(round(10 * scale), lane["y"] + round(5 * scale), message, (0.55, 0.55, 0.55, 1.0))

        # The color of the lane, the i button of the header tells them
        color = LANE_COLORS[lane["type"]]
        draw_rect(shader, (0, lane["y"], round(4 * scale), lane["height"]), (color[0], color[1], color[2], 1.0))

    if context.scene.level5_timeline_solo.armature_name == armature.name:
        draw_text(round(8 * scale), layout["top"] + round(6 * scale), get_solo_text(armature), (0.91, 0.64, 0.23, 1.0))

    set_blend(False)

def draw_timeline_header(self, context):
    if context.space_data.mode != 'TIMELINE':
        return

    layout = self.layout
    armature = get_timeline_armature(context)

    # The armature and the animation of each track are chosen in the header, the splits keep the height of the timeline
    if context.scene.level5_timeline_show_splits and armature is not None:
        layout.label(text=armature.name, icon='ARMATURE_DATA')

        layout.menu("LEVEL5_MT_timeline_animations", text=f"{get_track_name(0)}: {get_reference_name(armature)}")

        for track_index in range(1, get_track_count(armature)):
            track = armature.level5_archive.timeline_tracks[track_index - 1]

            name = track.animation_name
            if name == "":
                name = "None"

            row = layout.row(align=True)
            row.context_pointer_set("level5_timeline_track", track)
            row.menu("LEVEL5_MT_timeline_animations", text=f"{get_track_name(track_index)}: {name}")

            operator = row.operator("level5.timeline_remove_track", text="", icon='X')
            operator.track_index = track_index

        layout.operator("level5.timeline_add_track", text="", icon='ADD')
        layout.operator("level5.timeline_colors", text="", icon='INFO')

    layout.prop(context.scene, "level5_timeline_show_splits")

def update_show_splits(self, context):
    # Hiding the splits plays the whole animations again
    if not self.level5_timeline_show_splits:
        stop_solo(self)

##########################################
# Register class
##########################################

class LEVEL5_OT_timeline_click(bpy.types.Operator):
    bl_idname = "level5.timeline_click"
    bl_label = "Edit Split"
    bl_description = "Drag a split of the main track to move it, drag its start or its end to change its frames, Shift adds it to the selection"
    bl_options = {'UNDO', 'INTERNAL'}

    armature_name: StringProperty()
    index: IntProperty()
    part: StringProperty()
    extend: BoolProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        armature, hit = get_timeline_hit(context, event)
        if hit is None or hit["kind"] == 'lane':
            return {'PASS_THROUGH'}

        scene = context.scene
        track_index = hit["lane"]["track"]

        set_track_split_index(armature, track_index, hit["item"]["index"])
        redraw_timelines(context)

        # A second track is only played, its splits are selected but never moved
        if track_index > 0:
            refresh_solo(scene, armature)
            return {'FINISHED'}

        select_track_split(armature, hit["item"]["index"], self.extend)

        if self.extend:
            return {'FINISHED'}

        split = hit["item"]["split"]

        self.armature_name = armature.name
        self.index = hit["item"]["index"]
        self.part = hit["part"]
        self.mouse_x = event.mouse_x
        self.frame_start = split.frame_start
        self.frame_end = split.frame_end

        view2d = context.region.view2d
        self.frames_per_pixel = (view2d.region_to_view(100, 0)[0] - view2d.region_to_view(0, 0)[0]) / 100

        if self.part == 'MOVE':
            context.window.cursor_modal_set('HAND')
        else:
            context.window.cursor_modal_set('MOVE_X')

        context.window_manager.modal_handler_add(self)

        return {'RUNNING_MODAL'}

    def get_split(self):
        armature = bpy.data.objects.get(self.armature_name)
        if armature is None:
            return None

        splits = get_track_splits(armature, 0)
        if splits is None or self.index >= len(splits):
            return None

        return splits[self.index]

    def move_split(self, split, delta):
        frame_start = self.frame_start
        frame_end = self.frame_end

        if self.part == 'MOVE':
            frame_start = max(0, self.frame_start + delta)
            frame_end = frame_start + self.frame_end - self.frame_start
        elif self.part == 'START':
            frame_start = min(self.frame_end - 1, max(0, self.frame_start + delta))
        else:
            frame_end = max(self.frame_start + 1, self.frame_end + delta)

        # Only the frames that change, each change syncs the other types of the animation
        if split.frame_start != frame_start:
            split.frame_start = frame_start

        if split.frame_end != frame_end:
            split.frame_end = frame_end

    def modal(self, context, event):
        split = self.get_split()
        if split is None:
            context.window.cursor_modal_restore()
            return {'CANCELLED'}

        if event.type == 'MOUSEMOVE':
            delta = round((event.mouse_x - self.mouse_x) * self.frames_per_pixel)
            self.move_split(split, delta)
            redraw_timelines(context)
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            context.window.cursor_modal_restore()
            refresh_solo(context.scene, bpy.data.objects[self.armature_name])
            redraw_timelines(context)
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            split.frame_start = self.frame_start
            split.frame_end = self.frame_end
            context.window.cursor_modal_restore()
            redraw_timelines(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

class LEVEL5_OT_timeline_double_click(bpy.types.Operator):
    bl_idname = "level5.timeline_double_click"
    bl_label = "Rename Split"
    bl_description = "Select the split and change its name"
    bl_options = {'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        armature, hit = get_timeline_hit(context, event)
        if hit is None or hit["kind"] != 'split':
            return {'PASS_THROUGH'}

        track_index = hit["lane"]["track"]
        set_track_split_index(armature, track_index, hit["item"]["index"])
        redraw_timelines(context)

        # The splits of a second track can't be renamed
        if track_index == 0:
            context.window_manager.level5_timeline_split = hit["item"]["index"]
            bpy.ops.level5.timeline_open_menu('INVOKE_DEFAULT', panel_name="LEVEL5_PT_timeline_rename_split", release_type='LEFTMOUSE')

        return {'FINISHED'}

class LEVEL5_OT_timeline_context_menu(bpy.types.Operator):
    bl_idname = "level5.timeline_context_menu"
    bl_label = "Split Menu"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        armature, hit = get_timeline_hit(context, event)
        if hit is None or hit["kind"] not in {'split', 'lane'}:
            return {'PASS_THROUGH'}

        track_index = hit["lane"]["track"]
        window_manager = context.window_manager

        window_manager.level5_timeline_track = track_index
        window_manager.level5_timeline_split = -1
        window_manager.level5_timeline_frame = round(context.region.view2d.region_to_view(event.mouse_region_x, 0)[0])

        if hit["kind"] == 'split':
            index = hit["item"]["index"]
            set_track_split_index(armature, track_index, index)
            window_manager.level5_timeline_split = index

            # A right click keeps the selection it is on, like the keyframes
            if track_index == 0 and not get_track_splits(armature, 0)[index].select:
                select_track_split(armature, index)

        bpy.ops.level5.timeline_open_menu('INVOKE_DEFAULT', menu_name="LEVEL5_MT_timeline_split", release_type='RIGHTMOUSE')
        redraw_timelines(context)

        return {'FINISHED'}

class LEVEL5_OT_timeline_open_menu(bpy.types.Operator):
    bl_idname = "level5.timeline_open_menu"
    bl_label = "Open Menu"
    bl_options = {'INTERNAL'}

    menu_name: StringProperty()
    panel_name: StringProperty()
    release_type: StringProperty()

    # A menu opened while the button is pressed closes when it is released, it is opened on the release
    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == self.release_type and event.value == 'RELEASE':
            if self.panel_name != "":
                bpy.ops.wm.call_panel(name=self.panel_name, keep_open=False)
            else:
                bpy.ops.wm.call_menu(name=self.menu_name)

            return {'FINISHED'}

        if event.type == 'ESC':
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

class LEVEL5_OT_timeline_set_track_animation(bpy.types.Operator):
    bl_idname = "level5.timeline_set_track_animation"
    bl_label = "Set Track Animation"
    bl_description = "Play this animation on the track"
    bl_options = {'UNDO', 'INTERNAL'}

    track_index: IntProperty()
    animation_name: StringProperty()

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None or self.track_index >= get_track_count(armature):
            return {'CANCELLED'}

        scene = context.scene
        settings = armature.level5_archive

        if scene.level5_timeline_solo.armature_name == armature.name:
            stop_solo(scene)

        if self.track_index == 0:
            for i, animation in enumerate(settings.animations):
                if animation.name == self.animation_name:
                    settings.animation_index = i

            frame_count = get_animation_frame_count(settings.get_active_animation())
            if frame_count > 0:
                scene.frame_end = frame_count
        else:
            settings.timeline_tracks[self.track_index - 1].animation_name = self.animation_name

        set_track_split_index(armature, self.track_index, 0)

        apply_track_actions(armature)
        scene.frame_set(scene.frame_current)
        redraw_timelines(context)

        return {'FINISHED'}

def get_action_items(self, context):
    action_items.clear()

    armature = get_timeline_armature(context)
    if armature is not None:
        for action in bpy.data.actions:
            if is_armature_action(armature, action):
                action_items.append((action.name, action.name, ""))

    if len(action_items) == 0:
        action_items.append(('NONE', "No action", ""))

    return action_items

def find_animation_index(armature, animation_name):
    for i, animation in enumerate(armature.level5_archive.animations):
        if animation.name == animation_name:
            return i

    return -1

def check_animation_name(armature, name, old_name=""):
    """Error message when the name can't be used, None otherwise."""
    if name == "":
        return "The animation needs a name"

    if name != old_name and find_animation_index(armature, name) >= 0:
        return f"An animation named {name} already exists"

    return None

class LEVEL5_OT_timeline_new_animation(bpy.types.Operator):
    bl_idname = "level5.timeline_new_animation"
    bl_label = "New Animation"
    bl_description = "Make an animation of the export from an action of the armature, the main track plays it"
    bl_options = {'UNDO', 'INTERNAL'}

    name: StringProperty(name="Name", description="Name of the animation, the mtn2, imm2 and mtm2 files share it")
    action: EnumProperty(name="Action", description="Action of the armature the animation plays", items=get_action_items)

    def invoke(self, context, event):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        # The action the armature plays is chosen first
        action = get_default_action(armature)
        if action is not None:
            self.action = action.name
            self.name = get_unique_animation_name(armature, action.name)
        else:
            self.name = get_unique_animation_name(armature, "animation")

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        row = self.layout.row()
        row.activate_init = True
        row.prop(self, "name")

        self.layout.prop(self, "action")

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        action = bpy.data.actions.get(self.action)
        if action is None:
            self.report({'ERROR'}, "The armature has no action to make an animation from")
            return {'CANCELLED'}

        name = self.name.strip()
        error = check_animation_name(armature, name)
        if error is not None:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        scene = context.scene

        if scene.level5_timeline_solo.armature_name == armature.name:
            stop_solo(scene)

        make_animation(armature, name, action)
        armature.level5_archive.timeline_split_index = 0

        apply_track_actions(armature)

        frame_count = get_animation_frame_count(armature.level5_archive.get_active_animation())
        if frame_count > 0:
            scene.frame_end = frame_count

        redraw_timelines(context)

        return {'FINISHED'}

class LEVEL5_OT_timeline_rename_animation(bpy.types.Operator):
    bl_idname = "level5.timeline_rename_animation"
    bl_label = "Rename Animation"
    bl_description = "Change the name of the animation, the mtn2, imm2 and mtm2 files share it"
    bl_options = {'UNDO', 'INTERNAL'}

    animation_name: StringProperty()
    name: StringProperty(name="Name")

    def invoke(self, context, event):
        self.name = self.animation_name
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        row = self.layout.row()
        row.activate_init = True
        row.prop(self, "name")

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        index = find_animation_index(armature, self.animation_name)
        if index < 0:
            return {'CANCELLED'}

        name = self.name.strip()
        error = check_animation_name(armature, name, self.animation_name)
        if error is not None:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        settings = armature.level5_archive
        settings.animations[index].name = name

        # The second tracks find their animation by its name
        for track in settings.timeline_tracks:
            if track.animation_name == self.animation_name:
                track.animation_name = name

        redraw_timelines(context)

        return {'FINISHED'}

class LEVEL5_OT_timeline_remove_animation(bpy.types.Operator):
    bl_idname = "level5.timeline_remove_animation"
    bl_label = "Remove Animation"
    bl_description = "Remove the animation from the export of the armature, the armature keeps its action"
    bl_options = {'UNDO', 'INTERNAL'}

    animation_name: StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        index = find_animation_index(armature, self.animation_name)
        if index < 0:
            return {'CANCELLED'}

        scene = context.scene
        settings = armature.level5_archive
        main_removed = index == settings.animation_index

        if scene.level5_timeline_solo.armature_name == armature.name:
            stop_solo(scene)

        # Only the animation of the export goes, the armature keeps the action
        settings.animations.remove(index)

        if index < settings.animation_index or settings.animation_index >= len(settings.animations):
            settings.animation_index = max(0, settings.animation_index - 1)

        if main_removed:
            settings.timeline_split_index = 0

        for track in settings.timeline_tracks:
            if track.animation_name == self.animation_name:
                track.animation_name = ""

        apply_track_actions(armature)
        redraw_timelines(context)

        self.report({'INFO'}, f"{self.animation_name} removed from the animations of the export, its action is kept")

        return {'FINISHED'}

class LEVEL5_OT_timeline_remove_track(bpy.types.Operator):
    bl_idname = "level5.timeline_remove_track"
    bl_label = "Remove Track"
    bl_description = "Remove this second track, its animation is kept"
    bl_options = {'UNDO', 'INTERNAL'}

    track_index: IntProperty()

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None or self.track_index < 1 or self.track_index >= get_track_count(armature):
            return {'CANCELLED'}

        remove_second_track(context.scene, armature, self.track_index)
        redraw_timelines(context)

        return {'FINISHED'}

class LEVEL5_OT_timeline_add_track(bpy.types.Operator):
    bl_idname = "level5.timeline_add_track"
    bl_label = "Add Second Track"
    bl_description = "Add a second track, it plays another animation of the armature under the main track"
    bl_options = {'UNDO', 'INTERNAL'}

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        add_second_track(context.scene, armature)
        redraw_timelines(context)

        return {'FINISHED'}

class LEVEL5_OT_timeline_colors(bpy.types.Operator):
    bl_idname = "level5.timeline_colors"
    bl_label = "Split Colors"
    bl_description = "What the colors of the splits mean"
    bl_options = {'INTERNAL'}

    # Only shown in the popup, the swatches are the colors of the timeline
    armature_color: FloatVectorProperty(subtype='COLOR', default=LANE_COLORS['armature'], min=0.0, max=1.0)
    uv_color: FloatVectorProperty(subtype='COLOR', default=LANE_COLORS['uv'], min=0.0, max=1.0)
    material_color: FloatVectorProperty(subtype='COLOR', default=LANE_COLORS['material'], min=0.0, max=1.0)
    active_color: FloatVectorProperty(subtype='COLOR', default=(1.0, 1.0, 1.0), min=0.0, max=1.0)
    selected_color: FloatVectorProperty(subtype='COLOR', default=(1.0, 0.6, 0.2), min=0.0, max=1.0)
    second_color: FloatVectorProperty(subtype='COLOR', default=(0.25, 0.3, 0.5), min=0.0, max=1.0)

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=420)

    def draw_color(self, property_name, text):
        row = self.layout.split(factor=0.12)
        row.prop(self, property_name, text="")
        row.label(text=text)

    def draw(self, context):
        self.layout.label(text="Each track has three lanes, from top to bottom:")

        for animation_type in ANIMATION_TYPES:
            self.draw_color(animation_type + "_color", LANE_NAMES[animation_type])

        self.layout.separator()
        self.draw_color("active_color", "Outline of the active split")
        self.draw_color("selected_color", "Outline of the selected splits (Shift + click)")
        self.draw_color("second_color", "Lanes of a second track, their hollow splits are read only")

    def execute(self, context):
        return {'FINISHED'}

class LEVEL5_OT_timeline_insert_split(bpy.types.Operator):
    bl_idname = "level5.timeline_insert_split"
    bl_label = "Insert Split"
    bl_description = "Insert a split in the main track where the menu was opened, it is in the export menu too"
    bl_options = {'UNDO', 'INTERNAL'}

    frame: IntProperty()
    animation_name: StringProperty(name="Animation", description="Name of the Level-5 animation made from the action of the armature, the mtn2, imm2 and mtm2 files share it")
    name: StringProperty(name="Name", description="Name of the split")
    frame_start: IntProperty(name="Start Frame", min=0)
    frame_end: IntProperty(name="End Frame", min=0)
    speed: FloatProperty(name="Speed", default=1.0)
    new_animation: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        # The first split of an armature without Level-5 animation makes one, its name is asked too
        self.new_animation = len(armature.level5_archive.animations) == 0

        if self.new_animation:
            action = get_default_action(armature)
            if action is None:
                self.report({'ERROR'}, "The armature has no action to make an animation from")
                return {'CANCELLED'}

            self.animation_name = get_unique_animation_name(armature, action.name)
        elif get_track_animation(armature, 0) is None:
            self.report({'ERROR'}, "Choose the animation of the main track first")
            return {'CANCELLED'}

        split = get_new_split(armature)
        self.name = split["name"]
        self.speed = split["speed"]
        self.frame_start = max(0, self.frame)
        self.frame_end = self.frame_start + 30

        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        layout = self.layout

        if self.new_animation:
            layout.label(text="No Level-5 animation yet, one is made from the action", icon='INFO')
            layout.prop(self, "animation_name")
            layout.separator()

        row = layout.row()
        row.activate_init = True
        row.prop(self, "name")

        layout.prop(self, "frame_start")
        layout.prop(self, "frame_end")
        layout.prop(self, "speed")

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        name = self.name.strip()
        if name == "":
            self.report({'ERROR'}, "The split needs a name")
            return {'CANCELLED'}

        if self.frame_end <= self.frame_start:
            self.report({'ERROR'}, "The end frame must be after the start frame")
            return {'CANCELLED'}

        animation_name = ""

        if self.new_animation:
            animation_name = self.animation_name.strip()

            error = check_animation_name(armature, animation_name)
            if error is not None:
                self.report({'ERROR'}, error)
                return {'CANCELLED'}

        error = add_track_split(context.scene, armature, name, self.frame_start, self.frame_end, self.speed, animation_name)
        if error is not None:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        redraw_timelines(context)

        return {'FINISHED'}

class LEVEL5_OT_timeline_remove_split(bpy.types.Operator):
    bl_idname = "level5.timeline_remove_split"
    bl_label = "Delete Split"
    bl_description = "Delete the split of the main track"
    bl_options = {'UNDO', 'INTERNAL'}

    index: IntProperty()

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        if not remove_track_split(context.scene, armature, self.index):
            return {'CANCELLED'}

        redraw_timelines(context)

        return {'FINISHED'}

class LEVEL5_OT_timeline_delete_key(bpy.types.Operator):
    bl_idname = "level5.timeline_delete_key"
    bl_label = "Delete Split"
    bl_description = "Delete the split under the mouse, or the selected split of the main track"
    bl_options = {'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        armature, hit = get_timeline_hit(context, event)

        # Out of the main track the key deletes the keyframes as usual
        if hit is None or hit["kind"] not in {'split', 'lane'} or hit["lane"]["track"] != 0:
            return {'PASS_THROUGH'}

        index = armature.level5_archive.timeline_split_index
        if hit["kind"] == 'split':
            index = hit["item"]["index"]

        if not remove_track_split(context.scene, armature, index):
            return {'CANCELLED'}

        redraw_timelines(context)

        return {'FINISHED'}

class LEVEL5_OT_timeline_duplicate_split(bpy.types.Operator):
    bl_idname = "level5.timeline_duplicate_split"
    bl_label = "Duplicate Split"
    bl_description = "Copy the split of the main track right after it"
    bl_options = {'UNDO', 'INTERNAL'}

    index: IntProperty()

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        splits = get_track_splits(armature, 0)

        if splits is None or self.index >= len(splits):
            return {'CANCELLED'}

        source = splits[self.index]
        length = source.frame_end - source.frame_start

        used_indexes = []
        for split in splits:
            used_indexes.append(split.private_index)

        split = splits.add()
        split.private_index = find_unused_index(used_indexes)
        split.name = get_split_name(splits, source.name)
        split.speed = source.speed
        split.frame_start = source.frame_end + 1
        split.frame_end = source.frame_end + 1 + length

        armature.level5_archive.timeline_split_index = len(splits) - 1

        sync_animation_splits(get_track_animation(armature, 0))
        refresh_solo(context.scene, armature)
        redraw_timelines(context)

        return {'FINISHED'}

class LEVEL5_OT_timeline_copy_split(bpy.types.Operator):
    bl_idname = "level5.timeline_copy_split"
    bl_label = "Copy Splits"
    bl_description = "Copy the split, or the selected splits when it is one of them, Paste puts them on the main track of any armature"
    bl_options = {'INTERNAL'}

    track_index: IntProperty()
    index: IntProperty()

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None or self.track_index >= get_track_count(armature):
            return {'CANCELLED'}

        splits = get_copied_splits(armature, self.track_index, self.index)
        if len(splits) == 0:
            return {'CANCELLED'}

        copy_to_clipboard(splits)

        self.report({'INFO'}, f"{len(splits)} splits copied")

        return {'FINISHED'}

class LEVEL5_OT_timeline_paste_splits(bpy.types.Operator):
    bl_idname = "level5.timeline_paste_splits"
    bl_label = "Paste Splits"
    bl_description = "Paste the copied splits in the main track, the first one starts where the menu was opened"
    bl_options = {'UNDO', 'INTERNAL'}

    frame: IntProperty()

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        error = paste_track_splits(context.scene, armature, self.frame)
        if error is not None:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        redraw_timelines(context)

        return {'FINISHED'}

class Level5TimelineCopyTarget(bpy.types.PropertyGroup):
    name: StringProperty()
    enabled: BoolProperty(name="Copy", default=True, description="Copy the splits to this armature")
    animation_name: StringProperty(name="Animation", description="Animation that gets the splits, a new animation is made from the action of the armature when it has none with this name")

class LEVEL5_OT_timeline_copy_splits(bpy.types.Operator):
    bl_idname = "level5.timeline_copy_splits"
    bl_label = "Copy Splits to Other Armatures"
    bl_description = "Copy all the splits of the main track to an animation of the other armatures that have an animation"
    bl_options = {'UNDO', 'INTERNAL'}

    targets: CollectionProperty(type=Level5TimelineCopyTarget)

    def invoke(self, context, event):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        splits = get_track_splits(armature, 0)
        if splits is None or len(splits) == 0:
            self.report({'ERROR'}, "The main track has no split to copy")
            return {'CANCELLED'}

        self.targets.clear()

        for obj in bpy.data.objects:
            if obj.type != 'ARMATURE' or obj == armature:
                continue

            animation_name = get_copy_animation_name(obj)

            if animation_name != "":
                target = self.targets.add()
                target.name = obj.name
                target.animation_name = animation_name

        if len(self.targets) == 0:
            self.report({'ERROR'}, "No other armature has an animation")
            return {'CANCELLED'}

        return context.window_manager.invoke_props_dialog(self, width=450)

    def draw(self, context):
        layout = self.layout

        layout.label(text="The splits an animation already has are replaced", icon='ERROR')
        layout.separator()

        row = layout.row()
        row.label(text="Armature")
        row.label(text="Level-5 Animation")

        for target in self.targets:
            row = layout.row()
            row.prop(target, "enabled", text=target.name)

            column = row.column()
            column.enabled = target.enabled
            column.prop(target, "animation_name", text="")

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        splits = get_track_splits(armature, 0)
        if splits is None or len(splits) == 0:
            self.report({'ERROR'}, "The main track has no split to copy")
            return {'CANCELLED'}

        count = 0

        for target in self.targets:
            obj = bpy.data.objects.get(target.name)
            animation_name = target.animation_name.strip()

            if not target.enabled or obj is None or animation_name == "":
                continue

            copy_splits_to_armature(context.scene, armature, obj, animation_name)
            count += 1

        redraw_timelines(context)

        self.report({'INFO'}, f"{len(splits)} splits copied to {count} armatures")

        return {'FINISHED'}

class LEVEL5_OT_timeline_solo(bpy.types.Operator):
    bl_idname = "level5.timeline_solo"
    bl_label = "Solo"
    bl_description = "Play only the active split of each track, they start together like in the game"
    bl_options = {'UNDO', 'INTERNAL'}

    track_index: IntProperty()
    index: IntProperty(default=-1)

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        if self.index >= 0 and self.track_index < get_track_count(armature):
            set_track_split_index(armature, self.track_index, self.index)

        if not start_solo(context.scene, armature):
            self.report({'ERROR'}, "No split to play")
            return {'CANCELLED'}

        redraw_timelines(context)

        return {'FINISHED'}

class LEVEL5_OT_timeline_stop_solo(bpy.types.Operator):
    bl_idname = "level5.timeline_stop_solo"
    bl_label = "Stop Solo"
    bl_description = "Play the whole animations again"
    bl_options = {'UNDO', 'INTERNAL'}

    def execute(self, context):
        stop_solo(context.scene)
        redraw_timelines(context)

        return {'FINISHED'}

class LEVEL5_MT_timeline_animations(bpy.types.Menu):
    bl_idname = "LEVEL5_MT_timeline_animations"
    bl_label = "Animation"

    def draw(self, context):
        layout = self.layout

        armature = get_timeline_armature(context)
        if armature is None:
            return

        # The header gives its track to the menu of a second track, the main track has none
        track_index = 0
        track = getattr(context, "level5_timeline_track", None)

        if track is not None:
            for i, item in enumerate(armature.level5_archive.timeline_tracks):
                if item.as_pointer() == track.as_pointer():
                    track_index = i + 1

            if track_index == 0:
                return

        current = get_track_animation(armature, track_index)

        # A menu runs its operators without their invoke, the rename, remove and new dialogs need it
        layout.operator_context = 'INVOKE_DEFAULT'

        for animation in armature.level5_archive.animations:
            types = []
            for animation_type in ANIMATION_TYPES:
                if animation.get_animation(animation_type).include:
                    types.append(LANE_SHORT_NAMES[animation_type])

            icon = 'RADIOBUT_OFF'
            if current is not None and animation.name == current.name:
                icon = 'RADIOBUT_ON'

            row = layout.row(align=True)

            operator = row.operator("level5.timeline_set_track_animation", text=f"{animation.name}  ({', '.join(types)})", icon=icon)
            operator.track_index = track_index
            operator.animation_name = animation.name

            operator = row.operator("level5.timeline_rename_animation", text="", icon='GREASEPENCIL')
            operator.animation_name = animation.name

            operator = row.operator("level5.timeline_remove_animation", text="", icon='X')
            operator.animation_name = animation.name

        # Only the main track makes animations, the second tracks play the existing ones
        if track_index == 0:
            layout.separator()
            layout.operator("level5.timeline_new_animation", text="New Animation...", icon='ADD')

class LEVEL5_MT_timeline_split(bpy.types.Menu):
    bl_idname = "LEVEL5_MT_timeline_split"
    bl_label = "Split"

    def draw(self, context):
        layout = self.layout

        armature = get_timeline_armature(context)
        if armature is None:
            return

        window_manager = context.window_manager
        track_index = window_manager.level5_timeline_track
        index = window_manager.level5_timeline_split

        if track_index >= get_track_count(armature):
            return

        layout.label(text=f"{armature.name}  |  {get_reference_name(armature)}", icon='ARMATURE_DATA')
        layout.separator()

        splits = get_track_splits(armature, track_index)

        if splits is not None and 0 <= index < len(splits):
            # The splits of a second track can't be changed, only played
            if track_index == 0:
                split = splits[index]

                layout.prop(split, "name", text="")
                layout.prop(split, "frame_start")
                layout.prop(split, "frame_end")
                layout.prop(split, "speed")

                layout.separator()

            operator = layout.operator("level5.timeline_solo", text="Solo", icon='PLAY')
            operator.track_index = track_index
            operator.index = index

            copy_count = len(get_copied_splits(armature, track_index, index))
            copy_text = "Copy"
            if copy_count > 1:
                copy_text = f"Copy {copy_count} Splits"

            operator = layout.operator("level5.timeline_copy_split", text=copy_text, icon='COPYDOWN')
            operator.track_index = track_index
            operator.index = index

            if track_index == 0:
                operator = layout.operator("level5.timeline_duplicate_split", text="Duplicate", icon='DUPLICATE')
                operator.index = index

                operator = layout.operator("level5.timeline_remove_split", text="Delete", icon='TRASH')
                operator.index = index

            layout.separator()

        if track_index == 0:
            # The dialogs of Insert Split and of the copy need the invoke
            layout.operator_context = 'INVOKE_DEFAULT'

            operator = layout.operator("level5.timeline_insert_split", text="Insert Split...", icon='ADD')
            operator.frame = window_manager.level5_timeline_frame

            if len(split_clipboard) > 0:
                paste_text = "Paste Split"
                if len(split_clipboard) > 1:
                    paste_text = f"Paste {len(split_clipboard)} Splits"

                operator = layout.operator("level5.timeline_paste_splits", text=paste_text, icon='PASTEDOWN')
                operator.frame = window_manager.level5_timeline_frame

            if splits is not None and len(splits) > 0:
                layout.operator("level5.timeline_copy_splits", text="Copy Splits to Other Armatures...", icon='COPYDOWN')
        else:
            layout.label(text="Read only, change the animation of the main track to edit it", icon='LOCKED')

            operator = layout.operator("level5.timeline_remove_track", text="Remove Track", icon='X')
            operator.track_index = track_index

        if context.scene.level5_timeline_solo.armature_name != "":
            layout.separator()
            layout.operator("level5.timeline_stop_solo", text="Stop Solo", icon='X')

# Same as the rename of the active item (F2): the name field is edited as soon as it opens
class LEVEL5_PT_timeline_rename_split(bpy.types.Panel):
    bl_space_type = 'DOPESHEET_EDITOR'
    bl_region_type = 'HEADER'
    bl_label = "Rename Split"
    bl_ui_units_x = 12

    def draw(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return

        splits = get_track_splits(armature, 0)
        index = context.window_manager.level5_timeline_split

        if splits is None or index < 0 or index >= len(splits):
            return

        self.layout.label(text="Split Name")

        row = self.layout.row()
        row.activate_init = True
        row.prop(splits[index], "name", text="")

classes = (
    LEVEL5_OT_timeline_click,
    LEVEL5_OT_timeline_double_click,
    LEVEL5_OT_timeline_context_menu,
    LEVEL5_OT_timeline_open_menu,
    LEVEL5_OT_timeline_set_track_animation,
    LEVEL5_OT_timeline_new_animation,
    LEVEL5_OT_timeline_rename_animation,
    LEVEL5_OT_timeline_remove_animation,
    LEVEL5_OT_timeline_remove_track,
    LEVEL5_OT_timeline_add_track,
    LEVEL5_OT_timeline_colors,
    LEVEL5_OT_timeline_insert_split,
    LEVEL5_OT_timeline_remove_split,
    LEVEL5_OT_timeline_delete_key,
    LEVEL5_OT_timeline_duplicate_split,
    LEVEL5_OT_timeline_copy_split,
    LEVEL5_OT_timeline_paste_splits,
    Level5TimelineCopyTarget,
    LEVEL5_OT_timeline_copy_splits,
    LEVEL5_OT_timeline_solo,
    LEVEL5_OT_timeline_stop_solo,
    LEVEL5_MT_timeline_animations,
    LEVEL5_MT_timeline_split,
    LEVEL5_PT_timeline_rename_split,
)

def register_timeline_splits():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.WindowManager.level5_timeline_track = IntProperty()
    bpy.types.WindowManager.level5_timeline_split = IntProperty()
    bpy.types.WindowManager.level5_timeline_frame = IntProperty()
    bpy.types.Scene.level5_timeline_show_splits = BoolProperty(
        name="Show Splits",
        default=True,
        description="Show the splits of the active armature in the timeline, hiding them stops the solo",
        update=update_show_splits
    )

    draw_handlers.append(bpy.types.SpaceDopeSheetEditor.draw_handler_add(draw_timeline_splits, (), 'WINDOW', 'POST_PIXEL'))
    bpy.types.DOPESHEET_HT_header.append(draw_timeline_header)

    # No keyconfig in background mode
    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig is not None:
        keymap = keyconfig.keymaps.new(name="Dopesheet", space_type='DOPESHEET_EDITOR')

        for idname, event_type, value in [("level5.timeline_click", 'LEFTMOUSE', 'PRESS'), ("level5.timeline_double_click", 'LEFTMOUSE', 'DOUBLE_CLICK'), ("level5.timeline_context_menu", 'RIGHTMOUSE', 'PRESS'), ("level5.timeline_delete_key", 'DEL', 'PRESS')]:
            addon_keymaps.append((keymap, keymap.keymap_items.new(idname, event_type, value)))

        keymap_item = keymap.keymap_items.new("level5.timeline_click", 'LEFTMOUSE', 'PRESS', shift=True)
        keymap_item.properties.extend = True
        addon_keymaps.append((keymap, keymap_item))

def unregister_timeline_splits():
    for keymap, keymap_item in addon_keymaps:
        keymap.keymap_items.remove(keymap_item)

    addon_keymaps.clear()

    bpy.types.DOPESHEET_HT_header.remove(draw_timeline_header)

    for handler in draw_handlers:
        bpy.types.SpaceDopeSheetEditor.draw_handler_remove(handler, 'WINDOW')

    draw_handlers.clear()

    del bpy.types.Scene.level5_timeline_show_splits
    del bpy.types.WindowManager.level5_timeline_frame
    del bpy.types.WindowManager.level5_timeline_split
    del bpy.types.WindowManager.level5_timeline_track

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
