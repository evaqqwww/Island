"""生成树木和草坪：程序化贴图 + 树木模型，导出给 Godot。

用法（后台运行，不影响正在打开的 Blender）：
    blender -b --factory-startup -P blender/build_trees.py
输出：
    assets/textures/leaf_atlas.png  叶片图集：2×2 四种叶形（卵形、圆叶、窄叶、三叶簇），接近白色，
                                    颜色在 Godot 里按每棵树着色
    assets/textures/lawn.png        可平铺的草坪纹理
    assets/trees/trees.glb          树木网格：Tree_A/B/C（近景）和 Tree_A/B/C_Far（远景，叶片更少更大）
    blender/trees.blend             以上内容的 Blender 源文件，引用两张贴图
树冠是一个整体：每个球团里有实心内核（20 面的二十面体，取叶片贴图上一块不透明的叶面颜色，偏暗），
外面包两层叶片面片，叶片之间的缝隙露出的是同色的内核，不会透出背后的地面。
法线朝树冠中心外侧（球形化），受光柔和。藏在树冠里的部分（内核细节、枝杈）不建或只用最少的面。
顶点色 Col：RGB 是每片叶子的细微色差，A 是按高度和树冠内外深度算出的遮蔽。
材质 tree_leaves / tree_bark 只导出名称，Godot 按名称替换成自己的材质。
"""
import math
import os
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEX_DIR = os.path.join(PROJECT, "assets", "textures")
TREE_DIR = os.path.join(PROJECT, "assets", "trees")


# ---------- 程序化贴图 ----------

def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _leaf(x, y, angle, length, width, ox, oy, aa):
    """单片叶子。x 为 -0.5..0.5，y 为 0..1（叶柄朝下）。返回 (alpha, shade)。"""
    c, s = math.cos(angle), math.sin(angle)
    lx = (x - ox) * c - (y - oy) * s
    ly = (x - ox) * s + (y - oy) * c
    t = ly / length
    tc = np.clip(t, 0.0, 1.0)
    prof = np.where((t > 0.0) & (t < 1.0), np.sin(np.pi * tc ** 0.75) ** 0.9, 0.0) * width
    inside = np.where(prof > 0.0, prof - np.abs(lx), -1.0)
    alpha = _smoothstep(-aa, aa, inside)
    stem = ((ly > -0.05) & (ly < length * 0.12) & (np.abs(lx) < 0.016)).astype(float)
    alpha = np.maximum(alpha, stem)
    shade = 0.86 + 0.14 * tc
    shade = shade * np.where((np.abs(lx) < 0.009 + 0.006 * (1.0 - tc)) & (inside > 0.0), 0.9, 1.0)
    vein = np.mod((tc - np.abs(lx) / max(width, 1e-3) * 0.35) * 6.0, 1.0) < 0.08
    shade = shade * np.where(vein & (inside > 0.03), 0.93, 1.0)
    shade = shade * (0.8 + 0.2 * _smoothstep(0.0, 0.06, inside))
    return alpha, shade


def _combine(layers):
    alpha = np.zeros_like(layers[0][0])
    shade = np.ones_like(layers[0][1])
    for a, s in layers:
        shade = np.where(a > alpha, s, shade)
        alpha = np.maximum(alpha, a)
    return alpha, shade


def leaf_atlas(size=512):
    cell = size // 2
    ys, xs = np.mgrid[0:cell, 0:cell].astype(float)
    x = (xs + 0.5) / cell - 0.5
    y = (ys + 0.5) / cell
    aa = 1.5 / cell
    cells = [
        _combine([_leaf(x, y, 0.0, 0.92, 0.36, 0.0, 0.04, aa)]),
        _combine([_leaf(x, y, 0.0, 0.84, 0.44, 0.0, 0.08, aa)]),
        _combine([_leaf(x, y, 0.0, 0.95, 0.24, 0.0, 0.03, aa)]),
        _combine([_leaf(x, y, -0.5, 0.7, 0.2, 0.0, 0.05, aa), _leaf(x, y, 0.5, 0.7, 0.2, 0.0, 0.05, aa),
                  _leaf(x, y, 0.0, 0.86, 0.24, 0.0, 0.05, aa)]),
    ]
    tints = [(1.0, 0.99, 0.96), (0.98, 1.0, 0.95), (1.0, 0.97, 0.95), (0.97, 0.99, 0.97)]
    out = np.zeros((size, size, 4))
    for i, (alpha, shade) in enumerate(cells):
        cx, cy = i % 2, i // 2
        rgb = np.stack([shade * t * 0.96 for t in tints[i]], axis=-1)
        fill = np.array(tints[i]) * 0.9   # 透明处填叶色，避免 mipmap 出黑边
        rgb = np.where(alpha[..., None] > 0.01, rgb, fill)
        out[cy * cell:(cy + 1) * cell, cx * cell:(cx + 1) * cell, :3] = rgb
        out[cy * cell:(cy + 1) * cell, cx * cell:(cx + 1) * cell, 3] = alpha
    return out


