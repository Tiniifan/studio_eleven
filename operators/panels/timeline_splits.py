import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from bpy.props import StringProperty, BoolProperty, IntProperty

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

##########################################
# Timeline Function
##########################################

def get_timeline_armature(context):
    """Armature the timeline shows: the active armature, or the armature of the active mesh."""
    obj = context.active_object
    if obj is None:
        return None

    if obj.type == 'ARMATURE':
        return obj

    if obj.parent and obj.parent.type == 'ARMATURE':
        return obj.parent

    return None

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
    """Rectangles (x, y, width, height) of the tracks, their lanes, their buttons and their splits, in pixels of the region."""
    region = context.region
    scene = context.scene
    scale = context.preferences.system.ui_scale

    lane_height = round(18 * scale)
    lane_gap = round(3 * scale)
    track_gap = round(8 * scale)
    # Above the scrollbar of the region
    bottom = round(18 * scale)
    label_width = round(250 * scale)

    text_width = round(104 * scale)
    button_width = lane_height
    combo_x = round(8 * scale) + text_width
    combo_width = label_width - combo_x - button_width - round(7 * scale)

    # Rows from the top: the three lanes of each track, then the button that adds a second track
    rows = []
    for track_index in range(get_track_count(armature)):
        for animation_type in ANIMATION_TYPES:
            rows.append((track_index, animation_type))

    height = lane_height + len(rows) * (lane_height + lane_gap) + (get_track_count(armature) - 1) * track_gap
    y = bottom + height

    layout = {
        "scale": scale,
        "label_width": label_width,
        "bottom": bottom,
        "top": y,
        "lanes": [],
        "add_track": None,
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
            "combo": None,
            "remove": None,
            "has_splits": False,
            "splits": [],
        }

        # The first lane of a track has the combo box of its animation
        if animation_type == 'armature':
            lane["combo"] = (combo_x, y, combo_width, lane_height)

            if track_index > 0:
                lane["remove"] = (combo_x + combo_width + round(3 * scale), y, button_width, lane_height)

        splits = get_track_splits(armature, track_index, animation_type)

        if splits is not None:
            lane["has_splits"] = True
            offset = get_solo_offset(scene, armature, track_index)
            active_index = get_track_split_index(armature, track_index)

            for index, split in enumerate(splits):
                x1 = region.view2d.view_to_region(split.frame_start + offset, 0, clip=False)[0]
                x2 = region.view2d.view_to_region(split.frame_end + offset, 0, clip=False)[0]

                lane["splits"].append({
                    "index": index,
                    "split": split,
                    "x1": x1,
                    "x2": max(x2, x1 + 2),
                    "active": index == active_index,
                })

        layout["lanes"].append(lane)
        y -= lane_gap

    layout["add_track"] = (round(8 * scale), bottom, label_width - round(15 * scale), lane_height)

    return layout

def is_inside(rect, x, y):
    if rect is None:
        return False

    return rect[0] <= x <= rect[0] + rect[2] and rect[1] <= y <= rect[1] + rect[3]

def hit_timeline(layout, x, y):
    """What is under the mouse: a button, a split and the part of it (start, end, move), a lane, or None."""
    if is_inside(layout["add_track"], x, y):
        return {"kind": "add_track"}

    for lane in layout["lanes"]:
        if y < lane["y"] or y > lane["y"] + lane["height"]:
            continue

        if x < layout["label_width"]:
            for kind in ["combo", "remove"]:
                if is_inside(lane[kind], x, y):
                    return {"kind": kind, "lane": lane}

            return {"kind": "label", "lane": lane}

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

def add_track_split(scene, armature, frame):
    """Add a split to the main track at the frame, return an error message or None."""
    settings = armature.level5_archive

    # A custom animation gets its export animation with its first split
    if len(settings.animations) == 0:
        if get_default_action(armature) is None:
            return "The armature has no action to make an animation from"

        add_default_animation(armature)
        apply_track_actions(armature)

    animation = get_track_animation(armature, 0)
    if animation is None:
        return "Choose the animation of the main track first"

    source_type = get_source_type(animation)
    if source_type is None:
        source_type = 'armature'
        animation.armature_animation.include = True

    splits = animation.get_animation(source_type).splits

    speed = 1.0
    if len(splits) > 0:
        speed = splits[0].speed

    used_indexes = []
    for split in splits:
        used_indexes.append(split.private_index)

    split = splits.add()
    split.private_index = find_unused_index(used_indexes)
    split.name = "splitted_animation_" + str(split.private_index)
    split.speed = speed
    split.frame_start = max(0, frame)
    split.frame_end = split.frame_start + 30

    settings.timeline_split_index = len(splits) - 1

    sync_animation_splits(animation)
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

        if x2 < layout["label_width"] or x1 > region_width:
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

