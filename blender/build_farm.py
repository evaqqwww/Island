"""生成农田和牧场的道具：菜畦（种卷心菜）、牧场围栏（带门架）、奶牛（站立、低头吃草两种姿势）。

用法（后台运行，不影响正在打开的 Blender）：
    blender -b --factory-startup -P blender/build_farm.py
输出：
    assets/farm/farm.glb   网格 FarmPlot / PastureFence / Cow_Stand / Cow_Graze，材质 farm_props
    blender/farm.blend     以上内容的 Blender 源文件
颜色全部写在顶点色 Col 里（线性空间），并按离地高度做简单的遮蔽压暗（ao_height 以下逐渐变暗）；Godot 直接用顶点色作反照率。
面数按当前相机（45～70 米、手机竖屏）来定：一头牛约 170 个三角形，一块菜畦约 300 个，整圈围栏约 800 个。
坐标：Blender 单位为米，-Y 为正面（围栏的门所在一侧），导出到 Godot 后正面朝 +Z。
"""
import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(PROJECT, "assets", "farm")
PASTURE_SIZE = (6.5, 4.5)   # 围栏 x、y 方向的边长
GATE_WIDTH = 1.4
POST_SPACING = 1.1


def lin(c):
    return tuple((v / 255.0) ** 2.2 for v in c)


WOOD = lin((120, 88, 58))
FENCE_WOOD = lin((112, 84, 58))
SOIL = lin((104, 72, 48))
LEAF_DARK = lin((78, 138, 56))
LEAF_LIGHT = lin((176, 214, 120))
WHITE = lin((236, 232, 224))
BLACK = lin((40, 38, 38))
PINK = lin((214, 150, 150))


class MeshBuilder:
    """往同一个 bmesh 里加方块和二十面体，并按面写顶点色。"""

    def __init__(self, name, ao_height=0.8):
        self.name = name
        self.ao_height = ao_height
        self.bm = bmesh.new()
        self.col = self.bm.loops.layers.float_color.new("Col")

    def box(self, center, half, color, rot=None, cuts=0):
        before = set(self.bm.faces)
        m = Matrix.Translation(center) @ (rot or Matrix.Identity(4)) @ Matrix.Diagonal((half[0] * 2, half[1] * 2, half[2] * 2, 1))
        res = bmesh.ops.create_cube(self.bm, size=1.0, matrix=m)
        if cuts:
            edges = list({e for v in res["verts"] for e in v.link_edges})
            bmesh.ops.subdivide_edges(self.bm, edges=edges, cuts=cuts, use_grid_fill=True)
        self._paint(set(self.bm.faces) - before, color)

    def ico(self, center, radius, scale, color):
        before = set(self.bm.faces)
        bmesh.ops.create_icosphere(self.bm, subdivisions=1, radius=radius,
                                   matrix=Matrix.Translation(center) @ Matrix.Diagonal((*scale, 1)))
        self._paint(set(self.bm.faces) - before, color)

    def _paint(self, faces, color):
        for f in faces:
            c = color(f) if callable(color) else color
            j = random.uniform(0.94, 1.06)
            for loop in f.loops:
                occ = 0.62 + 0.38 * min(1.0, max(0.0, loop.vert.co.z / self.ao_height))
                loop[self.col] = (c[0] * j * occ, c[1] * j * occ, c[2] * j * occ, 1.0)

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
    runs = [
        [Vector((-gate, -hd, 0)), Vector((-hw, -hd, 0)), Vector((-hw, hd, 0)), Vector((hw, hd, 0)),
         Vector((hw, -hd, 0)), Vector((gate, -hd, 0))],
    ]
    for run in runs:
        posts = []
        for p0, p1 in zip(run, run[1:]):
            n = max(1, math.ceil((p1 - p0).length / POST_SPACING))
            posts += [p0.lerp(p1, k / n) for k in range(n)]
        posts.append(run[-1])
        for i, p in enumerate(posts):
            if i in (0, len(posts) - 1):
                continue
            b.box(p + Vector((0, 0, 0.45)), (0.05, 0.05, 0.45), FENCE_WOOD)
        for p0, p1 in zip(posts, posts[1:]):
            d = p1 - p0
            yaw = math.atan2(d.y, d.x)
            rot = Matrix.Rotation(yaw, 4, "Z")
            for z in (0.42, 0.78):
                b.box((p0 + p1) / 2 + Vector((0, 0, z)), (d.length / 2 + 0.03, 0.025, 0.04), FENCE_WOOD, rot)
    for sx in (-1, 1):
        b.box((sx * gate, -hd, 0.875), (0.07, 0.07, 0.875), FENCE_WOOD)
    b.box((0, -hd, 1.68), (gate + 0.15, 0.06, 0.07), FENCE_WOOD)
    return b


