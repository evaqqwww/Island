"""生成占位木屋：高模 + 低模 + 程序化制作材质。

Cabin 场景里有三个集合，由 bake_cabin.py 处理：
    CabinParts   高模，只作烘焙源：墙、屋顶瓦片、木构、烟囱、门窗、老虎窗花箱、灯柱、壁灯、栅栏、藤蔓，
                 材质用程序化节点做细节（木板缝、瓦片和叶片色差、石缝、边缘高光）。
    CabinLow     导出用的低模（约一千个三角形）：贴在墙上的木构、门窗、藤蔓都不建几何，
                 屋顶是两块屋面板。高模的颜色烘焙到低模的贴图上。
    CabinFoliage 墙根花丛（实心内核 + 少量叶片 + 小花），烘焙到顶点色（RGB 颜色，A 为 AO）。
                 UV 图层 "Wind" 存摆动数据：U 为摆动权重，V 为随机相位。
面数按当前相机（45～70 米、手机竖屏）下木屋只有几十到一百多像素来定。

坐标：Blender 单位为米，-Y 为正面（门所在的山墙），导出到 Godot 后正面朝 +Z。
"""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

HW, HD = 1.5, 2.0                    # 墙体半宽（x）、半深（y）
BASE, EAVE, RIDGE = 0.35, 3.15, 5.75  # 地基顶、檐口、屋脊高度
DORMER_Y = -0.35                     # 老虎窗中心 y


# ---------- 制作材质 ----------

def _lin(h, a=1.0):
    return [(c / 255.0) ** 2.2 for c in h] + [a]


def _gray(v):
    return (v, v, v, 1.0)


