@tool
extends Node3D

## 森林：在 area 多边形内种树，避开 clearing（空地）和 exclude_areas。
## 近处（离空地 far_distance 以内）：随机种树，相邻树冠按大小保持间距；离空地越远树越高越大，
## 林缘多是低矮的树和灌木，形成错落的层次。树冠和树干都投影。
## 远处：按网格均匀铺大树冠，低面数、球体少、不投影，用来在任意朝向下铺满远景（远景会被移轴完全虚化）。
## 所有球体按材质和远近合并成 MultiMesh，整片森林只有十次左右绘制调用。
## 区域都是平铺在地面上的 CSGPolygon3D。改了区域或参数后点「重新生成」。
## 实例在运行时生成，不写进场景文件。

@export var area: NodePath
@export var clearing: NodePath
@export var exclude_areas: Array[NodePath] = []
@export var foliage_materials: Array[Material] = []
@export var random_seed := 1

@export_group("近处树林")
@export var max_trees := 320
## 林缘 → 近处树林外缘的树冠半径。
@export var canopy_radius := Vector2(1.0, 4.2)
## 林缘 → 近处树林外缘的树干高度。
@export var trunk_height := Vector2(0.8, 5.5)
## 离空地多远长到最大。
@export var growth_distance := 22.0
## 林缘处长成灌木（没有树干）的概率，越往里越低。
@export var bush_chance := 0.4
## 相邻树冠的最小间距 = (r1 + r2) * overlap，小于 1 时树冠互相交叠。
@export var overlap := 0.7

@export_group("远景林冠")
## 离空地多远开始改用远景林冠。
@export var far_distance := 28.0
@export var far_spacing := 8.0
@export var far_canopy_radius := Vector2(4.5, 7.0)
## 远景树冠中心的高度范围。
@export var far_height := Vector2(5.0, 8.0)

@export_group("")
@export_tool_button("重新生成") var rebuild_action := _rebuild

static var _sphere: SphereMesh
static var _far_sphere: SphereMesh
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
	var mat_count := foliage_materials.size()
	var near_blobs := []
	var far_blobs := []
	for i in mat_count:
		near_blobs.append([])
		far_blobs.append([])
	var trunks := []
	var inv := global_transform.affine_inverse()

	# 近处：随机投点，空间网格加速邻居检查
	var near_bounds: Rect2 = include.bounds
	if not clear.is_empty():
		near_bounds = clear.bounds.grow(far_distance).intersection(include.bounds)
	var cell := maxf(2.0 * canopy_radius.y * 1.15 * overlap, 0.5)
	var grid := {}
	var trees := []
	var attempts := max_trees * 30
	while trees.size() < max_trees and attempts > 0:
		attempts -= 1
		var p := Vector2(rng.randf_range(near_bounds.position.x, near_bounds.end.x), rng.randf_range(near_bounds.position.y, near_bounds.end.y))
		if not Regions.inside_any(p, [include]) or Regions.inside_any(p, excludes):
			continue
		var d := Regions.distance_to_edge(p, clear) if not clear.is_empty() else far_distance
		if d >= far_distance:
			continue
		var g := clampf(d / growth_distance, 0.0, 1.0)
		var r := lerpf(canopy_radius.x, canopy_radius.y, g) * rng.randf_range(0.85, 1.15)
		var key := Vector2i(floori(p.x / cell), floori(p.y / cell))
		if not _is_free(grid, key, p, r):
			continue
		if not grid.has(key):
			grid[key] = []
		grid[key].append([p, r])
		trees.append([p, r, g])

	for t in trees:
		var p: Vector2 = t[0]
		var r: float = t[1]
		var g: float = t[2]
		var base := inv * Vector3(p.x, global_position.y, p.y)
		var canopy_y := r * 0.7
		if rng.randf() >= bush_chance * (1.0 - g):
			var h := lerpf(trunk_height.x, trunk_height.y, g) * rng.randf_range(0.8, 1.2)
			var w := 0.7 + r * 0.2
			trunks.append(Transform3D(Basis.from_scale(Vector3(w, h / _trunk.height, w)), base + Vector3(0.0, h * 0.5, 0.0)))
			canopy_y = h + r * 0.45
		_add_canopy(near_blobs[rng.randi() % mat_count], rng, base, r, canopy_y, rng.randi_range(4, 6), 0.9)

	# 远处：抖动网格，每格一棵大树冠
	var b: Rect2 = include.bounds
	var x := b.position.x
	while x < b.end.x:
		var y := b.position.y
		while y < b.end.y:
			var p := Vector2(x, y) + Vector2(rng.randf_range(0.1, 0.9), rng.randf_range(0.1, 0.9)) * far_spacing
			y += far_spacing
			if not Regions.inside_any(p, [include]) or Regions.inside_any(p, excludes):
				continue
			if not clear.is_empty() and Regions.distance_to_edge(p, clear) < far_distance:
				continue
			var r := rng.randf_range(far_canopy_radius.x, far_canopy_radius.y)
			var base := inv * Vector3(p.x, global_position.y, p.y)
			_add_canopy(far_blobs[rng.randi() % mat_count], rng, base, r, rng.randf_range(far_height.x, far_height.y), 3, 0.75)
		x += far_spacing

	for i in mat_count:
		_add_multimesh(_sphere, foliage_materials[i], near_blobs[i], true)
		_add_multimesh(_far_sphere, foliage_materials[i], far_blobs[i], false)
	_add_multimesh(_trunk, _trunk_material, trunks, true)


## 树冠：一个主球加若干个小球，flatten 越小越扁。
func _add_canopy(out: Array, rng: RandomNumberGenerator, base: Vector3, r: float, canopy_y: float, blobs: int, flatten: float) -> void:
	for k in blobs:
		var s := r * (1.0 if k == 0 else rng.randf_range(0.55, 0.8))
		var offset := Vector3(0.0, canopy_y, 0.0)
		if k > 0:
			var a := rng.randf() * TAU
			var d := r * rng.randf_range(0.45, 0.75)
			offset += Vector3(cos(a) * d, rng.randf_range(-0.35, 0.45) * r, sin(a) * d)
		var basis_k := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3(s, s * flatten * rng.randf_range(0.88, 1.05), s))
		out.append(Transform3D(basis_k, base + offset))


func _is_free(grid: Dictionary, key: Vector2i, p: Vector2, r: float) -> bool:
	for dx in range(-1, 2):
		for dy in range(-1, 2):
			var k := key + Vector2i(dx, dy)
			if not grid.has(k):
				continue
			for other in grid[k]:
				if p.distance_to(other[0]) < (r + other[1]) * overlap:
					return false
	return true


func _add_multimesh(mesh: Mesh, material: Material, xforms: Array, shadows: bool) -> void:
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
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if shadows else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
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
	_far_sphere = SphereMesh.new()
	_far_sphere.radius = 1.0
	_far_sphere.height = 2.0
	_far_sphere.radial_segments = 10
	_far_sphere.rings = 5
	_trunk = CylinderMesh.new()
	_trunk.top_radius = 0.1
	_trunk.bottom_radius = 0.18
	_trunk.height = 2.6
	_trunk.radial_segments = 8
	_trunk.rings = 1
	_trunk_material = StandardMaterial3D.new()
	_trunk_material.albedo_color = Color(0.27, 0.17, 0.12)
	_trunk_material.roughness = 1.0
