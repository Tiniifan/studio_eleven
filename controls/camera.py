import bpy

# Create a new object type for CameraEleven
class CameraElevenObject(bpy.types.Camera):
    """CameraEleven Object"""
    # Object name
    bl_idname = "custom.CameraEleven"
    # Displayed name in Blender
    bl_label = "CameraEleven"
    # Camera icon for CameraElevenObject
    bl_icon = "CAMERA"

    # Reference to the "Target" mesh object
    target_obj = None
    # Reference to the "Camera" camera object
    camera_obj = None

    # Function to create the object
    @classmethod
    def create(cls, hash_name, location):
        # Get the current scene
        scene = bpy.context.scene
        
        # Set render resolution
        scene.render.resolution_x = 400
        scene.render.resolution_y = 240
        
        # Create the CameraEleven object
        camera_eleven = bpy.data.objects.new("CameraEleven", None)
        camera_eleven.name = f"CameraEleven_{hash_name}"
        camera_eleven.location = location
        
        # Make the CameraEleven object invisible
        camera_eleven.hide_render = True
        camera_eleven.hide_viewport = True
        
        # Create the "Target" mesh object
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=location)
        target_obj = bpy.context.object
        target_obj.name = f"Target_{hash_name}"
        cls.target_obj = target_obj
        target_obj.parent = camera_eleven

        # Create the "Camera" camera object
        bpy.ops.object.camera_add(location=location)
        camera_obj = bpy.context.object
        camera_obj.name = f"Camera_{hash_name}"
        camera_obj.data.lens = 33
        cls.camera_obj = camera_obj
        camera_obj.parent = camera_eleven

        # Link the CameraEleven object to the scene
        bpy.context.collection.objects.link(camera_eleven)

        # Add a track-to constraint to the camera
        track_to_constraint = camera_obj.constraints.new(type='TRACK_TO')
        track_to_constraint.target = target_obj
        track_to_constraint.track_axis = 'TRACK_NEGATIVE_Z'
        track_to_constraint.up_axis = 'UP_Y'

        return cls
        
    def is_camera_eleven(obj):
        # Check if the object has exactly 2 children
        if len(obj.children) != 2:
            return False
        
        # Initialize flags to track if we find a camera and an empty
        found_camera = False
        found_empty = False
        
        # Iterate through the object's children
        for child in obj.children:
            # Check if the child is a camera
            if child.type == 'CAMERA':
                found_camera = True
            # Check if the child is an empty
            elif child.type == 'EMPTY':
                found_empty = True

        # Return True if we found both a camera and an empty, otherwise False
        return found_camera and found_empty
        
    def get_camera_and_target(obj):
        # Check if the object has exactly 2 children
        if len(obj.children) != 2:
            return False
        
        # Initialize flags to track if we find a camera and an empty
        camera = None
        target = None
        
        # Iterate through the object's children
        for child in obj.children:
            # Check if the child is a camera
            if child.type == 'CAMERA':
                camera = child
            # Check if the child is an empty
            elif child.type == 'EMPTY':
                target = child

        return camera, target
     
# Function to add the CameraEleven object via the Add > Camera menu
def add_CameraEleven_object(self, context):
    self.layout.operator("mesh.primitive_cameraeleven_add", icon="CAMERA_DATA")

# Operator to add the CameraEleven object
class MESH_OT_primitive_CameraEleven_add(bpy.types.Operator):
    bl_idname = "mesh.primitive_cameraeleven_add"
    bl_label = "CameraEleven"
    bl_description = "Add a new CameraEleven object"
    bl_icon = "CAMERA"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        CameraElevenObject.create("000", context.scene.cursor.location)
        return {'FINISHED'}

# Register the classes
def register():
    bpy.utils.register_class(MESH_OT_primitive_CameraEleven_add)
    bpy.types.VIEW3D_MT_camera_add.append(add_CameraEleven_object)

# Unregister the classes
def unregister():
    bpy.utils.unregister_class(MESH_OT_primitive_CameraEleven_add)
    bpy.types.VIEW3D_MT_camera_add.remove(add_CameraEleven_object)

register()