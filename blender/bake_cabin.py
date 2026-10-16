"""木屋烘焙导出：高模烘焙到低模。

    CabinParts（高模）→ 只作烘焙源，合并后不导出。
    CabinLow（低模）  → 网格 Cabin：自动展 UV；高模的颜色、法线（瓦片的倾斜、木构的侧面）和 AO
                        （瓦片缝、窗洞、木构和藤蔓的遮蔽）用「选中到活动」烘焙到低模贴图；材质 "cabin"。
    CabinFoliage      → 网格 CabinFoliage：烘焙到顶点色 "Col"（RGB 颜色，A 为 AO），
                        保留 UV 图层 "Wind"（U 摆动权重，V 相位），材质 "cabin_foliage"。

输出：
    assets/cabin/cabin.glb                  几何 + UV + 顶点色，材质只带名称（不内嵌贴图）
    assets/cabin/textures/cabin_albedo.png  木屋颜色
    assets/cabin/textures/cabin_normal.png  木屋切线空间法线
    assets/cabin/textures/cabin_ao.png      木屋环境光遮蔽（含地面和植被的遮挡）

Godot 导入时按材质名映射到 res://materials/cabin.tres 和 res://materials/cabin_foliage.tres。

用法：在 Blender 中打开 blender/cabin.blend，在文本编辑器里运行本脚本；
或命令行：blender -b blender/cabin.blend -P blender/bake_cabin.py
"""
import math
import os

import bmesh
import bpy

ALBEDO_SIZE = 1024
NORMAL_SIZE = 1024
AO_SIZE = 1024
COLOR_SAMPLES = 16
AO_SAMPLES = 128
AO_DISTANCE = 1.0
PARTS_COLLECTION = "CabinParts"
LOW_COLLECTION = "CabinLow"
# 从低模表面向外推出多远开始向内找高模表面（要盖住贴墙的木构、窗台和藤蔓）
CAGE_EXTRUSION = 0.25
MAX_RAY_DISTANCE = 0.6
FOLIAGE_COLLECTION = "CabinFoliage"
EXPORT_COLLECTION = "CabinExport"


def _layer_collection(layer_coll, name):
    if layer_coll.collection.name == name:
        return layer_coll
    for child in layer_coll.children:
        found = _layer_collection(child, name)
        if found:
            return found
    return None


def _merge(collection, export_coll, name):
    """应用修改器后把集合里的网格合并成一个对象，保留各自的制作材质和同名 UV 图层。"""
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    materials = []
    for ob in collection.objects:
        if ob.type != "MESH":
            continue
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
        me.transform(ob.matrix_world)
        start = len(bm.faces)
        bm.from_mesh(me)
        remap = []
        for m in me.materials:
            if m not in materials:
                materials.append(m)
            remap.append(materials.index(m))
        bm.faces.ensure_lookup_table()
        for i in range(start, len(bm.faces)):
            f = bm.faces[i]
            f.material_index = remap[f.material_index] if remap else 0
        bpy.data.meshes.remove(me)

    mesh = bpy.data.meshes.new(name.lower())
    bm.to_mesh(mesh)
    bm.free()
    for m in materials:
        mesh.materials.append(m)
    ob = bpy.data.objects.new(name, mesh)
    export_coll.objects.link(ob)
    return ob, materials


def _override(ob):
    return bpy.context.temp_override(active_object=ob, object=ob, selected_objects=[ob], selected_editable_objects=[ob])


def _select_only(objects):
    view_layer = bpy.context.view_layer
    for ob in view_layer.objects:
        ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    view_layer.objects.active = objects[0]


def _unwrap(ob):
    _select_only([ob])
    with _override(ob):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
        bpy.ops.uv.pack_islands(rotate=True, margin=0.02)
        bpy.ops.object.mode_set(mode="OBJECT")


def _set_bake_target(materials, image):
    for m in materials:
        nt = m.node_tree
        n = nt.nodes.get("BakeTarget") or nt.nodes.new("ShaderNodeTexImage")
        n.name = "BakeTarget"
        n.image = image
        for other in nt.nodes:
            other.select = False
        n.select = True
        nt.nodes.active = n


def _clear_bake_target(materials):
    for m in materials:
        n = m.node_tree.nodes.get("BakeTarget")
        if n:
            m.node_tree.nodes.remove(n)


def _bake(ob, bake_type, samples, **kwargs):
    bpy.context.scene.cycles.samples = samples
    with _override(ob):
        bpy.ops.object.bake(type=bake_type, margin=4, use_clear=True, **kwargs)


