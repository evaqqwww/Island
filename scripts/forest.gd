@tool
extends Node3D

## 森林：在 area 多边形内种树，避开 clearing（空地）和 exclude_areas。
## 树木网格来自 tree_scene（Blender 生成的 trees.glb）：名字以 _Far 结尾的是远景版本，其余是近景版本。
## 近处（离空地 far_distance 以内）：随机种树，相邻树冠按大小保持间距；离空地越远树越大，
## 林缘多是矮树和灌木（灌木把树干埋进地里），形成错落的层次。近景树投影。
## 远处：按网格均匀铺远景树，不投影，用来在任意朝向下铺满远景（远景会被移轴完全虚化）。
## 每棵树从 tints 里随机取色调，写进 MultiMesh 的实例颜色（着色器里和顶点色相乘）；
## 离空地越远，色调再逐渐乘上 shade_color，树林压暗偏冷，光线集中在空地上。
## 同一种网格的树合并成一个 MultiMesh，整片森林只有几次绘制调用。
## 区域都是平铺在地面上的 CSGPolygon3D。改了区域或参数后点「重新生成」。
## 实例在运行时生成，不写进场景文件。

@export var area: NodePath
@export var clearing: NodePath
@export var exclude_areas: Array[NodePath] = []
@export var tree_scene: PackedScene
## 树冠色调（sRGB），每棵树随机取一个；重复的颜色出现得更多。
@export var tints := PackedColorArray([Color(0.96, 0.88, 0.82), Color(0.86, 0.9, 0.62)])
@export var random_seed := 1

@export_group("近处树林")
@export var max_trees := 260
## 树木网格在缩放为 1 时的树冠半径（米）。
@export var mesh_canopy_radius := 1.9
## 林缘 → 近处树林外缘的缩放。
@export var tree_scale := Vector2(0.55, 1.5)
## 离空地多远长到最大。
@export var growth_distance := 22.0
## 林缘处长成灌木的概率，越往里越低。
@export var bush_chance := 0.4
## 灌木把树干埋进地里的深度（缩放为 1 时，米）。
@export var bush_sink := 1.6
## 相邻树冠的最小间距 = (r1 + r2) * overlap，小于 1 时树冠互相交叠。
@export var overlap := 0.75

@export_group("远景")
## 离空地多远开始改用远景树。
@export var far_distance := 28.0
@export var far_spacing := 7.0
@export var far_scale := Vector2(1.5, 2.2)

@export_group("明暗")
## 远处树冠颜色乘上的系数（线性），从离空地边缘 shade_range.x 米开始过渡，到 shade_range.y 米完全生效。
@export var shade_color := Color(1, 1, 1)
@export var shade_range := Vector2(4.0, 24.0)

@export_group("")
@export_tool_button("重新生成") var rebuild_action := _rebuild


func _ready() -> void:
	_rebuild()