def _new_mat(name, rough=0.85):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (600, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = rough
    return m, nt, bsdf


def _node(nt, kind, x=0, y=0, **props):
    n = nt.nodes.new(kind)
    n.location = (x, y)
    for k, v in props.items():
        setattr(n, k, v)
    return n


def _ramp(nt, stops, x=0, y=0, interp="LINEAR"):
    r = _node(nt, "ShaderNodeValToRGB", x, y)
    cr = r.color_ramp
    cr.interpolation = interp
    cr.elements[0].position = stops[0][0]
    cr.elements[0].color = stops[0][1]
    cr.elements[1].position = stops[-1][0]
    cr.elements[1].color = stops[-1][1]
    for pos, col in stops[1:-1]:
        cr.elements.new(pos).color = col
    return r


def _obj_coords(nt):
    return _node(nt, "ShaderNodeTexCoord", -900, 0).outputs["Object"]


def _noise_factor(nt, coords, scale, lo, hi, detail=2.0):
    nz = _node(nt, "ShaderNodeTexNoise", -600, -300)
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = detail
    nt.links.new(coords, nz.inputs["Vector"])
    mr = _node(nt, "ShaderNodeMapRange", -400, -300)
    mr.inputs[1].default_value = 0.3
    mr.inputs[2].default_value = 0.7
    mr.inputs[3].default_value = lo
    mr.inputs[4].default_value = hi
    nt.links.new(nz.outputs["Fac"], mr.inputs[0])
    return mr.outputs["Result"]


def _scale_color(nt, color_socket, fac_socket):
    vm = _node(nt, "ShaderNodeVectorMath", 200, 0, operation="SCALE")
    nt.links.new(color_socket, vm.inputs[0])
    nt.links.new(fac_socket, vm.inputs["Scale"])
    return vm.outputs["Vector"]


def _mul(nt, a, b, x=0, y=-500):
    mm = _node(nt, "ShaderNodeMath", x, y, operation="MULTIPLY")
    nt.links.new(a, mm.inputs[0])
    nt.links.new(b, mm.inputs[1])
    return mm.outputs["Value"]


def _edge_wear(nt, fac_socket, strength=0.35):
    """凸起的棱边提亮，模仿手绘风格的边缘高光。"""
    geo = _node(nt, "ShaderNodeNewGeometry", -600, -700)
    mr = _node(nt, "ShaderNodeMapRange", -400, -700)
    mr.inputs[1].default_value = 0.5
    mr.inputs[2].default_value = 0.58
    mr.inputs[3].default_value = 1.0
    mr.inputs[4].default_value = 1.0 + strength
    nt.links.new(geo.outputs["Pointiness"], mr.inputs[0])
    return _mul(nt, fac_socket, mr.outputs["Result"], -200, -700)


def _color(nt, rgba):
    rgb = _node(nt, "ShaderNodeRGB", -200, 200)
    rgb.outputs[0].default_value = rgba
    return rgb.outputs[0]


def _planks_mat(name, base, direction, scale, seam=0.5, wear=True, wear_strength=0.35):
    m, nt, bsdf = _new_mat(name)
    co = _obj_coords(nt)
    wave = _node(nt, "ShaderNodeTexWave", -600, 0, wave_type="BANDS", bands_direction=direction, wave_profile="SAW")
    wave.inputs["Scale"].default_value = scale
    wave.inputs["Distortion"].default_value = 0.0
    nt.links.new(co, wave.inputs["Vector"])
    r = _ramp(nt, [(0.0, _gray(seam)), (0.07, _gray(1.0)), (0.85, _gray(0.96)), (1.0, _gray(0.82))], -350, 0)
    nt.links.new(wave.outputs["Fac"], r.inputs["Fac"])
    f = _mul(nt, r.outputs["Color"], _noise_factor(nt, co, 2.5, 0.85, 1.1), -100, -200)
    if wear:
        f = _edge_wear(nt, f, wear_strength)
    nt.links.new(_scale_color(nt, _color(nt, _lin(base)), f), bsdf.inputs["Base Color"])
    return m


def _mottled_mat(name, base, scale, lo, hi, wear=False, rough=0.85):
    m, nt, bsdf = _new_mat(name, rough)
    f = _noise_factor(nt, _obj_coords(nt), scale, lo, hi, 4.0)
    if wear:
        f = _edge_wear(nt, f)
    nt.links.new(_scale_color(nt, _color(nt, _lin(base)), f), bsdf.inputs["Base Color"])
    return m


def _island_mat(name, stops, lo=0.9, hi=1.05, interp="LINEAR", crevice=0.0):
    """每个独立零件（瓦片、石块、花）随机取色。
    crevice > 0 时用局部 AO 把零件之间的缝隙和边缘压暗，烘焙到低模后仍能看出一片片的瓦片。"""
    m, nt, bsdf = _new_mat(name)
    co = _obj_coords(nt)
    geo = _node(nt, "ShaderNodeNewGeometry", -800, 300)
    r = _ramp(nt, stops, -500, 300, interp)
    nt.links.new(geo.outputs["Random Per Island"], r.inputs["Fac"])
    f = _noise_factor(nt, co, 6.0, lo, hi)
    if crevice > 0.0:
        ao = _node(nt, "ShaderNodeAmbientOcclusion", -800, -600, only_local=True, samples=16)
        ao.inputs["Distance"].default_value = 0.08
        mr = _node(nt, "ShaderNodeMapRange", -600, -600)
        mr.inputs[3].default_value = 1.0 - crevice
        mr.inputs[4].default_value = 1.0
        nt.links.new(ao.outputs["AO"], mr.inputs[0])
        f = _mul(nt, f, mr.outputs["Result"], -400, -600)
    nt.links.new(_scale_color(nt, r.outputs["Color"], f), bsdf.inputs["Base Color"])
    return m


def _stone_mat(name, base):
    m, nt, bsdf = _new_mat(name)
    co = _obj_coords(nt)
    edge = _node(nt, "ShaderNodeTexVoronoi", -600, 0, feature="DISTANCE_TO_EDGE")
    edge.inputs["Scale"].default_value = 5.0
    nt.links.new(co, edge.inputs["Vector"])
    r = _ramp(nt, [(0.0, _gray(0.4)), (0.05, _gray(1.0)), (1.0, _gray(1.0))], -350, 0)
    nt.links.new(edge.outputs["Distance"], r.inputs["Fac"])
    cell = _node(nt, "ShaderNodeTexVoronoi", -600, -300, feature="F1")
    cell.inputs["Scale"].default_value = 5.0
    nt.links.new(co, cell.inputs["Vector"])
    bw = _node(nt, "ShaderNodeRGBToBW", -400, -300)
    nt.links.new(cell.outputs["Color"], bw.inputs[0])
    mr = _node(nt, "ShaderNodeMapRange", -250, -300)
    mr.inputs[3].default_value = 0.85
    mr.inputs[4].default_value = 1.12
    nt.links.new(bw.outputs[0], mr.inputs[0])
    f = _mul(nt, r.outputs["Color"], mr.outputs["Result"], -100, -200)
    nt.links.new(_scale_color(nt, _color(nt, _lin(base)), f), bsdf.inputs["Base Color"])
    return m


def _materials():
    return {
        "wall": _planks_mat("cabin_wall", (142, 153, 170), "Z", 1.6, 0.78, wear_strength=0.1),
        "timber": _mottled_mat("cabin_timber", (164, 157, 144), 7.0, 0.85, 1.08, wear=True),
        "roof": _island_mat("cabin_roof", [(0.0, _lin((108, 50, 38))), (0.45, _lin((134, 64, 46))), (0.88, _lin((148, 80, 56))),
                                            (1.0, _lin((96, 96, 58)))],
                            crevice=0.75),
        "stone": _stone_mat("cabin_stone", (150, 146, 138)),
        "chimney": _island_mat("cabin_chimney", [(0.0, _lin((146, 70, 50))), (0.5, _lin((176, 92, 64))), (1.0, _lin((128, 62, 46)))]),
        "door": _planks_mat("cabin_door", (156, 98, 56), "X", 1.9, 0.45),
        "frame": _mottled_mat("cabin_frame", (176, 169, 153), 5.0, 0.9, 1.05, wear=True),
        "glass": _mottled_mat("cabin_glass", (66, 58, 86), 2.0, 0.85, 1.15, rough=0.25),
        "flowers": _island_mat("cabin_flowers", [(0.0, _lin((150, 110, 200))), (0.35, _lin((240, 210, 90))),
                                                 (0.7, _lin((240, 236, 230))), (1.0, _lin((230, 130, 170)))],
                               0.95, 1.05, "CONSTANT"),
        "planter": _planks_mat("cabin_planter", (110, 80, 56), "Z", 4.0, 0.5, wear=False),
        "fence": _mottled_mat("cabin_fence", (84, 72, 60), 6.0, 0.8, 1.1, wear=True),
        "post": _mottled_mat("cabin_post", (78, 58, 42), 6.0, 0.82, 1.1, wear=True),
        "metal": _mottled_mat("cabin_metal", (48, 46, 50), 8.0, 0.85, 1.1, wear=True, rough=0.6),
        "lamp_glass": _mottled_mat("cabin_lamp_glass", (238, 214, 160), 3.0, 0.92, 1.05, rough=0.3),
        # 植被（烘焙到顶点色）
        "stem": _mottled_mat("cabin_stem", (70, 62, 40), 8.0, 0.85, 1.1),
        "vine_leaf": _island_mat("cabin_vine_leaf", [(0.0, _lin((52, 96, 38))), (0.5, _lin((90, 140, 56))),
                                                     (1.0, _lin((150, 182, 90)))]),
        "bush_leaf": _island_mat("cabin_bush_leaf", [(0.0, _lin((48, 96, 40))), (0.5, _lin((86, 138, 54))),
                                                     (1.0, _lin((124, 168, 72)))]),
        "bloom": _island_mat("cabin_bloom", [(0.0, _lin((240, 160, 190))), (0.3, _lin((246, 242, 236))),
                                             (0.6, _lin((186, 160, 220))), (1.0, _lin((226, 120, 170)))],
                             0.95, 1.05, "CONSTANT"),
    }


# ---------- 几何 ----------

def _add_box(bm, center, u, v, n, hu, hv, hn):
    c = Vector(center)
    u = Vector(u).normalized()
    v = Vector(v).normalized()
    n = Vector(n).normalized()
    vs = [bm.verts.new(c + u * hu * sx + v * hv * sy + n * hn * sz)
          for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]

    def V(a, b, d):
        return vs[a * 4 + b * 2 + d]

    return [bm.faces.new(f) for f in (
        (V(0, 0, 0), V(0, 1, 0), V(1, 1, 0), V(1, 0, 0)), (V(0, 0, 1), V(1, 0, 1), V(1, 1, 1), V(0, 1, 1)),
        (V(0, 0, 0), V(1, 0, 0), V(1, 0, 1), V(0, 0, 1)), (V(0, 1, 0), V(0, 1, 1), V(1, 1, 1), V(1, 1, 0)),
        (V(0, 0, 0), V(0, 0, 1), V(0, 1, 1), V(0, 1, 0)), (V(1, 0, 0), V(1, 1, 0), V(1, 1, 1), V(1, 0, 1)),
    )]


def _aabb(bm, center, half):
    return _add_box(bm, center, (1, 0, 0), (0, 1, 0), (0, 0, 1), *half)


def _beam(bm, p0, p1, side_n, w, t):
    p0 = Vector(p0)
    p1 = Vector(p1)
    d = p1 - p0
    v = d.normalized()
    n = Vector(side_n).normalized()
    return _add_box(bm, (p0 + p1) / 2, v.cross(n), v, n, w, d.length / 2, t)


def _tube(bm, pts, radii, sides=6):
    """沿折线生成管子（灯柱、横臂），两端封口。"""
    rings = []
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        ref = Vector((1, 0, 0)) if abs(t.x) < 0.9 else Vector((0, 1, 0))
        a = (ref - t * ref.dot(t)).normalized()
        b = t.cross(a)
        rings.append([bm.verts.new(p + (a * math.cos(k * math.tau / sides) + b * math.sin(k * math.tau / sides)) * radii[i])
                      for k in range(sides)])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            bm.faces.new((r0[k], r0[(k + 1) % sides], r1[(k + 1) % sides], r1[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def _bezier(p0, p1, p2, n):
    return [p0 * (1 - t) ** 2 + p1 * 2 * (1 - t) * t + p2 * t ** 2 for t in (i / (n - 1) for i in range(n))]


def _lantern(bm_frame, bm_glass, center, s=1.0):
    """方形吊灯：四棱锥顶盖、上下底板、四根角柱、玻璃芯。center 为玻璃中心。"""
    c = Vector(center)
    bmesh.ops.create_cone(bm_frame, cap_ends=True, segments=4, radius1=0.13 * s, radius2=0.0, depth=0.09 * s,
                          matrix=Matrix.Translation(c + Vector((0, 0, 0.155 * s))) @ Matrix.Rotation(math.pi / 4, 4, "Z"))
    _aabb(bm_frame, c + Vector((0, 0, 0.11 * s)), (0.1 * s, 0.1 * s, 0.015 * s))
    _aabb(bm_frame, c + Vector((0, 0, -0.12 * s)), (0.09 * s, 0.09 * s, 0.02 * s))
    for sx in (-1, 1):
        for sy in (-1, 1):
            _aabb(bm_frame, c + Vector((sx * 0.075 * s, sy * 0.075 * s, 0)), (0.012 * s, 0.012 * s, 0.11 * s))
    _aabb(bm_glass, c, (0.07 * s, 0.07 * s, 0.1 * s))


def _leaf(bm, center, tip_dir, normal, length, width):
    """菱形叶片：4 个顶点、2 个三角形，中间略微折起。返回 (顶点, 面)，顶点顺序为 [叶柄, 左, 叶尖, 右]。"""
    t = tip_dir.normalized()
    n = (normal - t * normal.dot(t)).normalized()
    side = t.cross(n)
    pts = (center - t * length * 0.45, center - side * width * 0.5 + n * width * 0.12,
           center + t * length * 0.55, center + side * width * 0.5 + n * width * 0.12)
    vs = [bm.verts.new(p) for p in pts]
    return vs, [bm.faces.new((vs[0], vs[1], vs[2])), bm.faces.new((vs[0], vs[2], vs[3]))]


def _set_wind(faces, uv, weight, phase, material_index):
    """写入摆动 UV（U = 权重，V = 相位）和材质槽。weight 可以是常数或 vert -> 权重 的函数。"""
    for f in faces:
        f.material_index = material_index
        for loop in f.loops:
            loop[uv].uv = (weight(loop.vert) if callable(weight) else weight, phase)


def _vine(bm, uv, origin, u, n, a_start, a_range, z_max, steps):
    """藤蔓：从墙根向上随机生长的茎（槽 0）、沿途的叶片（槽 1）和零星小花（槽 2），可分叉。"""
    up = Vector((0, 0, 1))
    walkers = [(a_start, BASE + 0.05, math.pi / 2, steps)]
    while walkers:
        a, z, ang, remaining = walkers.pop()
        prev = origin + u * a + up * z + n * 0.12
        for i in range(remaining):
            ang += random.uniform(-0.45, 0.45)
            if z >= z_max:
                ang = 0.15 if math.cos(ang) >= 0 else math.pi - 0.15
            ang = min(max(ang, 0.15), math.pi - 0.15)
            na = a + math.cos(ang) * 0.11
            if not a_range[0] <= na <= a_range[1]:
                ang = math.pi - ang
                na = a + math.cos(ang) * 0.11
            a = na
            z = min(z + max(math.sin(ang) * 0.11, 0.0) * (0.0 if z >= z_max else 1.0), z_max + 0.05)
            pos = origin + u * a + up * z + n * (0.12 + random.uniform(-0.01, 0.01))
            seg = pos - prev
            if seg.length > 1e-4:
                faces = _add_box(bm, (prev + pos) / 2, seg.normalized().cross(n), seg.normalized(), n, 0.012, seg.length / 2 + 0.006, 0.01)
                _set_wind(faces, uv, 0.12, random.random(), 0)
            for _ in range(random.randint(1, 3)):
                b = random.uniform(0, math.tau)
                c = pos + u * random.uniform(-0.07, 0.07) + up * random.uniform(-0.05, 0.05) + n * random.uniform(0.01, 0.05)
                tip = (u * math.cos(b) + up * math.sin(b)) * 0.8 + n * 0.4
                normal = n + u * random.uniform(-0.4, 0.4) + up * random.uniform(-0.3, 0.3)
                vs, faces = _leaf(bm, c, tip, normal, random.uniform(0.1, 0.16), random.uniform(0.08, 0.12))
                stalk = vs[0]
                _set_wind(faces, uv, lambda v, s=stalk.co.copy(): 0.5 if v.co == s else 1.0, random.random(), 1)
            if random.random() < 0.25:
                p = pos + u * random.uniform(-0.06, 0.06) + up * random.uniform(-0.04, 0.04) + n * 0.05
                res = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=random.uniform(0.03, 0.045), matrix=Matrix.Translation(p))
                _set_wind({f for v in res["verts"] for f in v.link_faces}, uv, 0.6, random.random(), 2)
            if random.random() < 0.12 and remaining - i > 8:
                walkers.append((a, z, ang + random.choice((-0.8, 0.8)), (remaining - i) // 2))
            prev = pos


def _bush(bm, uv, center, radius, height, leaves=30, blooms=6):
    """墙根花丛：实心内核和表面朝外的叶片（槽 0）加顶部的小花（槽 1）。"""
    c = Vector(center)
    core = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0,
                                      matrix=Matrix.Translation(c + Vector((0, 0, height * 0.4)))
                                      @ Matrix.Diagonal((radius * 0.85, radius * 0.85, height * 0.6, 1.0)))
    _set_wind({f for v in core["verts"] for f in v.link_faces}, uv, 0.2, random.random(), 0)
    for _ in range(leaves):
        th = random.uniform(0, math.tau)
        phi = random.uniform(0, math.pi * 0.48)
        d = Vector((math.sin(phi) * math.cos(th), math.sin(phi) * math.sin(th), math.cos(phi)))
        s = random.uniform(0.85, 1.05)
        p = c + Vector((d.x * radius * s, d.y * radius * s, d.z * height * s))
        tip = d.cross(Vector((0, 0, 1))) * random.uniform(-1, 1) + Vector((0, 0, 1)) * random.uniform(0.2, 1.0) + d * 0.5
        vs, faces = _leaf(bm, p, tip, d, random.uniform(0.25, 0.38), random.uniform(0.18, 0.26))
        w = 0.3 + 0.7 * max(p.z - c.z, 0.0) / height
        _set_wind(faces, uv, w, random.random(), 0)
    for _ in range(blooms):
        th = random.uniform(0, math.tau)
        phi = random.uniform(0, math.pi / 3)
        d = Vector((math.sin(phi) * math.cos(th), math.sin(phi) * math.sin(th), math.cos(phi)))
        p = c + Vector((d.x * radius, d.y * radius, d.z * height)) * 1.02
        res = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=random.uniform(0.05, 0.07), matrix=Matrix.Translation(p))
        faces = {f for v in res["verts"] for f in v.link_faces}
        _set_wind(faces, uv, 0.6, random.random(), 1)


def _prism(bm, profile_yz, x0, x1):
    a = [bm.verts.new((x0, y, z)) for y, z in profile_yz]
    b = [bm.verts.new((x1, y, z)) for y, z in profile_yz]
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    k = len(profile_yz)
    for i in range(k):
        j = (i + 1) % k
        bm.faces.new((a[i], a[j], b[j], b[i]))


def build(scene_name="Cabin", seed=7):
    random.seed(seed)
    scn = bpy.data.scenes.get(scene_name) or bpy.data.scenes.new(scene_name)
    for o in list(scn.collection.all_objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(scn.collection.children_recursive):
        bpy.data.collections.remove(c)
    for me in list(bpy.data.meshes):
        if me.users == 0 and me.name.startswith("cabin_"):
            bpy.data.meshes.remove(me)

    M = _materials()
    coll = bpy.data.collections.new("CabinParts")
    scn.collection.children.link(coll)
    foliage_coll = bpy.data.collections.new("CabinFoliage")
    scn.collection.children.link(foliage_coll)
    root = bpy.data.objects.new("CabinSource", None)
    coll.objects.link(root)

    def make_obj(name, bm, material, bevel=0.0, segs=1, target=None):
        """material 可以是单个材质或材质列表（按面的 material_index 对应）。"""
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new("cabin_" + name)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        (target or coll).objects.link(ob)
        for m in material if isinstance(material, list) else [material]:
            me.materials.append(m)
        ob.parent = root
        if bevel > 0:
            mod = ob.modifiers.new("Bevel", "BEVEL")
            mod.width = bevel
            mod.segments = segs
        return ob

    dy = DORMER_Y

    # 墙体（五边形棱柱）+ 老虎窗墙体
    bm = bmesh.new()
    prof = [(-HW, BASE), (HW, BASE), (HW, EAVE), (0, RIDGE), (-HW, EAVE)]
    front = [bm.verts.new((x, -HD, z)) for x, z in prof]
    back = [bm.verts.new((x, HD, z)) for x, z in prof]
    bm.faces.new(front)
    bm.faces.new(list(reversed(back)))
    for i in range(5):
        j = (i + 1) % 5
        bm.faces.new((front[i], front[j], back[j], back[i]))
    _aabb(bm, (0.68, dy, 3.9), (0.47, 0.42, 0.7))
    _prism(bm, [(dy - 0.42, 4.6), (dy + 0.42, 4.6), (dy, 4.93)], 0.21, 1.15)
    make_obj("Walls", bm, M["wall"], 0.02, 2)

    # 地基 + 台阶
    bm = bmesh.new()
    _aabb(bm, (0, 0, 0.2), (HW + 0.12, HD + 0.12, 0.2))
    _aabb(bm, (0.55, -HD - 0.32, 0.2), (0.48, 0.2, 0.2))
    _aabb(bm, (0.55, -HD - 0.62, 0.1), (0.48, 0.12, 0.1))
    make_obj("Foundation", bm, M["stone"], 0.035, 2)

    # 木构
    bm = bmesh.new()
    for sx in (-1, 1):
        for sy in (-1, 1):
            _aabb(bm, (sx * HW, sy * HD, (BASE + EAVE) / 2), (0.1, 0.1, (EAVE - BASE) / 2))
    for sx in (-1, 1):
        for z in (0.5, 1.2, 3.08):
            _aabb(bm, (sx * (HW + 0.03), 0, z), (0.05, HD, 0.07))
        for y0, y1 in ((-HD + 0.1, -HD + 1.0), (HD - 0.1, HD - 1.0)):
            _beam(bm, (sx * (HW + 0.03), y0, 1.25), (sx * (HW + 0.03), y1, 3.05), (sx, 0, 0), 0.06, 0.05)
    for sy in (-1, 1):
        for z in (0.5, 3.08):
            _aabb(bm, (0, sy * (HD + 0.03), z), (HW, 0.05, 0.07))
        _beam(bm, (-HW, sy * (HD + 0.03), EAVE), (0, sy * (HD + 0.03), RIDGE), (0, sy, 0), 0.07, 0.05)
        _beam(bm, (HW, sy * (HD + 0.03), EAVE), (0, sy * (HD + 0.03), RIDGE), (0, sy, 0), 0.07, 0.05)
    for sy in (-1, 1):
        _aabb(bm, (1.16, dy + sy * 0.42, 4.15), (0.05, 0.05, 0.45))
    make_obj("Timber", bm, M["timber"], 0.015, 1)

    # 屋顶瓦片（老虎窗位置留空）+ 屋脊 + 门廊雨棚 + 老虎窗屋顶
    bm = bmesh.new()
    slope_len = math.hypot(HW, RIDGE - EAVE)
    shingle_len, thick, step = 0.42, 0.055, 0.30
    for side in (-1, 1):
        d = Vector((side * HW, 0, EAVE - RIDGE)).normalized()
        n = Vector((side * (RIDGE - EAVE), 0, HW)).normalized()
        yv = Vector((0, 1, 0))
        ridge = Vector((0, 0, RIDGE))
        rows = int((slope_len + 0.45 + 0.06) / step) + 1
        for i in range(rows):
            s_mid = -0.06 + i * step + shingle_len / 2
            y = -HD - 0.35 + random.uniform(0, 0.18)
            while y < HD + 0.35:
                w = min(random.uniform(0.24, 0.36), HD + 0.35 - y)
                if w < 0.08:
                    break
                cx = (d * s_mid).x
                if side > 0 and 0.5 < cx < 1.22 and abs(y + w / 2 - dy) < 0.5:
                    y += w
                    continue
                th = math.radians(7 + random.uniform(-2.5, 2.5))
                v2 = d * math.cos(th) + n * math.sin(th)
                n2 = n * math.cos(th) - d * math.sin(th)
                rot = Matrix.Rotation(math.radians(random.uniform(-3, 3)), 3, n2)
                c = ridge + d * s_mid + yv * (y + w / 2) + n * (thick / 2 + (shingle_len / 2) * math.sin(th) + random.uniform(0, 0.012))
                _add_box(bm, c, rot @ yv, rot @ v2, n2, w / 2 - 0.008, shingle_len / 2, thick / 2)
                y += w
    _add_box(bm, (0, 0, RIDGE + 0.16), (0, 1, 0), (1, 0, 1), (-1, 0, 1), HD + 0.38, 0.14, 0.14)
    a = math.radians(28)
    pd = Vector((0, -math.cos(a), -math.sin(a)))
    pn = Vector((0, -math.sin(a), math.cos(a)))
    _add_box(bm, Vector((0.55, -HD - 0.02, 2.62)) + pd * 0.45 + pn * 0.04, (1, 0, 0), pd, pn, 0.7, 0.5, 0.045)
    for sy in (-1, 1):
        top = Vector((0, dy, 4.97))
        low = Vector((0, dy + sy * 0.62, 4.48))
        dv = (low - top).normalized()
        nv = Vector((0, -sy * dv.z, sy * dv.y)).normalized()
        if nv.z < 0:
            nv = -nv
        _add_box(bm, (top + low) / 2 + Vector((0.76, 0, 0)) + nv * 0.03, (1, 0, 0), dv, nv,
                 0.62, (low - top).length / 2 + 0.04, 0.035)
    make_obj("Roof", bm, M["roof"], 0.01, 1)

    # 烟囱（叠砌石块）
    bm = bmesh.new()
    cx, cy, z = -0.78, -1.0, 3.6
    while z < 6.35:
        h = 0.24
        _aabb(bm, (cx + random.uniform(-0.015, 0.015), cy + random.uniform(-0.015, 0.015), z + h / 2),
              (0.3 + random.uniform(-0.02, 0.02), 0.3 + random.uniform(-0.02, 0.02), h / 2 - 0.006))
        z += h
    _aabb(bm, (cx, cy, z + 0.05), (0.38, 0.38, 0.06))
    make_obj("Chimney", bm, M["chimney"], 0.02, 1)

    # 门
    bm = bmesh.new()
    _aabb(bm, (0.55, -HD - 0.05, BASE + 0.05 + 0.85), (0.42, 0.04, 0.85))
    make_obj("Door", bm, M["door"], 0.012, 1)

    # 窗框、玻璃、门框
    win_specs = [
        ((HW, 0.4, 2.0), (1, 0, 0), 0.38, 0.45),
        ((-HW, 0.8, 2.0), (-1, 0, 0), 0.38, 0.45),
        ((-0.7, -HD, 1.95), (0, -1, 0), 0.32, 0.42),
        ((0, -HD, 4.15), (0, -1, 0), 0.24, 0.32),
        ((0, HD, 4.15), (0, 1, 0), 0.24, 0.32),
        ((1.15, dy, 4.2), (1, 0, 0), 0.2, 0.24),
    ]
    bm_f = bmesh.new()
    bm_g = bmesh.new()
    for c, o, hw_, hh in win_specs:
        c = Vector(c)
        o = Vector(o)
        up = Vector((0, 0, 1))
        sidev = up.cross(o)
        _add_box(bm_f, c + o * 0.04, sidev, up, o, hw_ + 0.08, hh + 0.08, 0.04)
        _add_box(bm_g, c + o * 0.07, sidev, up, o, hw_, hh, 0.02)
        _add_box(bm_f, c + o * 0.09, sidev, up, o, 0.025, hh, 0.02)
        _add_box(bm_f, c + o * 0.09, sidev, up, o, hw_, 0.025, 0.02)
        _add_box(bm_f, c + o * 0.10 + up * (-hh - 0.1), sidev, up, o, hw_ + 0.12, 0.04, 0.06)
    _add_box(bm_f, (0.55, -HD - 0.02, BASE + 0.05 + 0.92), (1, 0, 0), (0, 0, 1), (0, -1, 0), 0.52, 0.94, 0.03)
    make_obj("WindowFrames", bm_f, M["frame"], 0.008, 1)
    make_obj("Glass", bm_g, M["glass"])

    # 老虎窗花箱 + 花
    bm = bmesh.new()
    _aabb(bm, (1.33, dy, 3.86), (0.11, 0.3, 0.07))
    make_obj("Planter", bm, M["planter"], 0.01, 1)
    bm = bmesh.new()
    for _ in range(11):
        p = Vector((1.33 + random.uniform(-0.05, 0.05), dy + random.uniform(-0.26, 0.26), 3.96 + random.uniform(0, 0.04)))
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=random.uniform(0.045, 0.07), matrix=Matrix.Translation(p))
    make_obj("Flowers", bm, M["flowers"])

    # 门口灯柱：弯曲的木柱 + 横臂 + 斜撑，臂端吊一盏灯；门左侧墙上一盏壁灯
    bm = bmesh.new()
    post = _bezier(Vector((1.45, -3.15, 0.0)), Vector((1.6, -3.15, 1.1)), Vector((1.38, -3.12, 2.3)), 9)
    _tube(bm, post, [0.065 - 0.02 * i / 8 for i in range(9)], 7)
    arm = _bezier(Vector((1.39, -3.12, 2.17)), Vector((1.15, -3.12, 2.29)), Vector((0.92, -3.12, 2.26)), 5)
    _tube(bm, arm, [0.032] * 5, 6)
    _tube(bm, [Vector((1.43, -3.13, 1.75)), Vector((1.14, -3.12, 2.24))], [0.022, 0.022], 5)
    make_obj("LanternPost", bm, M["post"], 0.008, 1)

    bm_frame = bmesh.new()
    bm_glass = bmesh.new()
    _aabb(bm_frame, (0.97, -3.12, 2.16), (0.008, 0.008, 0.08))
    _lantern(bm_frame, bm_glass, (0.97, -3.12, 1.9))
    _aabb(bm_frame, (-0.2, -HD - 0.2, 2.22), (0.015, 0.13, 0.015))
    _aabb(bm_frame, (-0.2, -HD - 0.07, 2.22), (0.05, 0.02, 0.07))
    _lantern(bm_frame, bm_glass, (-0.2, -HD - 0.3, 2.05), 0.8)
    make_obj("LanternFrames", bm_frame, M["metal"], 0.004, 1)
    make_obj("LanternGlass", bm_glass, M["lamp_glass"])

    # 正面左侧的小院栅栏：立柱略歪，两道横杆，个别横杆缺失或掉落（低模用同一份数据）
    fence_boxes = []
    fence_line = [Vector((-0.1, -2.2, 0)), Vector((-0.1, -3.25, 0)), Vector((-2.0, -3.25, 0)), Vector((-2.0, -1.3, 0)), Vector((-1.7, -1.3, 0))]
    posts = []
    for p0, p1 in zip(fence_line, fence_line[1:]):
        count = max(1, math.ceil((p1 - p0).length / 0.62))
        for k in range(count):
            posts.append(p0.lerp(p1, k / count))
    posts.append(fence_line[-1])
    tops = []
    for p in posts:
        h = random.uniform(0.72, 0.86)
        tilt = Vector((random.uniform(-0.05, 0.05), random.uniform(-0.05, 0.05), 1)).normalized()
        fence_boxes.append((p + tilt * h / 2, tilt.cross(Vector((0, 1, 0))).normalized(), Vector((0, 1, 0)), tilt, 0.04, 0.04, h / 2))
        tops.append((p, tilt))
    for (p0, t0), (p1, t1) in zip(tops, tops[1:]):
        for rail_z in (0.3, 0.6):
            if random.random() < 0.12:
                continue
            a = p0 + t0 * (rail_z + random.uniform(-0.03, 0.03))
            b = p1 + t1 * (rail_z + random.uniform(-0.03, 0.03))
            if random.random() < 0.08:
                b = Vector((b.x, b.y, 0.12))
            d = b - a
            side = d.normalized().cross(Vector((0, 0, 1)))
            if side.length < 1e-3:
                continue
            fence_boxes.append(((a + b) / 2, side.normalized(), d.normalized(), d.normalized().cross(side).normalized(), 0.018, d.length / 2 + 0.03, 0.03))
    bm = bmesh.new()
    for box in fence_boxes:
        _add_box(bm, *box)
    make_obj("Fence", bm, M["fence"], 0.008, 1)

    # 藤蔓（正面左角、门右侧、东墙靠前），只作烘焙源，颜色烘焙到低模墙面
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("Wind")
    _vine(bm, uv, Vector((0, -HD, 0)), Vector((1, 0, 0)), Vector((0, -1, 0)), -1.35, (-1.55, -1.12), 3.0, 32)
    _vine(bm, uv, Vector((0, -HD, 0)), Vector((1, 0, 0)), Vector((0, -1, 0)), 1.4, (1.27, 1.55), 2.6, 24)
    _vine(bm, uv, Vector((HW, 0, 0)), Vector((0, -1, 0)), Vector((1, 0, 0)), 1.6, (0.9, 1.95), 3.0, 34)
    make_obj("Vines", bm, [M["stem"], M["vine_leaf"], M["bloom"]])

    # 墙根花丛
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("Wind")
    for center, r, h in (
        ((-0.6, -2.65, 0.0), 0.55, 0.8), ((-1.3, -2.8, 0.0), 0.6, 0.9), ((-1.75, -2.25, 0.0), 0.5, 0.75),
        ((-1.85, -1.55, 0.0), 0.48, 0.7), ((1.85, -1.5, 0.0), 0.5, 0.8), ((1.9, -0.2, 0.0), 0.55, 0.75),
        ((1.85, 1.4, 0.0), 0.5, 0.75), ((1.7, -2.85, 0.0), 0.42, 0.65),
    ):
        _bush(bm, uv, center, r, h)
    make_obj("Bushes", bm, [M["bush_leaf"], M["bloom"]], target=foliage_coll)

    _build_low(scn, root, fence_boxes)
    return scn


def _build_low(scn, root, fence_boxes):
    """导出用的低模：只保留轮廓，细节由高模烘焙到贴图。"""
    coll = bpy.data.collections.new("CabinLow")
    scn.collection.children.link(coll)

    def low_obj(name, bm):
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new("cabin_low_" + name)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name + "_Low", me)
        coll.objects.link(ob)
        ob.parent = root

    dy = DORMER_Y
    bm = bmesh.new()
    prof = [(-HW, BASE), (HW, BASE), (HW, EAVE), (0, RIDGE), (-HW, EAVE)]
    front = [bm.verts.new((x, -HD, z)) for x, z in prof]
    back = [bm.verts.new((x, HD, z)) for x, z in prof]
    bm.faces.new(front)
    bm.faces.new(list(reversed(back)))
    for i in range(5):
        j = (i + 1) % 5
        bm.faces.new((front[i], front[j], back[j], back[i]))
    _aabb(bm, (0.68, dy, 3.9), (0.47, 0.42, 0.7))
    _prism(bm, [(dy - 0.42, 4.6), (dy + 0.42, 4.6), (dy, 4.93)], 0.21, 1.15)
    _aabb(bm, (1.33, dy, 3.86), (0.11, 0.3, 0.07))                       # 花箱
    low_obj("Walls", bm)

    bm = bmesh.new()
    _aabb(bm, (0, 0, 0.2), (HW + 0.12, HD + 0.12, 0.2))
    _aabb(bm, (0.55, -HD - 0.32, 0.2), (0.48, 0.2, 0.2))
    _aabb(bm, (0.55, -HD - 0.62, 0.1), (0.48, 0.12, 0.1))
    low_obj("Foundation", bm)

    # 屋面板包住瓦片的外轮廓
    bm = bmesh.new()
    for side in (-1, 1):
        d = Vector((side * HW, 0, EAVE - RIDGE)).normalized()
        n = Vector((side * (RIDGE - EAVE), 0, HW)).normalized()
        _add_box(bm, Vector((0, 0, RIDGE)) + d * 1.8 + n * 0.055, (0, 1, 0), d, n, HD + 0.35, 1.86, 0.055)
    _add_box(bm, (0, 0, RIDGE + 0.16), (0, 1, 0), (1, 0, 1), (-1, 0, 1), HD + 0.38, 0.14, 0.14)
    a = math.radians(28)
    pd = Vector((0, -math.cos(a), -math.sin(a)))
    pn = Vector((0, -math.sin(a), math.cos(a)))
    _add_box(bm, Vector((0.55, -HD - 0.02, 2.62)) + pd * 0.45 + pn * 0.04, (1, 0, 0), pd, pn, 0.7, 0.5, 0.045)
    for sy in (-1, 1):
        top = Vector((0, dy, 4.97))
        low = Vector((0, dy + sy * 0.62, 4.48))
        dv = (low - top).normalized()
        nv = Vector((0, -sy * dv.z, sy * dv.y)).normalized()
        if nv.z < 0:
            nv = -nv
        _add_box(bm, (top + low) / 2 + Vector((0.76, 0, 0)) + nv * 0.03, (1, 0, 0), dv, nv,
                 0.62, (low - top).length / 2 + 0.04, 0.035)
    low_obj("Roof", bm)

    bm = bmesh.new()
    _aabb(bm, (-0.78, -1.0, (3.6 + 6.48) / 2), (0.31, 0.31, (6.48 - 3.6) / 2))
    _aabb(bm, (-0.78, -1.0, 6.53), (0.38, 0.38, 0.06))
    low_obj("Chimney", bm)

    bm = bmesh.new()
    _tube(bm, _bezier(Vector((1.45, -3.15, 0.0)), Vector((1.6, -3.15, 1.1)), Vector((1.38, -3.12, 2.3)), 4),
          [0.065, 0.058, 0.052, 0.045], 4)
    _beam(bm, (1.39, -3.12, 2.17), (0.92, -3.12, 2.26), (0, -1, 0), 0.03, 0.03)
    _aabb(bm, (0.97, -3.12, 1.92), (0.08, 0.08, 0.17))                   # 吊灯
    _aabb(bm, (-0.2, -HD - 0.2, 2.22), (0.015, 0.13, 0.015))             # 壁灯支架
    _aabb(bm, (-0.2, -HD - 0.3, 2.07), (0.065, 0.065, 0.14))             # 壁灯
    for box in fence_boxes:
        _add_box(bm, *box)
    low_obj("Props", bm)


if __name__ == "__main__":
    build()