def _tile_noise(size, cx, cy, rng):
    g = rng.random((cy, cx))
    xs = np.arange(size) * cx / size
    ys = np.arange(size) * cy / size
    x0 = np.floor(xs).astype(int)
    y0 = np.floor(ys).astype(int)
    fx = xs - x0
    fy = ys - y0
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    x1 = (x0 + 1) % cx
    y1 = (y0 + 1) % cy
    x0 %= cx
    y0 %= cy
    a, b = g[np.ix_(y0, x0)], g[np.ix_(y0, x1)]
    c, d = g[np.ix_(y1, x0)], g[np.ix_(y1, x1)]
    FX, FY = fx[None, :], fy[:, None]
    return (a * (1 - FX) + b * FX) * (1 - FY) + (c * (1 - FX) + d * FX) * FY


def _fbm(size, base, octaves, rng):
    total = np.zeros((size, size))
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        cells = base * 2 ** o
        total += amp * _tile_noise(size, cells, cells, rng)
        norm += amp
        amp *= 0.5
    return total / norm


def lawn(size=1024, seed=3):
    rng = np.random.default_rng(seed)
    macro = _fbm(size, 4, 4, rng)
    mid = _fbm(size, 32, 3, rng)
    speckle = _fbm(size, 128, 3, rng)
    v = 0.5 * macro + 0.3 * mid + 0.2 * speckle
    lo, hi = np.percentile(v, 2), np.percentile(v, 98)
    v = np.clip((v - lo) / (hi - lo), 0.0, 1.0)
    dark, base, light = np.array([0.42, 0.6, 0.2]), np.array([0.53, 0.71, 0.26]), np.array([0.64, 0.79, 0.32])
    rgb = np.where(v[..., None] < 0.5, dark + (base - dark) * (v[..., None] / 0.5),
                   base + (light - base) * ((v[..., None] - 0.5) / 0.5))
    out = np.ones((size, size, 4))
    out[..., :3] = rgb
    return out


def save_image(name, pixels, path):
    h, w = pixels.shape[:2]
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels.foreach_set(pixels.astype(np.float32).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return img


# ---------- 树木 ----------

# (树冠球团 [(中心, 半径)], 树干控制点)
VARIANTS = {
    "A": ([((0.0, 0.0, 2.7), 1.5), ((0.9, 0.3, 2.4), 0.95), ((-0.8, -0.4, 2.5), 1.0), ((0.1, -0.2, 3.6), 0.95)],
          [(0.0, 0.0, 0.0), (0.15, 0.05, 1.0), (0.05, -0.05, 2.1)]),
    "B": ([((-0.6, 0.0, 2.5), 1.25), ((0.75, 0.25, 2.8), 1.3), ((0.0, -0.35, 3.5), 1.0), ((0.2, 0.6, 2.2), 0.8)],
          [(0.0, 0.0, 0.0), (-0.2, 0.1, 1.0), (0.1, 0.0, 2.0)]),
    "C": ([((0.0, 0.0, 2.4), 1.15), ((0.1, 0.1, 3.3), 1.1), ((0.25, 0.0, 4.1), 0.85), ((-0.5, 0.2, 2.9), 0.75)],
          [(0.0, 0.0, 0.0), (0.1, -0.1, 1.0), (0.0, 0.05, 2.0)]),
}
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))
CELLS = [(0, 0), (1, 0), (0, 1), (1, 1)]
# 圆叶格子里一块不透明、避开叶脉的叶面，内核整体取这里的颜色
CORE_UV = (0.81, 0.25)


def _bezier(p0, p1, p2, n):
    return [p0 * (1 - t) ** 2 + p1 * 2 * (1 - t) * t + p2 * t ** 2 for t in (i / (n - 1) for i in range(n))]


