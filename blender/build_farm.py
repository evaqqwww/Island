"""生成农田和牧场的道具：菜畦（种卷心菜）、牧场围栏（带门架）、奶牛（站立、低头吃草两种姿势）。

用法（后台运行，不影响正在打开的 Blender）：
    blender -b --factory-startup -P blender/build_farm.py
输出：
    assets/farm/farm.glb                 网格 FarmPlot / PastureFence（材质 farm_props）、Cow_Stand / Cow_Graze（材质 farm_cow）
    assets/farm/textures/cow_albedo.png  两头奶牛共用的颜色图集（左半站立、右半吃草）
    assets/farm/textures/cow_ao.png      同一套 UV 的 AO
    blender/farm.blend                   以上内容的 Blender 源文件
菜畦和围栏的颜色写在顶点色 Col 里（线性空间），并按离地高度做简单的遮蔽压暗（ao_height 以下逐渐变暗）。
奶牛：躯干、四肢、脖子和头用基本形体拼出，体素重构合成一个光滑整体后减面；耳朵、角、尾巴单独用低模。
黑白花斑、口鼻、乳房、蹄子由程序化材质按物体坐标上色，烘焙进贴图（Cycles，优先用 GPU）。
面数按当前相机（45～70 米、手机竖屏）来定：一头牛约 1000 个三角形，一块菜畦约 300 个，整圈围栏约 800 个。
坐标：Blender 单位为米，-Y 为正面（围栏的门所在一侧），导出到 Godot 后正面朝 +Z；奶牛头朝 +Y（Godot 里朝 -Z）。
"""
import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(PROJECT, "assets", "farm")
TEX_DIR = os.path.join(OUT_DIR, "textures")
PASTURE_SIZE = (6.5, 4.5)   # 围栏 x、y 方向的边长
GATE_WIDTH = 1.4
POST_SPACING = 1.1

COW_BODY_TRIS = 900         # 体素重构后的身体减到这个面数
COW_VOXEL = 0.02
COW_TEX_SIZE = (512, 256)   # 每头牛占 256 × 256
COLOR_SAMPLES = 4
AO_SAMPLES = 128
AO_DISTANCE = 0.5


def lin(c):
    return tuple((v / 255.0) ** 2.2 for v in c)


WOOD = lin((120, 88, 58))
FENCE_WOOD = lin((112, 84, 58))
SOIL = lin((104, 72, 48))
LEAF_DARK = lin((78, 138, 56))
LEAF_LIGHT = lin((176, 214, 120))

COW_WHITE = lin((224, 220, 210))
COW_BLACK = lin((34, 32, 33))
COW_PINK = lin((232, 182, 178))
COW_NOSE = lin((196, 132, 132))
COW_HOOF = lin((64, 56, 50))
COW_HORN = lin((228, 216, 184))

# 两种姿势：poll 是头顶（两角之间）的位置，face 是从头顶指向鼻尖的方向；
# patch_seed 让两头牛的花斑不同，black_head 为 true 时整个头是黑的。
UDDER = ((0.0, -0.3, 0.48), (0.14, 0.16, 0.1))   # 乳房的中心和半径
COW_POSES = {
    "Cow_Stand": dict(poll=(0.0, 0.86, 1.26), face=(0.0, 0.6, -0.8), patch_seed=2.6, black_head=True),
    "Cow_Graze": dict(poll=(0.0, 0.97, 0.62), face=(0.0, 0.3, -0.95), patch_seed=4.7, black_head=False),
}