def _bake_from_high(high, low, bake_type, samples, **kwargs):
    """把高模的结果烘焙到低模（选中到活动）。"""
    bpy.context.scene.cycles.samples = samples
    _select_only([low, high])
    with bpy.context.temp_override(active_object=low, object=low, selected_objects=[high, low],
                                   selected_editable_objects=[high, low]):
        bpy.ops.object.bake(type=bake_type, margin=4, use_clear=True, use_selected_to_active=True,
                            cage_extrusion=CAGE_EXTRUSION, max_ray_distance=MAX_RAY_DISTANCE, **kwargs)


def _use_gpu(scn):
    """优先用 OptiX / CUDA 等 GPU 后端烘焙，找不到可用 GPU 时退回 CPU。"""
    cycles = bpy.context.preferences.addons.get("cycles")
    if cycles:
        prefs = cycles.preferences
        for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            try:
                prefs.compute_device_type = backend
            except TypeError:
                continue
            prefs.refresh_devices()
            if any(d.type == backend for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == backend
                scn.cycles.device = "GPU"
                return backend
    scn.cycles.device = "CPU"
    return "CPU"


def _new_image(name, size, non_color):
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, size, size, alpha=False)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


def _save_image(img, path):
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()


def _set_active_color(mesh, name):
    attrs = mesh.color_attributes
    names = [a.name for a in attrs]
    try:
        attrs.active_color_name = name
    except AttributeError:
        attrs.active_color = attrs[name]
    try:
        attrs.render_color_index = names.index(name)
    except AttributeError:
        pass


def _bake_vertex_colors(ob):
    """颜色烘焙到 Col 的 RGB，AO 烘焙后写进 Col 的 A。"""
    scn = bpy.context.scene
    mesh = ob.data
    mesh.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    mesh.color_attributes.new("AO", "FLOAT_COLOR", "POINT")
    scn.render.bake.target = "VERTEX_COLORS"
    try:
        _set_active_color(mesh, "Col")
        _bake(ob, "DIFFUSE", COLOR_SAMPLES, pass_filter={"COLOR"})
        _set_active_color(mesh, "AO")
        _bake(ob, "AO", AO_SAMPLES)
    finally:
        scn.render.bake.target = "IMAGE_TEXTURES"

    col = mesh.color_attributes["Col"]
    ao = mesh.color_attributes["AO"]
    n = len(col.data)
    c = [0.0] * (4 * n)
    a = [0.0] * (4 * n)
    col.data.foreach_get("color", c)
    ao.data.foreach_get("color", a)
    c[3::4] = a[0::4]
    col.data.foreach_set("color", c)
    mesh.color_attributes.remove(mesh.color_attributes["AO"])
    _set_active_color(mesh, "Col")


def _node_material(name):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.85
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat, nt, bsdf


def _cabin_preview_material(albedo, ao):
    """Blender 里预览烘焙结果：颜色 × AO。导出时不带贴图，Godot 按材质名替换。"""
    mat, nt, bsdf = _node_material("cabin")
    t_albedo = nt.nodes.new("ShaderNodeTexImage")
    t_albedo.image = albedo
    t_ao = nt.nodes.new("ShaderNodeTexImage")
    t_ao.image = ao
    mul = nt.nodes.new("ShaderNodeVectorMath")
    mul.operation = "MULTIPLY"
    nt.links.new(t_albedo.outputs["Color"], mul.inputs[0])
    nt.links.new(t_ao.outputs["Color"], mul.inputs[1])
    nt.links.new(mul.outputs["Vector"], bsdf.inputs["Base Color"])
    return mat


def _foliage_preview_material():
    """Blender 里预览植被：顶点色 RGB × A（AO）。"""
    mat, nt, bsdf = _node_material("cabin_foliage")
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    scale = nt.nodes.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    nt.links.new(attr.outputs["Color"], scale.inputs[0])
    nt.links.new(attr.outputs["Alpha"], scale.inputs["Scale"])
    nt.links.new(scale.outputs["Vector"], bsdf.inputs["Base Color"])
    return mat


def _use_single_material(ob, mat):
    mesh = ob.data
    mesh.materials.clear()
    mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.material_index = 0


