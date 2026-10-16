@tool
extends Node3D

## 花坛：在 areas 多边形（平铺在地面上的 CSGPolygon3D，它的材质就是花坛的泥土底面）里
## 均匀种一丛丛圆顶灌木，花开在每丛灌木朝上的那部分球面上；沿多边形边缘摆一圈小石块包边。
## 花是扁平的花片（网格局部 Y 轴为花片朝向），贴着灌木表面摆放，略微偏向朝上。
## 灌木之间按间距排开、互相略微交叠，不挤成一团；花只在灌木顶上，不散落在地面，花坛整齐、和草坪分得清。
## 灌木、花、石块各是一个 MultiMesh。实例在运行时生成，不写进场景文件。改了参数后点「重新生成」。

@export var areas: Array[NodePath] = []
@export var random_seed := 1

@export_group("灌木")
@export var shrub_mesh: Mesh
@export var shrub_material: Material
## 灌木半径范围（米），网格按半径 1 的球体缩放。
@export var shrub_radius := Vector2(0.45, 0.65)
## 竖向压扁比例。
@export var shrub_flatten := 0.75
## 相邻灌木的最小中心距 = (r1 + r2) * shrub_spacing。
@export var shrub_spacing := 0.72
## 灌木中心离花坛边缘至少 edge_inset + 半径 × 0.5 米，给包边石块留出位置。
@export var edge_inset := 0.1

@export_group("花")
@export var bloom_mesh: Mesh
@export var bloom_material: Material
@export var blooms_per_shrub := Vector2i(12, 20)
## 花分布在灌木顶部多大的角度以内（度）。
@export var bloom_cap := 65.0
@export var bloom_scale := Vector2(0.8, 1.3)
## 花片朝向在灌木表面法线和正上方之间的偏向，0 贴合表面，1 全部朝上。
@export var bloom_face_up := 0.35

@export_group("包边")
@export var stone_mesh: Mesh
@export var stone_material: Material
@export var stone_spacing := 0.28
@export var stone_scale := Vector2(0.8, 1.25)
## 石块颜色（sRGB），每块随机取一个。
@export var stone_colors := PackedColorArray([Color(0.72, 0.7, 0.66), Color(0.64, 0.62, 0.58), Color(0.78, 0.74, 0.66)])

@export_group("")
@export_tool_button("重新生成") var rebuild_action := _rebuild


func _ready() -> void:
	_rebuild()


func _rebuild() -> void:
	for child in get_children():
		if child.has_meta("generated"):
			remove_child(child)
			child.queue_free()
	if not is_inside_tree():
		return
	var rng := RandomNumberGenerator.new()
	rng.seed = random_seed
	var inv := global_transform.affine_inverse()
	var shrubs: Array[Transform3D] = []
	var shrub_custom := PackedColorArray()
	var blooms: Array[Transform3D] = []
	var bloom_custom := PackedColorArray()
	var stones: Array[Transform3D] = []
	var stone_tints := PackedColorArray()

	for region in Regions.collect(self, areas):
		var bounds: Rect2 = region.bounds
		var placed := []
		var attempts := int(bounds.get_area() * 40.0)
		for i in attempts:
			var p := Vector2(rng.randf_range(bounds.position.x, bounds.end.x), rng.randf_range(bounds.position.y, bounds.end.y))
			var r := rng.randf_range(shrub_radius.x, shrub_radius.y)
			if not Regions.inside_any(p, [region]) or Regions.distance_to_edge(p, region) < edge_inset + r * 0.5:
				continue
			var ok := true
			for other in placed:
				if p.distance_to(other[0]) < (r + other[1]) * shrub_spacing:
					ok = false
					break
			if not ok:
				continue
			placed.append([p, r])
			var h := r * shrub_flatten
			var center := Vector3(p.x, global_position.y + h * 0.35, p.y)
			var b := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3(r, h, r))
			shrubs.append(Transform3D(b, inv * center))
			shrub_custom.append(Color(rng.randf(), rng.randf(), rng.randf(), rng.randf()))
			var cos_cap := cos(deg_to_rad(bloom_cap))
			for k in rng.randi_range(blooms_per_shrub.x, blooms_per_shrub.y):
				var ct := lerpf(1.0, cos_cap, rng.randf())
				var st := sqrt(1.0 - ct * ct)
				var phi := rng.randf() * TAU
				var dir := Vector3(st * cos(phi), ct, st * sin(phi))
				var pos := center + Vector3(dir.x * (r + 0.03), dir.y * (h + 0.03), dir.z * (r + 0.03))
				var up := Vector3(dir.x / r, dir.y / h, dir.z / r).normalized().lerp(Vector3.UP, bloom_face_up).normalized()
				var side := up.cross(Vector3.FORWARD if absf(up.z) < 0.9 else Vector3.RIGHT).normalized()
				var bb := Basis(side, up, side.cross(up))
				var s := rng.randf_range(bloom_scale.x, bloom_scale.y)
				bb = Basis(up, rng.randf() * TAU) * bb
				blooms.append(Transform3D(bb.scaled(Vector3.ONE * s), inv * pos))
				bloom_custom.append(Color(rng.randf(), rng.randf(), rng.randf(), rng.randf()))

		var poly: PackedVector2Array = region.polygon
		for i in poly.size():
			var a := poly[i]
			var b := poly[(i + 1) % poly.size()]
			var n := maxi(1, roundi(a.distance_to(b) / stone_spacing))
			for k in n:
				var p := a.lerp(b, (k + rng.randf_range(0.3, 0.7)) / n)
				var s := rng.randf_range(stone_scale.x, stone_scale.y)
				var sb := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3(s, s * rng.randf_range(0.8, 1.1), s * rng.randf_range(0.8, 1.0)))
				stones.append(Transform3D(sb, inv * Vector3(p.x, global_position.y, p.y)))
				stone_tints.append(stone_colors[rng.randi() % stone_colors.size()].srgb_to_linear())

	_add("Shrubs", shrub_mesh, shrub_material, shrubs, shrub_custom, PackedColorArray())
	_add("Blooms", bloom_mesh, bloom_material, blooms, bloom_custom, PackedColorArray())
	_add("Edging", stone_mesh, stone_material, stones, PackedColorArray(), stone_tints)


func _add(node_name: String, mesh: Mesh, material: Material, xforms: Array[Transform3D], custom: PackedColorArray, colors: PackedColorArray) -> void:
	if mesh == null or xforms.is_empty():
		return
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_custom_data = not custom.is_empty()
	mm.use_colors = not colors.is_empty()
	mm.mesh = mesh
	mm.instance_count = xforms.size()
	for i in xforms.size():
		mm.set_instance_transform(i, xforms[i])
		if mm.use_custom_data:
			mm.set_instance_custom_data(i, custom[i])
		if mm.use_colors:
			mm.set_instance_color(i, colors[i])
	var mmi := MultiMeshInstance3D.new()
	mmi.name = node_name
	mmi.multimesh = mm
	mmi.material_override = material
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mmi.set_meta("generated", true)
	add_child(mmi)