class MeshBuilder:
    """往同一个 bmesh 里加方块和二十面体，并按面写顶点色。"""

    def __init__(self, name, ao_height=0.8):
        self.name = name
        self.ao_height = ao_height
        self.bm = bmesh.new()
        self.col = self.bm.loops.layers.float_color.new("Col")

    def box(self, center, half, color, rot=None):
        before = set(self.bm.faces)
        m = Matrix.Translation(center) @ (rot or Matrix.Identity(4)) @ Matrix.Diagonal((half[0] * 2, half[1] * 2, half[2] * 2, 1))
        bmesh.ops.create_cube(self.bm, size=1.0, matrix=m)
        self._paint(set(self.bm.faces) - before, color)

    def ico(self, center, radius, scale, color):
        before = set(self.bm.faces)
        bmesh.ops.create_icosphere(self.bm, subdivisions=1, radius=radius,
                                   matrix=Matrix.Translation(center) @ Matrix.Diagonal((*scale, 1)))
        self._paint(set(self.bm.faces) - before, color)

    def _paint(self, faces, color):
        for f in faces:
            j = random.uniform(0.94, 1.06)
            for loop in f.loops:
                occ = 0.62 + 0.38 * min(1.0, max(0.0, loop.vert.co.z / self.ao_height))
                loop[self.col] = (color[0] * j * occ, color[1] * j * occ, color[2] * j * occ, 1.0)

    def finish(self, material):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        attrs = me.color_attributes
        attrs.active_color = attrs["Col"]
        attrs.render_color_index = [a.name for a in attrs].index("Col")
        me.materials.append(material)
        return me


def farm_plot():
    """木框菜畦 1.8 × 1.1 米，种两行三列卷心菜。"""
    b = MeshBuilder("FarmPlot", ao_height=0.3)
    for sy in (-1, 1):
        b.box((0, sy * 0.55, 0.125), (0.9, 0.04, 0.125), WOOD)
    for sx in (-1, 1):
        b.box((sx * 0.88, 0, 0.125), (0.04, 0.51, 0.125), WOOD)
    b.box((0, 0, 0.09), (0.85, 0.51, 0.09), SOIL)
    for x in (-0.55, 0.0, 0.55):
        for y in (-0.24, 0.24):
            p = Vector((x + random.uniform(-0.04, 0.04), y + random.uniform(-0.03, 0.03), 0.0))
            b.ico(p + Vector((0, 0, 0.25)), 0.24, (1.0, 1.0, 0.6), LEAF_DARK)
            b.ico(p + Vector((0, 0, 0.31)), 0.12, (1.0, 1.0, 1.0), LEAF_LIGHT)
    return b


def pasture_fence():
    """矩形围栏，正面（-Y）中间开门，门两侧是高门柱和横梁。"""
    b = MeshBuilder("PastureFence")
    hw, hd = PASTURE_SIZE[0] / 2, PASTURE_SIZE[1] / 2
    gate = GATE_WIDTH / 2
    run = [Vector((-gate, -hd, 0)), Vector((-hw, -hd, 0)), Vector((-hw, hd, 0)), Vector((hw, hd, 0)),
           Vector((hw, -hd, 0)), Vector((gate, -hd, 0))]
    posts = []
    for p0, p1 in zip(run, run[1:]):
        n = max(1, math.ceil((p1 - p0).length / POST_SPACING))
        posts += [p0.lerp(p1, k / n) for k in range(n)]
    posts.append(run[-1])
    for p in posts[1:-1]:
        b.box(p + Vector((0, 0, 0.45)), (0.05, 0.05, 0.45), FENCE_WOOD)
    for p0, p1 in zip(posts, posts[1:]):
        d = p1 - p0
        rot = Matrix.Rotation(math.atan2(d.y, d.x), 4, "Z")
        for z in (0.42, 0.78):
            b.box((p0 + p1) / 2 + Vector((0, 0, z)), (d.length / 2 + 0.03, 0.025, 0.04), FENCE_WOOD, rot)
    for sx in (-1, 1):
        b.box((sx * gate, -hd, 0.875), (0.07, 0.07, 0.875), FENCE_WOOD)
    b.box((0, -hd, 1.68), (gate + 0.15, 0.06, 0.07), FENCE_WOOD)
    return b


# ---------------------------------------------------------------- 奶牛