def _tube(bm, uv, col, pts, radii, sides):
    rings = []
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        ref = Vector((1, 0, 0)) if abs(t.x) < 0.9 else Vector((0, 1, 0))
        a = (ref - t * ref.dot(t)).normalized()
        b = t.cross(a)
        rings.append([bm.verts.new(p + (a * math.cos(k * math.tau / sides) + b * math.sin(k * math.tau / sides)) * radii[i])
                      for k in range(sides)])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            faces.append(bm.faces.new((r0[k], r0[(k + 1) % sides], r1[(k + 1) % sides], r1[k])))
    faces.append(bm.faces.new(rings[-1]))
    for f in faces:
        f.material_index = 1
        for loop in f.loops:
            loop[uv].uv = (0.0, 0.0)
            loop[col] = (1.0, 1.0, 1.0, 1.0)


def _card(bm, uv, col, center, normal, tip, size, cell, rgba):
    n = normal.normalized()
    t = (tip - n * tip.dot(n)).normalized()
    s = t.cross(n)
    h = size * 0.5
    corners = (center - s * h - t * h, center + s * h - t * h, center + s * h + t * h, center - s * h + t * h)
    f = bm.faces.new([bm.verts.new(p) for p in corners])
    f.material_index = 0
    cx, cy = cell
    for loop, (u, v) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uv].uv = ((cx + u) * 0.5, (cy + v) * 0.5)
        loop[col] = rgba


def _core(bm, uv, col, center, radius, zmin, zmax, rng):
    """树冠球团的实心内核，和叶片同一个材质槽。几乎全被叶片盖住，用二十面体就够。"""
    res = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=radius, matrix=Matrix.Translation(center))
    shade = {v: rng.uniform(0.92, 1.0) for v in res["verts"]}
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = 0
        for loop in f.loops:
            h = (loop.vert.co.z - zmin) / max(zmax - zmin, 0.01)
            j = shade[loop.vert]
            loop[uv].uv = CORE_UV
            loop[col] = (j, j, j, 0.45 + 0.35 * h)


def build_tree(name, lumps, trunk, leaf_size, coverage, trunk_sides, trunk_points, rng):
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    col = bm.loops.layers.float_color.new("Col")
    lumps = [(Vector(c), r) for c, r in lumps]
    zmin = min(c.z - r for c, r in lumps)
    zmax = max(c.z + r for c, r in lumps)
    canopy_center = sum((c for c, _ in lumps), Vector()) / len(lumps)

    for li, (center, r) in enumerate(lumps):
        n_outer = int(4 * math.pi * r * r / (leaf_size * leaf_size) * coverage)
        n_inner = int(n_outer * 0.25)
        for i in range(n_outer + n_inner):
            inner = i >= n_outer
            k, n = (i - n_outer, n_inner) if inner else (i, n_outer)
            z = 1 - 2 * (k + 0.5) / n
            if z < -0.5 and rng.random() < 0.5:
                continue
            rxy = math.sqrt(max(0.0, 1 - z * z))
            phi = k * GOLDEN + rng.uniform(-0.2, 0.2) + (1.3 if inner else 0.0)
            d = Vector((rxy * math.cos(phi), rxy * math.sin(phi), z))
            depth = rng.uniform(0.62, 0.8) if inner else rng.uniform(0.86, 1.04)
            p = center + d * r * depth
            if any((p - c2).length < r2 * 0.9 for j, (c2, r2) in enumerate(lumps) if j != li):
                continue
            normal = d + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * 0.35
            tip = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) + Vector((0, 0, -0.4))
            h = (p.z - zmin) / max(zmax - zmin, 0.01)
            occlusion = (0.5 + 0.5 * h) * (0.75 + 0.25 * max(0.0, min(1.0, (depth - 0.8) / 0.24))) * (0.8 if z < -0.3 else 1.0)
            jitter = rng.uniform(0.9, 1.05)
            rgba = (jitter * rng.uniform(0.96, 1.02), jitter * rng.uniform(0.96, 1.02), jitter * rng.uniform(0.96, 1.02),
                    max(0.3, min(1.0, occlusion)))
            _card(bm, uv, col, p, normal, tip, leaf_size * rng.uniform(0.85, 1.2), CELLS[rng.randrange(4)], rgba)
        _core(bm, uv, col, center, r * 0.88, zmin, zmax, rng)

    pts = _bezier(*(Vector(p) for p in trunk), trunk_points)
    radii = [0.3 - 0.19 * (i / (trunk_points - 1)) ** 0.5 for i in range(trunk_points)]
    _tube(bm, uv, col, pts, radii, trunk_sides)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    attrs = mesh.color_attributes
    attrs.active_color = attrs["Col"]
    attrs.render_color_index = [a.name for a in attrs].index("Col")

    # 叶片法线球形化：朝树冠中心外侧，和面片自身朝向略作混合
    normals = [tuple(cn.vector) for cn in mesh.corner_normals]
    for poly in mesh.polygons:
        if poly.material_index != 0:
            continue
        for li in poly.loop_indices:
            p = mesh.vertices[mesh.loops[li].vertex_index].co
            n = (p - canopy_center).normalized() * 0.8 + Vector(normals[li]) * 0.2
            normals[li] = tuple(n.normalized())
    mesh.normals_split_custom_set(normals)
    return mesh


