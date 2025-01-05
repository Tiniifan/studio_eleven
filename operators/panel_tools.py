import re
import bpy
import bmesh
import mathutils
from mathutils import Vector


from bpy.types import Operator
from bpy.props import IntProperty, StringProperty

# Operator for converting single bind to vertex group
class ConvertSingleBindToVertexGroup(bpy.types.Operator):
    bl_idname = "object.convert_single_bind_to_vertex_group"
    bl_label = "Single Bind to Vertex Group"
    bl_description = "Convert single-bone parenting to vertex groups and adds armature deform modifier."

    def execute(self, context):
        try:
            armature_name = None
            if context.view_layer.objects.active and context.view_layer.objects.active.type == 'ARMATURE':
                armature_name = context.view_layer.objects.active.name
            else:
                for obj in bpy.context.scene.objects:
                    if obj.type == 'ARMATURE':
                        armature_name = obj.name
                        break

            if not armature_name:
                self.report({'ERROR'}, "No armature found in the scene")
                return {'CANCELLED'}

            armature = bpy.data.objects[armature_name]

            for obj in bpy.context.scene.objects:
                if obj.parent == armature and obj.parent_type == 'BONE':
                    # Conserver la matrice monde
                    world_matrix = obj.matrix_world.copy()
                    parent_bone_name = obj.parent_bone

                    # Modifier la parenté
                    obj.parent = armature
                    obj.parent_type = 'OBJECT'
                    obj.matrix_world = world_matrix
                    
                    # Sélectionner l'objet
                    bpy.ops.object.select_all(action='DESELECT')  # Désélectionner tout
                    obj.select_set(True)  # Sélectionner l'objet
                    bpy.context.view_layer.objects.active = obj  # Définir comme actif

                    # Appliquer les transformations
                    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

                    # Ajouter les groupes de sommets et le modificateur
                    if obj.type == 'MESH' and parent_bone_name:
                        if parent_bone_name not in obj.vertex_groups:
                            vg = obj.vertex_groups.new(name=parent_bone_name)
                            for vertex in obj.data.vertices:
                                vg.add([vertex.index], 1.0, 'REPLACE')

                        if not any(mod.type == 'ARMATURE' and mod.object == armature for mod in obj.modifiers):
                            mod = obj.modifiers.new(name="Armature Deform", type='ARMATURE')
                            mod.object = armature

            self.report({'INFO'}, "Successfully converted single bind to vertex group")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error: {e}")
            return {'CANCELLED'}

# Operator for changing all draw priorities
class ChangeAllDrawPriority(bpy.types.Operator):
    bl_idname = "object.change_all_draw_priority"
    bl_label = "Change All Draw Priority"
    bl_description = "Sets the draw priority for all meshes in the scene."
    
    reference_point = mathutils.Vector((0, 0, 0))
    
    def distance_to_reference(self, obj, ref_point):
        obj_location = obj.matrix_world.translation
        return (obj_location - ref_point).length

    def execute(self, context):
        # Parcourir tous les objets de type 'MESH' dans la scène
        meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
        
        for mesh in meshes:
            if hasattr(mesh.data, 'brres'):
                if hasattr(mesh.data, 'level5_properties'):
                    mesh.data.level5_properties.draw_priority = mesh.data.brres.drawPrio + 10

        self.report({'INFO'}, f"The draw priority of Berry Bush has been transferred to Studio Eleven")
        return {'FINISHED'}