func _rebuild() -> void:
	for child in get_children():
		if child.has_meta("generated"):
			remove_child(child)
			child.queue_free()
	if not is_inside_tree() or tree_scene == null or tints.is_empty():
		return
	var include := Regions.from_node(get_node_or_null(area))
	if include.is_empty():
		return
	var clear := Regions.from_node(get_node_or_null(clearing))
	var excludes := Regions.collect(self, exclude_areas)
	if not clear.is_empty():
		excludes.append(clear)

	var near_meshes: Array[Mesh] = []
	var far_meshes: Array[Mesh] = []
	var scene := tree_scene.instantiate()
	for mi in scene.find_children("*", "MeshInstance3D", true, false):
		(far_meshes if String(mi.name).ends_with("_Far") else near_meshes).append((mi as MeshInstance3D).mesh)
	scene.free()
	if near_meshes.is_empty():
		return
	if far_meshes.is_empty():
		far_meshes = near_meshes

	var rng := RandomNumberGenerator.new()
	rng.seed = random_seed
	var linear_tints := PackedColorArray()
	for c in tints:
		linear_tints.append(c.srgb_to_linear())
	var near := _buckets(near_meshes.size())
	var far := _buckets(far_meshes.size())
	var inv := global_transform.affine_inverse()

	# 近处：随机投点，空间网格加速邻居检查
	var near_bounds: Rect2 = include.bounds
	if not clear.is_empty():
		near_bounds = clear.bounds.grow(far_distance).intersection(include.bounds)
	var cell := maxf(2.0 * mesh_canopy_radius * tree_scale.y * 1.1 * overlap, 0.5)
	var grid := {}
	var placed := 0
	var attempts := max_trees * 30
	while placed < max_trees and attempts > 0:
		attempts -= 1
		var p := Vector2(rng.randf_range(near_bounds.position.x, near_bounds.end.x), rng.randf_range(near_bounds.position.y, near_bounds.end.y))
		if not Regions.inside_any(p, [include]) or Regions.inside_any(p, excludes):
			continue
		var d := Regions.distance_to_edge(p, clear) if not clear.is_empty() else far_distance
		if d >= far_distance:
			continue
		var g := clampf(d / growth_distance, 0.0, 1.0)
		var s := lerpf(tree_scale.x, tree_scale.y, g) * rng.randf_range(0.9, 1.1)
		var r := mesh_canopy_radius * s
		var key := Vector2i(floori(p.x / cell), floori(p.y / cell))
		if not _is_free(grid, key, p, r):
			continue
		if not grid.has(key):
			grid[key] = []
		grid[key].append([p, r])
		placed += 1
		var sink := bush_sink * s if rng.randf() < bush_chance * (1.0 - g) else 0.0
		var origin := inv * Vector3(p.x, global_position.y - sink, p.y)
		_add_instance(near, rng.randi() % near_meshes.size(), origin, s, _shaded(linear_tints[rng.randi() % linear_tints.size()], d), rng)

	# 远处：抖动网格，每格一棵远景树
	var b: Rect2 = include.bounds
	var x := b.position.x
	while x < b.end.x:
		var y := b.position.y
		while y < b.end.y:
			var p := Vector2(x, y) + Vector2(rng.randf_range(0.1, 0.9), rng.randf_range(0.1, 0.9)) * far_spacing
			y += far_spacing
			if not Regions.inside_any(p, [include]) or Regions.inside_any(p, excludes):
				continue
			var d := Regions.distance_to_edge(p, clear) if not clear.is_empty() else far_distance
			if d < far_distance:
				continue
			var s := rng.randf_range(far_scale.x, far_scale.y)
			_add_instance(far, rng.randi() % far_meshes.size(), inv * Vector3(p.x, global_position.y, p.y), s, _shaded(linear_tints[rng.randi() % linear_tints.size()], d), rng)
		x += far_spacing

	for i in near_meshes.size():
		_add_multimesh(near_meshes[i], near[i], true)
	for i in far_meshes.size():
		_add_multimesh(far_meshes[i], far[i], false)


func _shaded(tint: Color, edge_distance: float) -> Color:
	return tint * Color(1, 1, 1).lerp(shade_color, smoothstep(shade_range.x, shade_range.y, edge_distance))


func _buckets(count: int) -> Array:
	var result := []
	for i in count:
		result.append({"xforms": [], "tints": []})
	return result


func _add_instance(buckets: Array, index: int, origin: Vector3, s: float, tint: Color, rng: RandomNumberGenerator) -> void:
	var b := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3(s, s * rng.randf_range(0.92, 1.08), s))
	buckets[index].xforms.append(Transform3D(b, origin))
	buckets[index].tints.append(Color(tint.r, tint.g, tint.b, 1.0))


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


func _add_multimesh(mesh: Mesh, bucket: Dictionary, shadows: bool) -> void:
	var xforms: Array = bucket.xforms
	if xforms.is_empty():
		return
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = mesh
	mm.instance_count = xforms.size()
	for i in xforms.size():
		mm.set_instance_transform(i, xforms[i])
		mm.set_instance_color(i, bucket.tints[i])
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if shadows else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mmi.set_meta("generated", true)
	add_child(mmi)