def draw_lane_label(shader, layout, lane):
    scale = layout["scale"]
    color = LANE_COLORS[lane["type"]]
    y = lane["y"]
    height = lane["height"]
    text_y = y + round(5 * scale)
    read_only = lane["track"] > 0

    draw_rect(shader, (0, y, round(3 * scale), height), (color[0], color[1], color[2], 1.0))

    if read_only:
        draw_text(round(8 * scale), text_y, LANE_SHORT_NAMES[lane["type"]] + " (read only)", (0.6, 0.65, 0.8, 1.0))
    else:
        draw_text(round(8 * scale), text_y, LANE_NAMES[lane["type"]], (0.85, 0.85, 0.85, 1.0))

    # Combo box of the animation, the arrow tells that it opens a list
    combo = lane["combo"]
    if combo is not None:
        draw_rect(shader, combo, (0.09, 0.09, 0.09, 1.0))
        draw_outline(shader, combo, (0.38, 0.38, 0.38, 1.0))

        name = "None"
        if lane["animation"] is not None:
            name = lane["animation"].name

        arrow_size = round(4 * scale)
        arrow_x = combo[0] + combo[2] - round(10 * scale)
        arrow_y = y + height / 2
        draw_text(combo[0] + round(5 * scale), text_y, name, (0.93, 0.93, 0.93, 1.0), (combo[0], y, arrow_x - arrow_size - 2, y + height))
        draw_shape(shader, 'TRIS', ((arrow_x - arrow_size, arrow_y + arrow_size / 2), (arrow_x + arrow_size, arrow_y + arrow_size / 2), (arrow_x, arrow_y - arrow_size / 2)), (0.75, 0.75, 0.75, 1.0))

    # Cross that removes a second track
    remove = lane["remove"]
    if remove is not None:
        cross_size = round(4 * scale)
        center_x = remove[0] + remove[2] / 2
        center_y = y + height / 2

        draw_rect(shader, remove, (0.24, 0.24, 0.24, 1.0))
        draw_shape(shader, 'LINES', (
            (center_x - cross_size, center_y - cross_size), (center_x + cross_size, center_y + cross_size),
            (center_x - cross_size, center_y + cross_size), (center_x + cross_size, center_y - cross_size),
        ), (0.9, 0.9, 0.9, 1.0))

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
                message = "Choose the animation this track plays"
            else:
                message = f"No {LANE_SHORT_NAMES[lane['type']]} animation in {lane['animation'].name}"

            draw_text(layout["label_width"] + round(8 * scale), lane["y"] + round(5 * scale), message, (0.55, 0.55, 0.55, 1.0))

    # The labels are drawn over the splits that go under them
    margin = round(3 * scale)
    draw_rect(shader, (0, layout["bottom"] - margin, layout["label_width"], layout["top"] - layout["bottom"] + 2 * margin), (0.14, 0.14, 0.14, 1.0))

    for lane in layout["lanes"]:
        draw_lane_label(shader, layout, lane)

    add_track = layout["add_track"]
    draw_rect(shader, add_track, (0.24, 0.24, 0.24, 1.0))
    draw_outline(shader, add_track, (0.38, 0.38, 0.38, 1.0))
    draw_text(add_track[0] + round(6 * scale), add_track[1] + round(5 * scale), "+  Add Second Track", (0.85, 0.85, 0.85, 1.0))

    if context.scene.level5_timeline_solo.armature_name == armature.name:
        draw_text(round(8 * scale), layout["top"] + round(6 * scale), get_solo_text(armature), (0.91, 0.64, 0.23, 1.0))

    set_blend(False)