def _ellipsoid(bm, center, radii, rot=None, segments=24, rings=12):
    m = Matrix.Translation(center) @ (rot or Matrix.Identity(4)) @ Matrix.Diagonal((*radii, 1))
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=1.0, matrix=m)


def _limb(bm, p0, p1, r0, r1, segments=16, round_ends=True):
    """从 p0 到 p1 的锥台，两端可加球形圆头。"""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=r0, radius2=r1, depth=d.length,
                          matrix=Matrix.Translation((p0 + p1) / 2) @ rot)
    if round_ends:
        for p, r in ((p0, r0), (p1, r1)):
            bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=8, radius=r, matrix=Matrix.Translation(p))


def _head_frame(pose):
    """头部坐标系：side 指向牛的左右，face 从头顶指向鼻尖，brow 是额头朝向。"""
    poll = Vector(pose["poll"])
    face = Vector(pose["face"]).normalized()
    side = Vector((1.0, 0.0, 0.0))
    brow = side.cross(face)
    rot = Matrix((side, face, brow)).transposed().to_4x4()
    return poll, face, side, brow, rot


def _horn_tip_dir(side, brow, face, sx):
    return (side * sx * 0.7 + brow * 0.5 - face * 0.3).normalized()


def _cow_body(pose):
    """体素重构用的源形体：躯干、胸、臀、四肢、乳房、脖子和头（互相穿插，重构后连成一体）。"""
    bm = bmesh.new()
    e = _ellipsoid
    e(bm, (0, 0, 0.84), (0.3, 0.62, 0.3))          # 躯干
    e(bm, (0, 0.02, 0.74), (0.31, 0.46, 0.28))     # 肚子
    e(bm, (0, 0.42, 0.88), (0.26, 0.24, 0.3))      # 胸
    e(bm, (0, 0.36, 1.06), (0.16, 0.22, 0.1))      # 鬐甲
    e(bm, (0, -0.45, 0.91), (0.26, 0.28, 0.25))    # 臀
    e(bm, UDDER[0], UDDER[1])                      # 乳房
    for sx in (-1, 1):
        x = sx * 0.16
        e(bm, (sx * 0.18, -0.4, 1.02), (0.07, 0.08, 0.06))    # 腰角
        e(bm, (sx * 0.08, -0.68, 1.02), (0.05, 0.05, 0.05))   # 坐骨
        _limb(bm, (x, 0.4, 0.7), (x, 0.42, 0.3), 0.1, 0.068)         # 前腿上段
        _limb(bm, (x, 0.42, 0.3), (x, 0.42, 0.06), 0.064, 0.056)     # 前腿下段
        e(bm, (x, -0.44, 0.7), (0.11, 0.18, 0.24))                   # 后腿大腿
        _limb(bm, (x, -0.47, 0.58), (x, -0.55, 0.32), 0.09, 0.06)    # 小腿
        _limb(bm, (x, -0.55, 0.32), (x, -0.5, 0.06), 0.058, 0.054)   # 跗关节以下
        for y in (0.42, -0.5):
            _limb(bm, (x, y, 0.0), (x, y, 0.08), 0.066, 0.06, round_ends=False)  # 蹄

    poll, face, side, brow, rot = _head_frame(pose)
    _limb(bm, (0, 0.45, 0.94), poll + face * 0.06 - brow * 0.03, 0.22, 0.14)  # 脖子
    e(bm, poll + face * 0.15 - brow * 0.02, (0.125, 0.18, 0.13), rot)         # 头骨
    e(bm, poll + face * 0.36, (0.115, 0.1, 0.105), rot)                       # 口鼻
    return bm


