@tool
extends MultiMeshInstance3D

## 在地面上随机撒实例（花、团簇、睡莲等），整片是一个 MultiMesh（一次绘制调用）。
## 区域用平铺在地面上的 CSGPolygon3D 划定：include_areas 为空时撒在 area 矩形内，
## 否则只撒在这些多边形里；落进 exclude_areas 的点会被剔除。
## 改了区域形状后点检查器里的「重新生成」。实例数据在运行时生成，不写进场景文件。

@export var mesh: Mesh
@export var count := 1000
## include_areas 为空时使用的矩形（以本节点为中心，XZ 平面）。
@export var area := Vector2(30.0, 30.0)
@export var include_areas: Array[NodePath] = []
@export var exclude_areas: Array[NodePath] = []
@export var scale_range := Vector2(0.8, 1.2)
## 额外的竖向缩放。
@export var height_range := Vector2(1.0, 1.0)
## 实例原点离地高度，会乘以竖向缩放。
@export var y_offset_range := Vector2(0.0, 0.0)
## 最大随机倾斜角（度）。
@export var max_tilt := 0.0
@export var random_seed := 1
@export_tool_button("重新生成") var rebuild_action := _rebuild


func _ready() -> void:
	_rebuild()


func _validate_property(property: Dictionary) -> void:
	if property.name == "multimesh":
		property.usage &= ~PROPERTY_USAGE_STORAGE


func _rebuild() -> void:
	if not is_inside_tree():
		return
	var includes := Regions.collect(self, include_areas)
	var excludes := Regions.collect(self, exclude_areas)
	var inv := global_transform.affine_inverse()

	var bounds := Rect2(global_position.x - area.x * 0.5, global_position.z - area.y * 0.5, area.x, area.y)
	if not includes.is_empty():
		bounds = Regions.merged_bounds(includes)

	var rng := RandomNumberGenerator.new()
	rng.seed = random_seed
	# 每个实例 16 个 float：3x4 变换矩阵（按行）+ 4 个自定义数据
	var buf := PackedFloat32Array()
	buf.resize(count * 16)
	var n := 0
	var attempts := 0
	while n < count and attempts < count * 4:
		attempts += 1
		var p := Vector2(rng.randf_range(bounds.position.x, bounds.end.x), rng.randf_range(bounds.position.y, bounds.end.y))
		if not includes.is_empty() and not Regions.inside_any(p, includes):
			continue
		if Regions.inside_any(p, excludes):
			continue

		var s := rng.randf_range(scale_range.x, scale_range.y)
		var h := s * rng.randf_range(height_range.x, height_range.y)
		var b := Basis.from_scale(Vector3(s, h, s))
		b = Basis(Vector3.UP, rng.randf() * TAU) * b
		if max_tilt > 0.0:
			var axis := Vector3(rng.randf_range(-1.0, 1.0), 0.0, rng.randf_range(-1.0, 1.0)).normalized()
			if axis != Vector3.ZERO:
				b = Basis(axis, deg_to_rad(rng.randf_range(0.0, max_tilt))) * b
		var origin := inv * Vector3(p.x, global_position.y + rng.randf_range(y_offset_range.x, y_offset_range.y) * h, p.y)

		var o := n * 16
		buf[o] = b.x.x
		buf[o + 1] = b.y.x
		buf[o + 2] = b.z.x
		buf[o + 3] = origin.x
		buf[o + 4] = b.x.y
		buf[o + 5] = b.y.y
		buf[o + 6] = b.z.y
		buf[o + 7] = origin.y
		buf[o + 8] = b.x.z
		buf[o + 9] = b.y.z
		buf[o + 10] = b.z.z
		buf[o + 11] = origin.z
		buf[o + 12] = rng.randf()
		buf[o + 13] = rng.randf()
		buf[o + 14] = rng.randf()
		buf[o + 15] = rng.randf()
		n += 1
	buf.resize(n * 16)

	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_custom_data = true
	mm.mesh = mesh
	mm.instance_count = n
	if n > 0:
		mm.buffer = buf
	multimesh = mm
