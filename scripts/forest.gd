@tool
extends Node3D

## 森林：在 area 多边形内随机种树，避开 clearing（空地）和 exclude_areas。
## 相邻树冠按大小保持间距；离空地越远树越高越大，林缘多是低矮的树和灌木，形成错落的层次。
## 所有树冠球体按材质合并成 MultiMesh，树干合并成一个 MultiMesh，整片森林只有几次绘制调用。
## 区域都是平铺在地面上的 CSGPolygon3D。改了区域或参数后点「重新生成」。
## 实例在运行时生成，不写进场景文件。

@export var area: NodePath
@export var clearing: NodePath
@export var exclude_areas: Array[NodePath] = []
@export var foliage_materials: Array[Material] = []
@export var max_trees := 160
## 林缘 → 林深处的树冠半径。
@export var canopy_radius := Vector2(1.0, 3.0)
## 林缘 → 林深处的树干高度。
@export var trunk_height := Vector2(0.8, 4.2)
## 离空地多远长到最大。
@export var growth_distance := 12.0
## 林缘处长成灌木（没有树干）的概率，越往里越低。
@export var bush_chance := 0.4
## 相邻树冠的最小间距 = (r1 + r2) * overlap，小于 1 时树冠互相交叠。
@export var overlap := 0.7
@export var random_seed := 1
@export_tool_button("重新生成") var rebuild_action := _rebuild

static var _sphere: SphereMesh
static var _trunk: CylinderMesh
static var _trunk_material: StandardMaterial3D


func _ready() -> void:
	_rebuild()


func _rebuild() -> void:
	for child in get_children():
		if child.has_meta("generated"):
			remove_child(child)
			child.queue_free()
	if not is_inside_tree() or foliage_materials.is_empty():
		return
	var include := Regions.from_node(get_node_or_null(area))
	if include.is_empty():
		return
	var clear := Regions.from_node(get_node_or_null(clearing))
	var excludes := Regions.collect(self, exclude_areas)
	if not clear.is_empty():
		excludes.append(clear)
	_ensure_shared()

	var rng := RandomNumberGenerator.new()
	rng.seed = random_seed
	var bounds: Rect2 = include.bounds
	var trees := []
	var attempts := max_trees * 40
	while trees.size() < max_trees and attempts > 0:
		attempts -= 1
		var p := Vector2(rng.randf_range(bounds.position.x, bounds.end.x), rng.randf_range(bounds.position.y, bounds.end.y))
		if not Regions.inside_any(p, [include]) or Regions.inside_any(p, excludes):
			continue
		var g := 1.0
		if not clear.is_empty():
			g = clampf(Regions.distance_to_edge(p, clear) / growth_distance, 0.0, 1.0)
		var r := lerpf(canopy_radius.x, canopy_radius.y, g) * rng.randf_range(0.85, 1.15)
		var free := true
		for t in trees:
			if p.distance_to(t[0]) < (r + t[1]) * overlap:
				free = false
				break
		if free:
			trees.append([p, r, g])

	var blob_xforms := []
	for i in foliage_materials.size():
		blob_xforms.append([])
	var trunk_xforms := []
	var inv := global_transform.affine_inverse()
	for t in trees:
		var p: Vector2 = t[0]
		var r: float = t[1]
		var g: float = t[2]
		var base := inv * Vector3(p.x, global_position.y, p.y)
		var canopy_y := r * 0.7
		if rng.randf() >= bush_chance * (1.0 - g):
			var h := lerpf(trunk_height.x, trunk_height.y, g) * rng.randf_range(0.8, 1.2)
			var w := 0.7 + r * 0.2
			trunk_xforms.append(Transform3D(Basis.from_scale(Vector3(w, h / _trunk.height, w)), base + Vector3(0.0, h * 0.5, 0.0)))
			canopy_y = h + r * 0.45
		var mat := rng.randi() % foliage_materials.size()
		var blobs := rng.randi_range(4, 6)
		for k in blobs:
			var s := r * (1.0 if k == 0 else rng.randf_range(0.55, 0.8))
			var offset := Vector3(0.0, canopy_y, 0.0)
			if k > 0:
				var a := rng.randf() * TAU
				var d := r * rng.randf_range(0.45, 0.75)
				offset += Vector3(cos(a) * d, rng.randf_range(-0.35, 0.45) * r, sin(a) * d)
			var b := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3(s, s * rng.randf_range(0.8, 0.95), s))
			blob_xforms[mat].append(Transform3D(b, base + offset))

	for i in foliage_materials.size():
		_add_multimesh(_sphere, foliage_materials[i], blob_xforms[i])
	_add_multimesh(_trunk, _trunk_material, trunk_xforms)


func _add_multimesh(mesh: Mesh, material: Material, xforms: Array) -> void:
	if xforms.is_empty():
		return
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = xforms.size()
	for i in xforms.size():
		mm.set_instance_transform(i, xforms[i])
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.material_override = material
	mmi.set_meta("generated", true)
	add_child(mmi)


static func _ensure_shared() -> void:
	if _sphere:
		return
	_sphere = SphereMesh.new()
	_sphere.radius = 1.0
	_sphere.height = 2.0
	_sphere.radial_segments = 16
	_sphere.rings = 8
	_trunk = CylinderMesh.new()
	_trunk.top_radius = 0.1
	_trunk.bottom_radius = 0.18
	_trunk.height = 2.6
	_trunk.radial_segments = 8
	_trunk.rings = 1
	_trunk_material = StandardMaterial3D.new()
	_trunk_material.albedo_color = Color(0.27, 0.17, 0.12)
	_trunk_material.roughness = 1.0