def _cow_extras(pose):
    """不参与体素重构的细小部件：耳朵、角、尾巴。"""
    bm = bmesh.new()
    poll, face, side, brow, rot = _head_frame(pose)
    for sx in (-1, 1):
        droop = Matrix.Rotation(sx * 0.35, 4, face)
        c = poll + face * 0.08 - brow * 0.03 + side * (sx * 0.17)
        _ellipsoid(bm, c, (0.1, 0.035, 0.06), droop @ rot, segments=8, rings=4)              # 耳朵
        base = poll + side * (sx * 0.075) + brow * 0.02
        _limb(bm, base, base + _horn_tip_dir(side, brow, face, sx) * 0.1,
              0.026, 0.006, segments=6, round_ends=False)                                       # 角
    _limb(bm, (0, -0.7, 1.04), (0, -0.77, 0.46), 0.03, 0.022, segments=6, round_ends=False)   # 尾巴
    _ellipsoid(bm, (0, -0.775, 0.4), (0.045, 0.045, 0.09), segments=8, rings=4)               # 尾梢
    return bm


def _bm_object(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _apply_modifiers(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)


def _tri_count(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def build_cow(name, pose):
    ob = _bm_object(name, _cow_body(pose))
    rm = ob.modifiers.new("Remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = COW_VOXEL
    sm = ob.modifiers.new("Smooth", "SMOOTH")
    sm.factor = 0.5
    sm.iterations = 3
    _apply_modifiers(ob)
    dec = ob.modifiers.new("Decimate", "DECIMATE")
    dec.decimate_type = "COLLAPSE"
    dec.ratio = COW_BODY_TRIS / _tri_count(ob.data)
    dec.use_collapse_triangulate = True
    _apply_modifiers(ob)

    extras = _bm_object(name + "_extras", _cow_extras(pose))
    with bpy.context.temp_override(active_object=ob, object=ob, selected_objects=[ob, extras],
                                   selected_editable_objects=[ob, extras]):
        bpy.ops.object.join()
    ob.data.name = name
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def _unwrap(ob, u_offset):
    """展 UV 后压进图集的左半或右半。"""
    view_layer = bpy.context.view_layer
    for o in view_layer.objects:
        o.select_set(o == ob)
    view_layer.objects.active = ob
    with bpy.context.temp_override(active_object=ob, object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.02)
        bpy.ops.uv.pack_islands(rotate=True, margin=0.02)
        bpy.ops.object.mode_set(mode="OBJECT")
    uv = ob.data.uv_layers.active.data
    co = [0.0] * (2 * len(uv))
    uv.foreach_get("uv", co)
    co[0::2] = [u_offset + u * 0.5 for u in co[0::2]]
    uv.foreach_set("uv", co)


class _Nodes:
    """搭程序化材质节点的小工具。"""

    def __init__(self, mat):
        if mat.node_tree is None:
            mat.use_nodes = True
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.links = self.nt.links

    def new(self, kind, **props):
        n = self.nt.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def math(self, op, a, b):
        n = self.new("ShaderNodeMath", operation=op)
        self._feed(n.inputs[0], a)
        self._feed(n.inputs[1], b)
        return n.outputs[0]

    def vmath(self, op, a, b=None):
        n = self.new("ShaderNodeVectorMath", operation=op)
        self._feed(n.inputs[0], a)
        if b is not None:
            self._feed(n.inputs[1], b)
        return n.outputs["Value"] if op in ("DISTANCE", "LENGTH", "DOT_PRODUCT") else n.outputs["Vector"]

    def soft_below(self, value, edge, width=0.012):
        """value < edge 时为 1，边缘按 smoothstep 过渡。"""
        n = self.new("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
        self._feed(n.inputs["Value"], value)
        n.inputs["From Min"].default_value = edge - width
        n.inputs["From Max"].default_value = edge + width
        n.inputs["To Min"].default_value = 1.0
        n.inputs["To Max"].default_value = 0.0
        return n.outputs["Result"]

    def mix(self, factor, a, b):
        n = self.new("ShaderNodeMix", data_type="RGBA")
        self._feed(next(s for s in n.inputs if s.name == "Factor" and s.type == "VALUE"), factor)
        self._feed(next(s for s in n.inputs if s.name == "A" and s.type == "RGBA"), a)
        self._feed(next(s for s in n.inputs if s.name == "B" and s.type == "RGBA"), b)
        return next(s for s in n.outputs if s.type == "RGBA")

    def _feed(self, socket, value):
        if hasattr(value, "is_output"):
            self.links.new(value, socket)
        elif socket.type == "RGBA":
            socket.default_value = (*value, 1.0)
        else:
            socket.default_value = value


def cow_bake_material(name, pose, image):
    """按物体坐标给奶牛上色：花斑噪声 + 头、腿、乳房、口鼻、蹄、角的区域。"""
    mat = bpy.data.materials.new(name)
    n = _Nodes(mat)
    out = n.new("ShaderNodeOutputMaterial")
    bsdf = n.new("ShaderNodeBsdfPrincipled")
    n.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    coord = n.new("ShaderNodeTexCoord").outputs["Object"]
    sep = n.new("ShaderNodeSeparateXYZ")
    n.links.new(coord, sep.inputs[0])
    z = sep.outputs["Z"]

    noise = n.new("ShaderNodeTexNoise", noise_dimensions="4D")
    n.links.new(n.vmath("MULTIPLY", coord, (1.0, 0.85, 1.0)), noise.inputs["Vector"])
    noise.inputs["W"].default_value = pose["patch_seed"]
    noise.inputs["Scale"].default_value = 2.3
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.45
    noise.inputs["Distortion"].default_value = 0.35
    patch = n.math("SUBTRACT", 1.0, n.soft_below(noise.outputs["Fac"], 0.53, 0.01))

    poll, face, side, brow, _ = _head_frame(pose)

    def near(p, r, w=0.012):
        return n.soft_below(n.vmath("DISTANCE", coord, tuple(p)), r, w)

    head = near(poll + face * 0.2, 0.3)
    not_head = n.math("SUBTRACT", 1.0, head)
    legs = n.math("MULTIPLY", n.soft_below(z, 0.3), not_head)
    udder_local = n.vmath("MULTIPLY", n.vmath("SUBTRACT", coord, UDDER[0]), tuple(1 / (r + 0.02) for r in UDDER[1]))
    udder = n.soft_below(n.vmath("LENGTH", udder_local), 1.0, 0.08)
    nose = near(poll + face * 0.44, 0.1)
    hoof = n.math("MULTIPLY", n.soft_below(z, 0.085, 0.006), not_head)
    horns = n.math("MAXIMUM", *(near(poll + side * (sx * 0.075) + brow * 0.02
                                     + _horn_tip_dir(side, brow, face, sx) * 0.065, 0.045) for sx in (-1, 1)))

    c = n.mix(patch, COW_WHITE, COW_BLACK)
    c = n.mix(head, c, COW_BLACK if pose["black_head"] else COW_WHITE)
    c = n.mix(legs, c, COW_WHITE)
    c = n.mix(udder, c, COW_PINK)
    c = n.mix(nose, c, COW_NOSE)
    c = n.mix(hoof, c, COW_HOOF)
    c = n.mix(horns, c, COW_HORN)
    n.links.new(c, bsdf.inputs["Base Color"])

    target = n.new("ShaderNodeTexImage", name="BakeTarget", image=image)
    for node in n.nt.nodes:
        node.select = False
    target.select = True
    n.nt.nodes.active = target
    return mat


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


def _new_image(name, non_color):
    img = bpy.data.images.new(name, *COW_TEX_SIZE, alpha=False)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


def bake_cows(cows):
    """两头牛一起烘焙到同一张图集：先颜色，再 AO（临时地面参与遮蔽，不导出）。"""
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    device = _use_gpu(scn)
    scn.render.bake.target = "IMAGE_TEXTURES"
    if scn.world is None:
        scn.world = bpy.data.worlds.new("World")
    scn.world.light_settings.distance = AO_DISTANCE

    ground = _bm_object("BakeGround", bmesh.new())
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=20.0)
    bm.to_mesh(ground.data)
    bm.free()

    albedo = _new_image("cow_albedo", False)
    ao = _new_image("cow_ao", True)
    materials = []
    for i, (ob, pose) in enumerate(cows):
        _unwrap(ob, 0.5 * i)
        mat = cow_bake_material(ob.name + "_bake", pose, albedo)
        ob.data.materials.clear()
        ob.data.materials.append(mat)
        materials.append(mat)

    obs = [ob for ob, _ in cows]
    for o in bpy.context.view_layer.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[0]
    with bpy.context.temp_override(active_object=obs[0], object=obs[0], selected_objects=obs,
                                   selected_editable_objects=obs):
        scn.cycles.samples = COLOR_SAMPLES
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, margin=4, use_clear=True)
        for m in materials:
            m.node_tree.nodes["BakeTarget"].image = ao
        scn.cycles.samples = AO_SAMPLES
        bpy.ops.object.bake(type="AO", margin=4, use_clear=True)

    os.makedirs(TEX_DIR, exist_ok=True)
    for img in (albedo, ao):
        img.filepath_raw = os.path.join(TEX_DIR, img.name + ".png")
        img.file_format = "PNG"
        img.save()
    bpy.data.objects.remove(ground, do_unlink=True)
    for m in materials:
        bpy.data.materials.remove(m)
    return albedo, ao, device


def cow_material(albedo, ao):
    """导出用的奶牛材质：Blender 里预览颜色 × AO；导出时不带贴图，Godot 按材质名换成 cow.tres。"""
    mat = bpy.data.materials.new("farm_cow")
    n = _Nodes(mat)
    out = n.new("ShaderNodeOutputMaterial")
    bsdf = n.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.8
    t_albedo = n.new("ShaderNodeTexImage", image=albedo)
    t_ao = n.new("ShaderNodeTexImage", image=ao)
    n.links.new(n.vmath("MULTIPLY", t_albedo.outputs["Color"], t_ao.outputs["Color"]), bsdf.inputs["Base Color"])
    n.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def props_material():
    """菜畦和围栏：顶点色作反照率。"""
    mat = bpy.data.materials.new("farm_props")
    n = _Nodes(mat)
    out = n.new("ShaderNodeOutputMaterial")
    bsdf = n.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.9
    attr = n.new("ShaderNodeVertexColor", layer_name="Col")
    n.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    n.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def main():
    random.seed(5)
    os.makedirs(OUT_DIR, exist_ok=True)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)
    scn = bpy.context.scene
    scn.name = "Farm"

    props = props_material()
    objects = []
    for builder, loc in ((farm_plot(), (0, 0, 0)), (pasture_fence(), (0, 6, 0))):
        mesh = builder.finish(props)
        ob = bpy.data.objects.new(mesh.name, mesh)
        ob.location = loc
        scn.collection.objects.link(ob)
        objects.append(ob)

    cows = []
    for i, (name, pose) in enumerate(COW_POSES.items()):
        ob = build_cow(name, pose)
        ob.location = (10 + 3 * i, 0, 0)
        cows.append((ob, pose))
    albedo, ao, device = bake_cows(cows)
    mat = cow_material(albedo, ao)
    for ob, _ in cows:
        ob.data.materials.clear()
        ob.data.materials.append(mat)
        objects.append(ob)

    bpy.context.view_layer.update()
    for ob in bpy.context.view_layer.objects:
        ob.select_set(ob in objects)
    bpy.context.view_layer.objects.active = objects[0]
    options = dict(filepath=os.path.join(OUT_DIR, "farm.glb"), export_format="GLB", use_selection=True,
                   export_apply=True, export_yup=True, export_materials="EXPORT", export_image_format="NONE",
                   export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(**options, export_vertex_color="ACTIVE")
    except TypeError:
        bpy.ops.export_scene.gltf(**options, export_colors=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(PROJECT, "blender", "farm.blend"))
    print("FARM", device, {ob.name: _tri_count(ob.data) for ob in objects})


if __name__ == "__main__":
    main()