def draw_timeline_header(self, context):
    if context.space_data.mode == 'TIMELINE':
        self.layout.prop(context.scene, "level5_timeline_show_splits")

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
    bl_description = "Drag a split of the main track to move it, drag its start or its end to change its frames"
    bl_options = {'UNDO', 'INTERNAL'}

    armature_name: StringProperty()
    index: IntProperty()
    part: StringProperty()

    def invoke(self, context, event):
        armature, hit = get_timeline_hit(context, event)
        if hit is None or hit["kind"] == 'lane':
            return {'PASS_THROUGH'}

        scene = context.scene
        window_manager = context.window_manager

        if hit["kind"] == 'label':
            return {'CANCELLED'}

        if hit["kind"] == 'add_track':
            add_second_track(scene, armature)
            redraw_timelines(context)
            return {'FINISHED'}

        track_index = hit["lane"]["track"]

        if hit["kind"] == 'combo':
            window_manager.level5_timeline_track = track_index
            bpy.ops.level5.timeline_open_menu('INVOKE_DEFAULT', menu_name="LEVEL5_MT_timeline_animations", release_type='LEFTMOUSE')
            return {'CANCELLED'}

        if hit["kind"] == 'remove':
            remove_second_track(scene, armature, track_index)
            redraw_timelines(context)
            return {'FINISHED'}

        set_track_split_index(armature, track_index, hit["item"]["index"])
        redraw_timelines(context)

        # A second track is only played, its splits are selected but never moved
        if track_index > 0:
            refresh_solo(scene, armature)
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
            set_track_split_index(armature, track_index, hit["item"]["index"])
            window_manager.level5_timeline_split = hit["item"]["index"]

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

class LEVEL5_OT_timeline_new_animation(bpy.types.Operator):
    bl_idname = "level5.timeline_new_animation"
    bl_label = "New Animation"
    bl_description = "Make an animation of the export from the action the armature plays, the main track plays it"
    bl_options = {'UNDO', 'INTERNAL'}

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        if get_default_action(armature) is None:
            self.report({'ERROR'}, "The armature has no action to make an animation from")
            return {'CANCELLED'}

        scene = context.scene

        if scene.level5_timeline_solo.armature_name == armature.name:
            stop_solo(scene)

        add_default_animation(armature)
        armature.level5_archive.timeline_split_index = 0

        apply_track_actions(armature)
        redraw_timelines(context)

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

class LEVEL5_OT_timeline_insert_split(bpy.types.Operator):
    bl_idname = "level5.timeline_insert_split"
    bl_label = "Insert Split"
    bl_description = "Insert a split in the main track where the menu was opened, it is in the export menu too"
    bl_options = {'UNDO', 'INTERNAL'}

    frame: IntProperty()

    def execute(self, context):
        armature = get_timeline_armature(context)
        if armature is None:
            return {'CANCELLED'}

        error = add_track_split(context.scene, armature, self.frame)
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

        track_index = context.window_manager.level5_timeline_track
        if track_index >= get_track_count(armature):
            return

        current = get_track_animation(armature, track_index)

        for animation in armature.level5_archive.animations:
            types = []
            for animation_type in ANIMATION_TYPES:
                if animation.get_animation(animation_type).include:
                    types.append(LANE_SHORT_NAMES[animation_type])

            icon = 'RADIOBUT_OFF'
            if current is not None and animation.name == current.name:
                icon = 'RADIOBUT_ON'

            operator = layout.operator("level5.timeline_set_track_animation", text=f"{animation.name}  ({', '.join(types)})", icon=icon)
            operator.track_index = track_index
            operator.animation_name = animation.name

        # Only the main track makes animations, the second tracks play the existing ones
        if track_index == 0:
            layout.separator()
            layout.operator("level5.timeline_new_animation", text="New Animation (current action)", icon='ADD')

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

            if track_index == 0:
                operator = layout.operator("level5.timeline_duplicate_split", text="Duplicate", icon='DUPLICATE')
                operator.index = index

                operator = layout.operator("level5.timeline_remove_split", text="Delete", icon='TRASH')
                operator.index = index

            layout.separator()

        if track_index == 0:
            operator = layout.operator("level5.timeline_insert_split", text="Insert Split", icon='ADD')
            operator.frame = window_manager.level5_timeline_frame
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
    LEVEL5_OT_timeline_remove_track,
    LEVEL5_OT_timeline_insert_split,
    LEVEL5_OT_timeline_remove_split,
    LEVEL5_OT_timeline_delete_key,
    LEVEL5_OT_timeline_duplicate_split,
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