def bake_and_export(project_dir):
    scn = bpy.context.scene
    parts = bpy.data.collections[PARTS_COLLECTION]
    low_src = bpy.data.collections[LOW_COLLECTION]
    foliage_src = bpy.data.collections.get(FOLIAGE_COLLECTION)
    out_dir = os.path.join(project_dir, "assets", "cabin")
    tex_dir = os.path.join(out_dir, "textures")
    os.makedirs(tex_dir, exist_ok=True)

    export_coll = bpy.data.collections.get(EXPORT_COLLECTION)
    if export_coll is None:
        export_coll = bpy.data.collections.new(EXPORT_COLLECTION)
        scn.collection.children.link(export_coll)
    for ob in list(export_coll.objects):
        bpy.data.objects.remove(ob, do_unlink=True)

    root_layer = scn.view_layers[0].layer_collection
    sources = [parts, low_src] + ([foliage_src] if foliage_src else [])
    source_layers = [_layer_collection(root_layer, c.name) for c in sources]
    for layer in source_layers + [_layer_collection(root_layer, EXPORT_COLLECTION)]:
        layer.hide_viewport = False

    high, _ = _merge(parts, export_coll, "CabinHigh")
    cabin, _ = _merge(low_src, export_coll, "Cabin")
    target = _node_material("cabin_bake_target")[0]
    _use_single_material(cabin, target)
    foliage = None
    if foliage_src:
        foliage, _ = _merge(foliage_src, export_coll, "CabinFoliage")
    _unwrap(cabin)

    # 烘焙时只让合并后的网格和临时地面参与渲染
    hidden = []
    for c in sources:
        for ob in c.objects:
            if not ob.hide_render:
                ob.hide_render = True
                hidden.append(ob)
    ground_mesh = bpy.data.meshes.new("bake_ground")
    ground_mesh.from_pydata([(-15, -15, 0), (15, -15, 0), (15, 15, 0), (-15, 15, 0)], [], [(0, 1, 2, 3)])
    ground = bpy.data.objects.new("BakeGround", ground_mesh)
    export_coll.objects.link(ground)

    scn.render.engine = "CYCLES"
    device = _use_gpu(scn)
    scn.render.bake.margin_type = "EXTEND"
    if scn.world is None:
        scn.world = bpy.data.worlds.new("CabinBakeWorld")
    try:
        scn.world.light_settings.distance = AO_DISTANCE
    except AttributeError:
        pass

    albedo = _new_image("cabin_albedo", ALBEDO_SIZE, non_color=False)
    _set_bake_target([target], albedo)
    _bake_from_high(high, cabin, "DIFFUSE", COLOR_SAMPLES, pass_filter={"COLOR"})
    _save_image(albedo, os.path.join(tex_dir, "cabin_albedo.png"))

    normal = _new_image("cabin_normal", NORMAL_SIZE, non_color=True)
    _set_bake_target([target], normal)
    _bake_from_high(high, cabin, "NORMAL", COLOR_SAMPLES, normal_space="TANGENT")
    _save_image(normal, os.path.join(tex_dir, "cabin_normal.png"))

    # AO 也从高模烘焙；低模和高模重叠，烘焙时让低模对光线不可见，避免把高模整个遮住
    ray_flags = ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission",
                 "visible_volume_scatter", "visible_shadow")
    for flag in ray_flags:
        setattr(cabin, flag, False)
    ao = _new_image("cabin_ao", AO_SIZE, non_color=True)
    _set_bake_target([target], ao)
    _bake_from_high(high, cabin, "AO", AO_SAMPLES)
    _save_image(ao, os.path.join(tex_dir, "cabin_ao.png"))
    _clear_bake_target([target])
    for flag in ray_flags:
        setattr(cabin, flag, True)
    high.hide_render = True

    if foliage:
        _bake_vertex_colors(foliage)

    for ob in hidden:
        ob.hide_render = False

    _use_single_material(cabin, _cabin_preview_material(albedo, ao))
    exported = [cabin]
    if foliage:
        _use_single_material(foliage, _foliage_preview_material())
        exported.append(foliage)

    _select_only(exported)
    bpy.context.view_layer.update()
    glb = os.path.join(out_dir, "cabin.glb")
    options = dict(filepath=glb, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
                   export_materials="EXPORT", export_image_format="NONE", export_cameras=False, export_lights=False)
    with bpy.context.temp_override(active_object=cabin, object=cabin, selected_objects=exported,
                                   selected_editable_objects=exported):
        try:
            bpy.ops.export_scene.gltf(**options, export_vertex_color="ACTIVE")
        except TypeError:
            bpy.ops.export_scene.gltf(**options, export_colors=True)

    # 临时对象在导出之后再删：导出前删除对象会让依赖图引用失效
    high_triangles = sum(len(p.vertices) - 2 for p in high.data.polygons)
    for ob in (ground, high):
        mesh = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.meshes.remove(mesh)
    bpy.context.view_layer.update()
    for layer in source_layers:
        layer.hide_viewport = True
    return {
        "glb": glb,
        "device": device,
        "high_triangles": high_triangles,
        "cabin_triangles": sum(len(p.vertices) - 2 for p in cabin.data.polygons),
        "foliage_triangles": sum(len(p.vertices) - 2 for p in foliage.data.polygons) if foliage else 0,
        "foliage_uv": [uv.name for uv in foliage.data.uv_layers] if foliage else [],
        "foliage_colors": [a.name for a in foliage.data.color_attributes] if foliage else [],
    }


if __name__ == "__main__":
    if not bpy.data.filepath:
        raise SystemExit("请先把 .blend 保存到项目的 blender/ 目录再运行")
    print(bake_and_export(os.path.abspath(os.path.join(os.path.dirname(bpy.data.filepath), ".."))))