# Operator to read animation items from a configuration file
class AnimationItemsReader(bpy.types.Operator):
    bl_idname = "object.animation_items_reader"
    bl_label = "Animation Items Reader"
    bl_description = "Reads animation configuration from a .txt file."
    
    filepath: StringProperty(subtype="FILE_PATH", name="Filepath", description="Path to the .txt file")
    filter_glob: StringProperty(
        default="*.txt",
        options={'HIDDEN'},
        description="File filter for .txt files"
    )

    def process_animation_data(self, data):
        """
        Processes the raw text data and formats it into a structured dictionary.

        :param data: The raw animation data as a string.
        :return: A dictionary with the formatted animation data.
        """
        animations = {}

        # Split the data by AnimationType section
        sections = data.split("[AnimationType: ")
        for section in sections[1:]:  # Skip the first empty section
            lines = section.strip().splitlines()

            animation_type = lines[0].strip("]")  # Extract the animation type (Armature, UV, Material)
            name = None
            splits = {}

            # Extract the name and splits
            for line in lines[1:]:
                my_line = line
                line = line.strip(' ')
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("Splits:"):
                    continue  # Skip the Splits header line
                elif line.startswith("- Name:"):
                    # Extract split info
                    split_name = line.split(":", 1)[1].strip()
                    speed = None
                    start_frame = None
                    end_frame = None
                    for split_line in lines[lines.index(my_line) + 1:]:
                        if split_line.strip().startswith("Speed:"):
                            speed = float(split_line.split(":", 1)[1].strip())
                        elif split_line.strip().startswith("StartFrame:"):
                            start_frame = int(split_line.split(":", 1)[1].strip())
                        elif split_line.strip().startswith("EndFrame:"):
                            end_frame = int(split_line.split(":", 1)[1].strip())
                        
                        # Check if the next split begins
                        if split_line.strip().startswith("- Name:"):
                            break
                    splits[split_name] = [speed, start_frame, end_frame]

            # Add the animation to the dictionary
            if name:
                if animation_type not in animations:
                    animations[animation_type] = {}
                animations[animation_type][name] = splits

        # Return the formatted data
        return {"Animations": animations}

    def execute(self, context):
        try:
            # Read the content of the file
            with open(self.filepath, 'r') as file:
                data = file.read()

            self.report({'INFO'}, f"Successfully loaded animation data from {self.filepath}")

            # Process the data and format it into a dictionary
            formatted_data = self.process_animation_data(data)
            
            # Clear animations
            context.scene.animation_items_armature.clear()
            context.scene.animation_items_uv.clear()
            context.scene.animation_items_material.clear()
            context.scene.animation_items_camera.clear()

            # Iterate over the formatted data to set the appropriate fields
            for animation_key, animation_data in formatted_data["Animations"].items():
                # Based on the animation_key (Armature, UV, Material)
                if animation_key == "Armature":
                    collection_name = "animation_items_armature"
                    animations = context.scene.animation_armature           
                elif animation_key == "UV":
                    collection_name = "animation_items_uv"
                    animations = context.scene.animation_uv
                elif animation_key == "Material":
                    collection_name = "animation_items_material"
                    animations = context.scene.animation_material
                else:
                    continue  # Skip if the animation type is not recognized

                if len(animations) == 0:
                    animations.add()
                
                animations[0].name = list(animation_data.keys())[0]
                animations[0].checked = True 

                # Add each split item to the appropriate collection
                for split_name, animation_split_value in animation_data[animations[0].name].items():
                    # Using the operator to add items to the correct collection
                    bpy.ops.export_xc.add_animation_item(collection_name=collection_name)

                    # Now update the last item in the collection
                    collection = getattr(context.scene, collection_name)
                    last_item = collection[-1]  # Get the last item added
                    last_item.name = split_name
                    last_item.speed = float(animation_split_value[0])
                    last_item.frame_start = int(animation_split_value[1])
                    last_item.frame_end = int(animation_split_value[2])

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Error reading file: {e}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# Operator for adapting material names
class AdaptMaterialName(bpy.types.Operator):
    bl_idname = "object.adapt_material_name"
    bl_label = "Adapt Material Name"
    bl_description = "Format material names to start with 'DefaultLib.' if not already formatted."

    def execute(self, context):
        try:
            for obj in bpy.context.scene.objects:
                if obj.type == 'MESH' and obj.data.materials:
                    for mat in obj.data.materials:
                        if mat and not mat.name.startswith("DefaultLib."):
                            mat.name = f"DefaultLib.{mat.name}"
            self.report({'INFO'}, "Material names formatted successfully")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error: {e}")
            return {'CANCELLED'}

