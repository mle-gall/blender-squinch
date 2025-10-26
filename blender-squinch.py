bl_info = {
    "name": "Squinched Media Setup",
    "author": "Maxence Le Gall",
    "version": (2, 0, 0),
    "blender": (3, 3, 0),
    "location": "View3D > Sidebar (N) > Squinch",
    "description": "Automated projection squinching for moving cameras (US Patent 6,462,769 - Trowbridge & Coup)",
    "category": "Render",
}

import math
from math import atan2, tan
from typing import List, Tuple

import bpy
import mathutils
from mathutils import Vector, Matrix


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------


def get_scene() -> bpy.types.Scene:
    return bpy.context.scene


def find_object(name: str) -> bpy.types.Object:
    return bpy.data.objects.get(name)


def ensure_empty(name: str, location: Vector, parent: bpy.types.Object, collection: bpy.types.Collection) -> bpy.types.Object:
    obj = find_object(name)
    if obj is None:
        obj = bpy.data.objects.new(name, None)
        obj.empty_display_type = 'PLAIN_AXES'
        obj.empty_display_size = 0.1
        collection.objects.link(obj)
    obj.matrix_world = Matrix.Translation(location)
    # Parent while keeping world transform
    obj.parent = parent
    obj.matrix_parent_inverse = parent.matrix_world.inverted_safe()
    return obj


def _mesh_world_vertices(obj: bpy.types.Object) -> List[Vector]:
    mw = obj.matrix_world
    me = obj.data
    return [mw @ v.co for v in me.vertices]