def _patches(face):
    """奶牛身上的黑白花斑：按面中心所在的格子取伪随机值。"""
    c = face.calc_center_median()
    h = math.sin(math.floor(c.x * 4 + 7) * 12.9898 + math.floor(c.y * 3.2 + 3) * 78.233 + math.floor(c.z * 4) * 37.719) * 43758.5453
    return BLACK if h - math.floor(h) < 0.4 else WHITE


def cow(name, grazing):
    """奶牛：身体朝 +Y，身长约 1.6 米；grazing 时低头吃草。"""
    b = MeshBuilder(name)
    b.box((0, 0, 0.95), (0.3, 0.72, 0.28), _patches, cuts=1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.box((sx * 0.2, sy * 0.52, 0.34), (0.065, 0.065, 0.34), WHITE)
    b.box((0, -0.45, 0.62), (0.12, 0.1, 0.06), PINK)
    b.box((0, -0.76, 0.82), (0.025, 0.025, 0.25), WHITE, Matrix.Rotation(-0.25, 4, "X"))
    if grazing:
        head, muzzle, ear_z, pitch = Vector((0, 0.98, 0.58)), Vector((0, 1.06, 0.36)), 0.7, -0.9
    else:
        head, muzzle, ear_z, pitch = Vector((0, 0.95, 1.18)), Vector((0, 1.13, 1.08)), 1.3, 0.0
    rot = Matrix.Rotation(pitch, 4, "X")
    b.box(head, (0.15, 0.2, 0.16), lambda f: BLACK if f.calc_center_median().z > head.z + 0.1 else WHITE, rot)
    b.box(muzzle, (0.12, 0.07, 0.09), PINK, rot)
    for sx in (-1, 1):
        b.box((sx * 0.2, head.y - 0.05, ear_z), (0.07, 0.03, 0.04), BLACK)
    return b


def _material():
    mat = bpy.data.materials.get("farm_props") or bpy.data.materials.new("farm_props")
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.9
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def main():
    random.seed(5)
    os.makedirs(OUT_DIR, exist_ok=True)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    scn = bpy.context.scene
    scn.name = "Farm"
    mat = _material()
    builders = [(farm_plot(), (0, 0, 0)), (pasture_fence(), (0, 6, 0)),
                (cow("Cow_Stand", False), (5, 0, 0)), (cow("Cow_Graze", True), (7, 0, 0))]
    objects = []
    for builder, loc in builders:
        mesh = builder.finish(mat)
        ob = bpy.data.objects.new(mesh.name, mesh)
        ob.location = loc
        scn.collection.objects.link(ob)
        objects.append(ob)

    bpy.context.view_layer.update()
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    options = dict(filepath=os.path.join(OUT_DIR, "farm.glb"), export_format="GLB", use_selection=True,
                   export_apply=True, export_yup=True, export_materials="EXPORT", export_image_format="NONE",
                   export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(**options, export_vertex_color="ACTIVE")
    except TypeError:
        bpy.ops.export_scene.gltf(**options, export_colors=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(PROJECT, "blender", "farm.blend"))
    print("FARM", {ob.name: sum(len(p.vertices) - 2 for p in ob.data.polygons) for ob in objects})


if __name__ == "__main__":
    main()