class CalculateDrawPriority(bpy.types.Operator):
    bl_idname = "object.calculate_draw_priority"
    bl_label = "Calculate Draw Priority"
    bl_description = "Calculate and set draw priority based on distance to the selected camera."

    # Méthodes pour les événements de changement
    def on_change_get_berry_bush_draw_prioty(self, context):
        self.calculate_draw_prioty_from_camera = not(self.get_berry_bush_draw_prioty)

    def on_change_calculate_draw_prioty_from_camera(self, context):
        self.get_berry_bush_draw_prioty = not(self.calculate_draw_prioty_from_camera)
    
    # Définir les propriétés Bool avec la fonction update
    get_berry_bush_draw_prioty: bpy.props.BoolProperty(
        name="Get draw priority from Berry Bush", 
        update=on_change_get_berry_bush_draw_prioty
    )   
    calculate_draw_prioty_from_camera: bpy.props.BoolProperty(
        name="Calculate draw priority from Camera", 
        update=on_change_calculate_draw_prioty_from_camera
    )
    merge_with_berry_bush: bpy.props.BoolProperty(name="Merge with Berry Bush")

    def execute(self, context):
        print(self.get_berry_bush_draw_prioty)
        
        if self.get_berry_bush_draw_prioty:
            bpy.ops.object.change_all_draw_priority()
            return {'FINISHED'}
        else:
            # Vérifier si une caméra est sélectionnée
            camera = context.view_layer.objects.active
            
            if not camera or camera.type != 'CAMERA':
                self.report({'ERROR'}, "Please select a camera.")
                return {'CANCELLED'}

            # Parcourir tous les objets mesh dans la scène
            meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
            if not meshes:
                self.report({'INFO'}, "No meshes found in the scene.")
                return {'CANCELLED'}

            # Calculer les distances entre la caméra et chaque mesh
            distances = []
            camera_location = camera.matrix_world.translation
            for mesh in meshes:
                # Obtenez la position de la mesh
                world_matrix = mesh.matrix_world
                depsgraph = context.evaluated_depsgraph_get()
                bm = bmesh.new()
                bm.from_object(mesh, depsgraph)
                x, y, z = 0.0, 0.0, 0.0
                for v in bm.verts:
                    v_x, v_y, v_z = world_matrix @ v.co
                    x += v_x
                    y += v_y
                    z += v_z
                        
                num_verts = len(bm.verts)
                x /= num_verts
                y /= num_verts
                z /= num_verts
                mesh_location = Vector((x, y, z)) 
                bm.free()
                
                distance = abs(mesh_location.x - camera_location.x)
                
                if self.merge_with_berry_bush:
                    if hasattr(mesh.data, 'brres'):
                        distances.append((mesh, distance, mesh.data.brres.drawPrio))
                    else:
                        self.report({'INFO'}, "Berry Bush must be enabled")
                        return {'CANCELLED'}
                else:
                    distances.append((mesh, distance, 0))
                    
            # sort
            distances.sort(key=lambda x: (x[2], x[1]))  # (berry_distance, distance)
            
            # reverse order
            if self.merge_with_berry_bush == False:               
                distances.reverse()

            # Réattribuer les draw priorities
            draw_priority = 0
            last_distance = None

            for mesh, distance, berry_distance in distances:
                print(mesh.name, distance, berry_distance, draw_priority)
                if hasattr(mesh.data, 'level5_properties'):
                    mesh.data.level5_properties.draw_priority = draw_priority

                if last_distance is None or last_distance != distance:
                    draw_priority += 1
                    last_distance = distance

            self.report({'INFO'}, "Draw priorities updated successfully.")
            return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
            
        if self.calculate_draw_prioty_from_camera:
            layout.prop(self, "calculate_draw_prioty_from_camera", text="Calculate draw priority from Camera")
            layout.prop(self, "merge_with_berry_bush", text="Merge with Berry Bush")
        else:
            layout.prop(self, "get_berry_bush_draw_prioty", text="Get draw priority from Berry Bush")

    def invoke(self, context, event):
        self.calculate_draw_prioty_from_camera = True
        return context.window_manager.invoke_props_dialog(self)

# Custom panel
class VIEW3D_PT_my_custom_panel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Studio Eleven"
    bl_label = "Studio Eleven Tools"

    def draw(self, context):
        layout = self.layout

        # Single Bind to Vertex Group
        row = layout.row()
        row.operator("object.convert_single_bind_to_vertex_group", text="Single Bind to Vertex Group")
        
        # Calculate Draw Priority
        row = layout.row()
        row.operator("object.calculate_draw_priority", text="Calculate Draw Priority")
        
        # Adapt Material Name
        row = layout.row()
        row.operator("object.adapt_material_name", text="Format Material Names")

        # Animation Items Reader
        row = layout.row()
        row.operator("object.animation_items_reader", text="Load Animation Config")       

def register():
    bpy.types.Scene.merge_with_berry_bush = bpy.props.BoolProperty(
        name="Merge with Berry Bush",
        description="Merge draw priority with Berry Bush",
        default=False
    )

    bpy.types.Scene.get_berry_bush_draw_prioty = bpy.props.BoolProperty(
        name="Get draw priority from Berry Bush",
        description="Transfer draw priority from Berry Bush to Studio Eleven",
        default=False
    )
    
    bpy.types.Scene.calculate_draw_prioty_from_camera = bpy.props.BoolProperty(
        name="Calculate draw priority using a camera",
        description="Calculate the draw priority based on the distance from a camera",
        default=False
    )  
    
    bpy.utils.register_class(ConvertSingleBindToVertexGroup)
    bpy.utils.register_class(ChangeAllDrawPriority)
    bpy.utils.register_class(AnimationItemsReader)
    bpy.utils.register_class(AdaptMaterialName)
    bpy.utils.register_class(CalculateDrawPriority)
    bpy.utils.register_class(VIEW3D_PT_my_custom_panel)  

def unregister():
    bpy.utils.unregister_class(ConvertSingleBindToVertexGroup)
    bpy.utils.unregister_class(ChangeAllDrawPriority)
    bpy.utils.unregister_class(AnimationItemsReader)
    bpy.utils.unregister_class(AdaptMaterialName)
    bpy.utils.unregister_class(CalculateDrawPriority)
    bpy.utils.unregister_class(VIEW3D_PT_my_custom_panel)
    
    del bpy.types.Scene.merge_with_berry_bush
    del bpy.types.Scene.get_berry_bush_draw_prioty
    del bpy.types.Scene.calculate_draw_prioty_from_camera

register()