def _compute_plane_basis(plane: bpy.types.Object) -> Tuple[Vector, Vector, Vector, Vector]:
    """
    Returns (origin, axis_u, axis_v, normal) in WORLD space for the plane's mesh.
    - origin: centroid of mesh vertices (world space)
    - axis_u, axis_v: unit tangent axes spanning the plane (orthonormal)
    - normal: unit normal vector (axis_u x axis_v)
    """
    verts = _mesh_world_vertices(plane)
    if not verts:
        # Fallback to object origin axes
        n = (plane.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
        up_ref = Vector((0, 0, 1)) if abs(n.dot(Vector((0, 0, 1)))) < 0.999 else Vector((0, 1, 0))
        u = (up_ref.cross(n)).normalized()
        v = (n.cross(u)).normalized()
        o = plane.matrix_world.translation.copy()
        return o, u, v, n

    # Origin as centroid
    o = Vector((0.0, 0.0, 0.0))
    for p in verts:
        o += p
    o /= float(len(verts))

    # Normal from averaged face normals if faces exist, else from verts
    n = None
    me = plane.data
    if getattr(me, 'polygons', None) and len(me.polygons) >= 1:
        acc = Vector((0.0, 0.0, 0.0))
        m3 = plane.matrix_world.to_3x3()
        for poly in me.polygons:
            acc += (m3 @ poly.normal) * poly.area
        if acc.length > 1e-12:
            n = acc.normalized()
    if n is None:
        # Fallback: use first three distinct points
        p0 = verts[0]
        p1 = None
        for p in verts[1:]:
            if (p - p0).length > 1e-8:
                p1 = p
                break
        p2 = None
        if p1 is not None:
            for p in verts[2:]:
                if ((p - p0).cross(p1 - p0)).length > 1e-8:
                    p2 = p
                    break
        if p1 is None or p2 is None:
            n = Vector((0, 0, 1))
        else:
            n = ((p1 - p0).cross(p2 - p0)).normalized()

    # Build orthonormal basis (u, v, n)
    up_ref = Vector((0, 0, 1)) if abs(n.dot(Vector((0, 0, 1)))) < 0.999 else Vector((0, 1, 0))
    u = (up_ref.cross(n)).normalized()
    v = (n.cross(u)).normalized()
    return o, u, v, n


def get_plane_corner_world_positions(plane: bpy.types.Object) -> dict:
    """
    Compute world positions of plane corners using a robust plane basis.
    Labels are relative to basis (u = right, v = up):
    - bottom: smaller v
    - top: larger v
    - left: smaller u
    - right: larger u
    Returns keys: bottom_left, bottom_right, top_left, top_right
    """
    o, u, v, n = _compute_plane_basis(plane)
    verts = _mesh_world_vertices(plane)
    # Project onto basis
    us = [p.dot(u) for p in verts]
    vs = [p.dot(v) for p in verts]
    min_u, max_u = (min(us), max(us)) if us else (0.0, 1.0)
    min_v, max_v = (min(vs), max(vs)) if vs else (0.0, 1.0)

    # To reconstruct positions, we need coordinates relative to origin o.
    # Use mean of projections at origin to offset properly.
    o_u = o.dot(u)
    o_v = o.dot(v)

    def pos(uu: float, vv: float) -> Vector:
        return o + (uu - o_u) * u + (vv - o_v) * v

    return {
        'bottom_left': pos(min_u, min_v),
        'bottom_right': pos(max_u, min_v),
        'top_left': pos(min_u, max_v),
        'top_right': pos(max_u, max_v),
    }


def width_height_from_corners(plane: bpy.types.Object) -> Tuple[float, float]:
    o, u, v, n = _compute_plane_basis(plane)
    verts = _mesh_world_vertices(plane)
    if not verts:
        return 1.0, 1.0
    us = [p.dot(u) for p in verts]
    vs = [p.dot(v) for p in verts]
    width = max(us) - min(us)
    height = max(vs) - min(vs)
    return float(abs(width)), float(abs(height))


def get_corner_empty_name(plane_name: str, label: str) -> str:
    return f"Squinch_{plane_name}_{label}"


def get_orientation_empty_name(plane_name: str) -> str:
    return f"Squinch_Orientation_{plane_name}"


def get_corner_empties(plane_name: str) -> List[bpy.types.Object]:
    names = [
        get_corner_empty_name(plane_name, 'bottom_left'),
        get_corner_empty_name(plane_name, 'bottom_right'),
        get_corner_empty_name(plane_name, 'top_left'),
        get_corner_empty_name(plane_name, 'top_right'),
    ]
    return [find_object(n) for n in names]


def create_corner_empties(plane: bpy.types.Object, collection: bpy.types.Collection) -> dict:
    corners = get_plane_corner_world_positions(plane)
    created = {}
    for label, loc in corners.items():
        name = get_corner_empty_name(plane.name, label)
        created[label] = ensure_empty(name, loc, plane, collection)
    return created


def ensure_orientation_empty(plane: bpy.types.Object, camera: bpy.types.Object, collection: bpy.types.Collection) -> bpy.types.Object:
    name = get_orientation_empty_name(plane.name)
    obj = find_object(name)
    if obj is None:
        obj = bpy.data.objects.new(name, None)
        obj.empty_display_type = 'ARROWS'
        obj.empty_display_size = 0.2
        collection.objects.link(obj)
    # Compute world-space basis so Z aligns with plane normal, flipping to face camera side
    o, u, v, n = _compute_plane_basis(plane)
    if camera is not None:
        side = (camera.matrix_world.translation - o).dot(n)
        if side < 0.0:
            # Camera is on the back side; flip normal to face camera
            n = -n
            # Rebuild orthonormal basis to keep right-handed frame
            up_ref = Vector((0, 0, 1)) if abs(n.dot(Vector((0, 0, 1)))) < 0.999 else Vector((0, 1, 0))
            u = (up_ref.cross(n)).normalized()
            v = (n.cross(u)).normalized()
    basis = Matrix((u, v, n)).transposed()  # columns = u, v, n
    mw = Matrix.Translation(o) @ basis.to_4x4()
    # Parent while keeping world transform
    obj.parent = plane
    obj.matrix_parent_inverse = plane.matrix_world.inverted_safe()
    obj.matrix_world = mw
    return obj


def set_render_aspect_to_plane(scene: bpy.types.Scene, plane: bpy.types.Object) -> None:
    width, height = width_height_from_corners(plane)
    if width <= 0.0 or height <= 0.0:
            return
    aspect = width / height
    # Keep current X (rounded to even), adjust Y to match aspect (also even)
    res_x = max(2, int(scene.render.resolution_x))
    if res_x % 2 != 0:
        res_x += 1
    res_y = max(2, int(round(res_x / aspect)))
    if res_y % 2 != 0:
        # Minimal bump to nearest even
        res_y += 1
    scene.render.resolution_x = res_x
    scene.render.resolution_y = res_y
    scene.render.pixel_aspect_x = 1.0
    scene.render.pixel_aspect_y = 1.0


def add_copy_rotation_constraint(camera: bpy.types.Object, target: bpy.types.Object) -> None:
    # Remove existing constraint with same name to avoid duplicates
    name = "Squinch Copy Rotation"
    for c in list(camera.constraints):
        if c.name == name:
            camera.constraints.remove(c)
    con = camera.constraints.new(type='COPY_ROTATION')
    con.name = name
    con.target = target
    con.mix_mode = 'REPLACE'
    con.use_x = True
    con.use_y = True
    con.use_z = True
    con.target_space = 'WORLD'
    con.owner_space = 'WORLD'


# -----------------------------------------------------------------------------
# Driver Functions (Camera-space, orientation agnostic)
# -----------------------------------------------------------------------------


# Cache to avoid recalculating same data multiple times per frame
_squinch_cache = {'frame': -1, 'data': None}


def _calculate_squinch_data():
    """Calculate all squinch values once per frame and cache them"""
    scene = get_scene()
    current_frame = scene.frame_current
    
    # Return cached data if same frame
    if _squinch_cache['frame'] == current_frame and _squinch_cache['data'] is not None:
        return _squinch_cache['data']
    
    # Get context
    camera_name = scene.get('squinch_camera_name')
    plane_name = scene.get('squinch_plane_name')
    if not camera_name or not plane_name:
        return None
    
    cam = find_object(camera_name)
    plane = find_object(plane_name)
    if cam is None or plane is None:
        return None
    
    empties = get_corner_empties(plane.name)
    if any(e is None for e in empties):
        return None
    
    try:
        # Transform corners to camera space once
        cam_inv = cam.matrix_world.inverted_safe()
        corners_cam = [cam_inv @ e.matrix_world.translation for e in empties]
        
        # Calculate perspective-normalized coordinates
        eps = 1e-4
        u_vals = []
        v_vals = []
        for p in corners_cam:
            dz = max(-p.z, eps)  # Clamp depth
            u_vals.append(p.x / dz)
            v_vals.append(p.y / dz)
        
        # Calculate extents
        u_min, u_max = min(u_vals), max(u_vals)
        width_u = u_max - u_min
        center_u = (u_min + u_max) * 0.5
        center_v = sum(v_vals) * 0.25  # Average of 4 corners
        
        # Cache results
        sensor_width = cam.data.sensor_width
        data = {
            'width_u': width_u,
            'center_u': center_u,
            'center_v': center_v,
            'sensor_width': sensor_width,
            'current_lens': cam.data.lens
        }
        _squinch_cache['frame'] = current_frame
        _squinch_cache['data'] = data
        return data
        
    except Exception:
        return None


def squinch_horizontal_fov() -> float:
    data = _calculate_squinch_data()
    if data is None or abs(data['width_u']) <= 1e-9:
                return 35.0
    focal = data['sensor_width'] / data['width_u']
    return max(1.0, float(focal))


def squinch_horizontal_shift() -> float:
    data = _calculate_squinch_data()
    if data is None or abs(data['width_u']) <= 1e-9:
        return 0.0
    shift = data['center_u'] / data['width_u']
    return float(shift)


def squinch_vertical_shift() -> float:
    data = _calculate_squinch_data()
    if data is None or abs(data['width_u']) <= 1e-9:
        return 0.0
    shift = data['center_v'] / data['width_u']
    return float(shift)


def register_driver_functions():
    ns = bpy.app.driver_namespace
    ns['squinch_horizontal_fov'] = squinch_horizontal_fov
    ns['squinch_horizontal_shift'] = squinch_horizontal_shift
    ns['squinch_vertical_shift'] = squinch_vertical_shift


def unregister_driver_functions():
    ns = bpy.app.driver_namespace
    for key in ['squinch_horizontal_fov', 'squinch_horizontal_shift', 'squinch_vertical_shift']:
        if key in ns:
            try:
                del ns[key]
            except Exception:
                pass


def add_driver_single(scene: bpy.types.Scene, id_data: bpy.types.ID, data_path: str, expression: str) -> None:
    # Remove existing fcurve/driver for cleanliness
    ad = id_data.animation_data
    if ad and ad.drivers:
        for fcu in list(ad.drivers):
            if fcu.data_path == data_path:
                id_data.animation_data.drivers.remove(fcu)

    if id_data.animation_data is None:
        id_data.animation_data_create()

    fcu = id_data.driver_add(data_path)
    drv = fcu.driver
    drv.type = 'SCRIPTED'
    drv.expression = expression
    # Add frame dependency so drivers update when the camera moves on a path
    var = drv.variables.new()
    var.name = 'frame'
    var.type = 'SINGLE_PROP'
    targ = var.targets[0]
    targ.id_type = 'SCENE'
    targ.id = scene
    targ.data_path = 'frame_current'
    # Also depend on subframe time to update during render-time subframe sampling
    var2 = drv.variables.new()
    var2.name = 'subframe'
    var2.type = 'SINGLE_PROP'
    targ2 = var2.targets[0]
    targ2.id_type = 'SCENE'
    targ2.id = scene
    targ2.data_path = 'frame_subframe'


def add_squinch_driver_with_deps(
    scene: bpy.types.Scene,
    id_data: bpy.types.ID,
    data_path: str,
    expression: str,
    empties: List[bpy.types.Object],
    camera: bpy.types.Object,
    follow_path: bpy.types.Constraint = None,
    follow_path_target: bpy.types.Object = None,
) -> None:
    # Create base driver
    add_driver_single(scene, id_data, data_path, expression)
    # Append transform dependencies so evaluation order is stable in render
    fcu = None
    for d in id_data.animation_data.drivers:
        if d.data_path == data_path:
            fcu = d
            break
    if fcu is None:
        return
    drv = fcu.driver
    # Add camera dependencies: location and rotation in world space
    for comp in ('X', 'Y', 'Z'):
        v = drv.variables.new()
        v.name = f'cam_loc{comp.lower()}'
        v.type = 'TRANSFORMS'
        t = v.targets[0]
        t.id = camera
        t.transform_type = f'LOC_{comp}'
        t.transform_space = 'WORLD_SPACE'
    for comp in ('X', 'Y', 'Z'):
        v = drv.variables.new()
        v.name = f'cam_rot{comp.lower()}'
        v.type = 'TRANSFORMS'
        t = v.targets[0]
        t.id = camera
        t.transform_type = f'ROT_{comp}'
        t.transform_space = 'WORLD_SPACE'

    # Add empties dependencies: location (XYZ) to catch boundary changes
    for idx, e in enumerate(empties):
        for comp in ('X', 'Y', 'Z'):
            v = drv.variables.new()
            v.name = f'e{idx}_loc{comp.lower()}'
            v.type = 'TRANSFORMS'
            t = v.targets[0]
            t.id = e
            t.transform_type = f'LOC_{comp}'
            t.transform_space = 'WORLD_SPACE'

    # If camera uses Follow Path, add its driving properties as dependencies
    if follow_path is not None:
        # Constraint offset / offset_factor
        if hasattr(follow_path, 'offset_factor'):
            v = drv.variables.new()
            v.name = 'fp_offsetf'
            v.type = 'SINGLE_PROP'
            t = v.targets[0]
            t.id_type = 'OBJECT'
            t.id = camera
            t.data_path = f'constraints["{follow_path.name}"]\.offset_factor'
        if hasattr(follow_path, 'offset'):
            v = drv.variables.new()
            v.name = 'fp_offset'
            v.type = 'SINGLE_PROP'
            t = v.targets[0]
            t.id_type = 'OBJECT'
            t.id = camera
            t.data_path = f'constraints["{follow_path.name}"]\.offset'
        # Curve eval_time (if Path Animation is used)
        if follow_path_target is not None and getattr(follow_path_target, 'data', None) is not None:
            v = drv.variables.new()
            v.name = 'curve_eval_time'
            v.type = 'SINGLE_PROP'
            t = v.targets[0]
            t.id_type = 'CURVE'
            t.id = follow_path_target.data
            t.data_path = 'eval_time'


def setup_camera_drivers(scene: bpy.types.Scene, camera: bpy.types.Object, plane: bpy.types.Object, empties: List[bpy.types.Object]) -> None:
    register_driver_functions()
    scene['squinch_camera_name'] = camera.name
    scene['squinch_plane_name'] = plane.name

    cam_data = camera.data
    # Detect Follow Path constraint and its target
    fp_con = None
    fp_target = None
    for c in camera.constraints:
        if c.type == 'FOLLOW_PATH':
            fp_con = c
            fp_target = getattr(c, 'target', None)
            break

    add_squinch_driver_with_deps(scene, cam_data, 'lens', 'squinch_horizontal_fov()', empties, camera, fp_con, fp_target)
    add_squinch_driver_with_deps(scene, cam_data, 'shift_x', 'squinch_horizontal_shift()', empties, camera, fp_con, fp_target)
    add_squinch_driver_with_deps(scene, cam_data, 'shift_y', 'squinch_vertical_shift()', empties, camera, fp_con, fp_target)


def clear_camera_drivers(scene: bpy.types.Scene, camera: bpy.types.Object) -> None:
        cam_data = camera.data
    if cam_data.animation_data and cam_data.animation_data.drivers:
        for fcu in list(cam_data.animation_data.drivers):
            if fcu.data_path in {'lens', 'shift_x', 'shift_y'}:
                cam_data.animation_data.drivers.remove(fcu)
    # Cleanup scene properties
    for key in ['squinch_camera_name', 'squinch_plane_name']:
        if key in scene:
            try:
                del scene[key]
            except Exception:
                pass
    unregister_driver_functions()


# -----------------------------------------------------------------------------
# Properties
# -----------------------------------------------------------------------------


def scene_pointer_properties():
    if not hasattr(bpy.types.Scene, 'squinch_plane'):
        bpy.types.Scene.squinch_plane = bpy.props.PointerProperty(
            name="Projection Plane",
            type=bpy.types.Object,
            description="Mesh object used as the projection plane",
        )
    if not hasattr(bpy.types.Scene, 'squinch_camera'):
        bpy.types.Scene.squinch_camera = bpy.props.PointerProperty(
            name="Camera",
            type=bpy.types.Object,
            description="Camera to drive",
        )


# -----------------------------------------------------------------------------
# Operators
# -----------------------------------------------------------------------------


class SQUINCH_OT_setup(bpy.types.Operator):
    bl_idname = "squinch.setup"
    bl_label = "Setup Squinch Scene"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        plane = scene.squinch_plane
        camera = scene.squinch_camera

        if plane is None or plane.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object as the Projection Plane")
            return {'CANCELLED'}
        if camera is None or camera.type != 'CAMERA':
            self.report({'ERROR'}, "Select a Camera to drive")
            return {'CANCELLED'}
        
        # Create empties and orientation helper in the active collection
        collection = context.view_layer.active_layer_collection.collection

        corner_map = create_corner_empties(plane, collection)
        empties = [corner_map['bottom_left'], corner_map['bottom_right'], corner_map['top_left'], corner_map['top_right']]
        orient_helper = ensure_orientation_empty(plane, camera, collection)

        # Match render aspect to plane
        set_render_aspect_to_plane(scene, plane)

        # Constrain camera orientation to face and stay parallel to plane
        add_copy_rotation_constraint(camera, orient_helper)

        # Add camera drivers for lens and shifts
        setup_camera_drivers(scene, camera, plane, empties)

        # Ensure sensor fit is horizontal for consistent FOV mapping
        if hasattr(camera.data, 'sensor_fit'):
            camera.data.sensor_fit = 'HORIZONTAL'

        self.report({'INFO'}, f"Squinch setup complete for plane '{plane.name}' and camera '{camera.name}'.")
        return {'FINISHED'}


class SQUINCH_OT_clear(bpy.types.Operator):
    bl_idname = "squinch.clear"
    bl_label = "Clear Squinch Setup"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        plane = scene.squinch_plane
        camera = scene.squinch_camera

        # Remove drivers
        if camera and camera.type == 'CAMERA':
            clear_camera_drivers(scene, camera)

        # Remove constraint
        if camera:
            for c in list(camera.constraints):
                if c.name == "Squinch Copy Rotation":
                    camera.constraints.remove(c)

        # Remove empties
        if plane:
            for e in get_corner_empties(plane.name):
                if e and e.users == 1:
                    bpy.data.objects.remove(e, do_unlink=True)
            orient = find_object(get_orientation_empty_name(plane.name))
            if orient and orient.users == 1:
                bpy.data.objects.remove(orient, do_unlink=True)

        self.report({'INFO'}, "Squinch setup cleared.")
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# UI Panel
# -----------------------------------------------------------------------------


class SQUINCH_PT_panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Squinch'
    bl_label = 'Squinched Media'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.use_property_split = True

        col = layout.column()
        col.prop(scene, "squinch_plane")
        col.prop(scene, "squinch_camera")

        col.separator()
        row = col.row()
        row.operator("squinch.setup", icon='CONSTRAINT')
        row = col.row()
        row.operator("squinch.clear", icon='TRASH')


# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------


classes = (
    SQUINCH_OT_setup,
    SQUINCH_OT_clear,
    SQUINCH_PT_panel,
)


def register():
    scene_pointer_properties()
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    # Remove properties to avoid stale pointers
    if hasattr(bpy.types.Scene, 'squinch_plane'):
        del bpy.types.Scene.squinch_plane
    if hasattr(bpy.types.Scene, 'squinch_camera'):
        del bpy.types.Scene.squinch_camera


if __name__ == "__main__":
    register()


