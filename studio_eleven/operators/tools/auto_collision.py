import bpy
import bmesh
import re

##########################################
# Auto Collision Function
##########################################

def get_next_name(base_name, suffix):
    """Find the next available name using the _colX or _kabeX prefix"""
    existing_numbers = []
    pattern = re.compile(rf"^{re.escape(base_name)}{suffix}(\d+)$")

    for obj in bpy.data.objects:
        match = pattern.match(obj.name)
        if match:
            existing_numbers.append(int(match.group(1)))

    if not existing_numbers:
        return f"{base_name}{suffix}1"
    else:
        return f"{base_name}{suffix}{max(existing_numbers) + 1}"


def create_clean_duplicate(context, original_obj, new_name):
    """Duplicate the object and remove the textures/materials"""
    # Force Object Mode
    if bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Duplicate the object
    new_obj = original_obj.copy()
    new_obj.data = original_obj.data.copy()
    new_obj.name = new_name
    context.collection.objects.link(new_obj)

    # Clear materials
    new_obj.data.materials.clear()

    # Deselect all and select the new one
    bpy.ops.object.select_all(action='DESELECT')
    new_obj.select_set(True)
    context.view_layer.objects.active = new_obj

    return new_obj


def force_triangulate(obj):
    """Safely and strictly triangulate the mesh using low-level BMesh API. 
       This prevents silent failures that can happen with bpy.ops or modifiers."""
    if bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
        
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    
    # Triangulate all faces (Quads and N-gons)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
    
    # Write back to the mesh and free resources
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

##########################################
# Register class
##########################################

class OBJECT_OT_CreateFloorCollision(bpy.types.Operator):
    bl_idname = "object.create_floor_collision"
    bl_label = "Create Floor Collision"    
    bl_description = "Create a floor collision mesh from the selected object, with adjustable thickness"
    bl_options = {'REGISTER', 'UNDO'}
    
    thickness: bpy.props.FloatProperty(
        name="Thickness (m)",
        description="Thickness of the floor collision",
        default=1.0,
        min=0.01
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        # Get the currently active/selected object
        orig_obj = context.active_object
        
        # Generate a valid sequential name for the floor collision (e.g., _col1)
        new_name = get_next_name(orig_obj.name, "_col")
        
        # Create a duplicate of the original object without materials
        new_obj = create_clean_duplicate(context, orig_obj, new_name)

        # Add a Solidify modifier to give thickness to the floor collision
        mod = new_obj.modifiers.new(name="Solidify_Collision", type='SOLIDIFY')
        mod.thickness = self.thickness
        mod.offset = -1.0  # Offset -1.0 forces extrusion downwards so the top surface matches original height

        # Apply the Solidify modifier to bake the geometry
        bpy.ops.object.modifier_apply(modifier=mod.name)

        # Strictly force triangulation using BMesh (Fixes exporter errors)
        force_triangulate(new_obj)

        # Set the Level 5 mesh type to Collision
        new_obj.data.level5_properties.mesh_type = 'COLLISION'

        # Report success message in Blender's info bar
        self.report({'INFO'}, f"Floor collision created and triangulated: {new_name}")
        return {'FINISHED'}


class OBJECT_OT_CreateWallCollision(bpy.types.Operator):
    bl_idname = "object.create_wall_collision"
    bl_label = "Create Wall Collision"
    bl_description = "Create a wall collision mesh by extruding the outer edges of the selected object upward"
    bl_options = {'REGISTER', 'UNDO'}  

    height: bpy.props.FloatProperty(
        name="Wall Height (m)",
        description="Height of the wall collision",
        default=52.0,
        min=0.1
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        # Get the currently active/selected object
        orig_obj = context.active_object

        # Generate a valid sequential name for the wall collision (e.g., _kabe1)
        new_name = get_next_name(orig_obj.name, "_kabe")
        
        # Create a duplicate of the original object without materials
        new_obj = create_clean_duplicate(context, orig_obj, new_name)

        # Apply Rotation and Scale so the Z height extrusion is accurate
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

        # Switch to Edit mode on the newly duplicated object
        bpy.ops.object.mode_set(mode='EDIT')
        context.tool_settings.mesh_select_mode = (False, True, False) # Edge Selection Mode

        # Use BMesh for cleanup and selection based on wall.py logic
        bm = bmesh.from_edit_mesh(new_obj.data)

        # Merge overlapping vertices (remove doubles)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        # Deselect everything beforehand
        for v in bm.verts: v.select = False
        for e in bm.edges: e.select = False
        for f in bm.faces: f.select = False

        # Select the outer boundary edges (edges linked to exactly 1 face)
        edges_found = 0
        for edge in bm.edges:
            if len(edge.link_faces) == 1:
                edge.select = True
                edges_found += 1

        # Update the mesh in Blender with our active selection
        bmesh.update_edit_mesh(new_obj.data)
        
        if edges_found == 0:
            self.report({'WARNING'}, "No outer edges found for extrusion!")
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.data.objects.remove(new_obj) # Clean up the failed object
            return {'CANCELLED'}

        # Simulate pressing 'E' and moving on the Z axis (upwards)
        bpy.ops.mesh.extrude_region_move(
            TRANSFORM_OT_translate={
                "value": (0, 0, self.height), # Displacement (X, Y, Z)
                "orient_type": 'GLOBAL'       # Global Z axis (towards the sky)
            }
        )

        # Recalculate normals to ensure they point outward
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)

        # Switch back to Object Mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Strictly force triangulation using BMesh (Fixes exporter errors)
        force_triangulate(new_obj)

        # Set the Level 5 mesh type to Collision
        new_obj.data.level5_properties.mesh_type = 'COLLISION'

        # Report success message in Blender's info bar
        self.report({'INFO'}, f"Wall collision created and triangulated: {new_name} ({edges_found} edges extruded)")
        return {'FINISHED'}


def auto_collision_menu_func(self, context):
    self.layout.separator()
    self.layout.operator_context = 'INVOKE_DEFAULT'
    self.layout.operator(OBJECT_OT_CreateFloorCollision.bl_idname, icon='MESH_PLANE')
    self.layout.operator(OBJECT_OT_CreateWallCollision.bl_idname, icon='MESH_CUBE')

##########################################
# Register
##########################################

classes = (
    OBJECT_OT_CreateFloorCollision,
    OBJECT_OT_CreateWallCollision,
)

def register_auto_collision():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.VIEW3D_MT_object_context_menu.append(auto_collision_menu_func)

def unregister_auto_collision():
    bpy.types.VIEW3D_MT_object_context_menu.remove(auto_collision_menu_func)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