def _materials(atlas):
    leaves = bpy.data.materials.get("tree_leaves") or bpy.data.materials.new("tree_leaves")
    try:
        leaves.use_nodes = True
    except Exception:
        pass
    nt = leaves.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = atlas
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    tint = nt.nodes.new("ShaderNodeRGB")
    tint.outputs[0].default_value = (0.75, 0.82, 0.55, 1.0)
    mul1 = nt.nodes.new("ShaderNodeVectorMath")
    mul1.operation = "MULTIPLY"
    mul2 = nt.nodes.new("ShaderNodeVectorMath")
    mul2.operation = "MULTIPLY"
    nt.links.new(tex.outputs["Color"], mul1.inputs[0])
    nt.links.new(vc.outputs["Color"], mul1.inputs[1])
    nt.links.new(mul1.outputs["Vector"], mul2.inputs[0])
    nt.links.new(tint.outputs[0], mul2.inputs[1])
    nt.links.new(mul2.outputs["Vector"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    for attr, value in (("blend_method", "CLIP"), ("surface_render_method", "DITHERED")):
        try:
            setattr(leaves, attr, value)
        except (AttributeError, TypeError):
            pass

    bark = bpy.data.materials.get("tree_bark") or bpy.data.materials.new("tree_bark")
    try:
        bark.use_nodes = True
    except Exception:
        pass
    bsdf = next(n for n in bark.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.13, 0.065, 0.03, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    return leaves, bark


def main():
    os.makedirs(TEX_DIR, exist_ok=True)
    os.makedirs(TREE_DIR, exist_ok=True)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)

    atlas = save_image("leaf_atlas", leaf_atlas(), os.path.join(TEX_DIR, "leaf_atlas.png"))
    save_image("lawn", lawn(), os.path.join(TEX_DIR, "lawn.png"))
    leaves, bark = _materials(atlas)

    scn = bpy.context.scene
    scn.name = "Trees"
    rng = random.Random(11)
    objects = []
    for i, (key, (lumps, trunk)) in enumerate(VARIANTS.items()):
        for suffix, leaf_size, coverage, sides, points, row in (("", 0.55, 1.8, 5, 4, 0.0),
                                                                ("_Far", 0.9, 1.0, 4, 3, 6.0)):
            mesh = build_tree(f"Tree_{key}{suffix}", lumps, trunk, leaf_size, coverage, sides, points, rng)
            mesh.materials.append(leaves)
            mesh.materials.append(bark)
            ob = bpy.data.objects.new(mesh.name, mesh)
            ob.location = (i * 5.0, row, 0.0)
            scn.collection.objects.link(ob)
            objects.append(ob)

    view_layer = bpy.context.view_layer
    view_layer.update()
    for ob in objects:
        ob.select_set(True)
    view_layer.objects.active = objects[0]
    options = dict(filepath=os.path.join(TREE_DIR, "trees.glb"), export_format="GLB", use_selection=True,
                   export_apply=True, export_yup=True, export_materials="EXPORT", export_image_format="NONE",
                   export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(**options, export_vertex_color="ACTIVE")
    except TypeError:
        bpy.ops.export_scene.gltf(**options, export_colors=True)

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(PROJECT, "blender", "trees.blend"), relative_remap=True)
    stats = {ob.name: len(ob.data.polygons) for ob in objects}
    print("TREES", stats)


if __name__ == "__main__":
    main()
