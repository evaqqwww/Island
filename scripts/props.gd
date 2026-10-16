@tool
extends MultiMeshInstance3D

## 按固定位置摆放同一个网格的多个实例（菜畦、奶牛、围栏等），整组是一个 MultiMesh（一次绘制调用）。
## 网格取自 source 场景（Blender 导出的 glb）里名为 mesh_name 的 MeshInstance3D。
## placements 每项是 (x, z, 朝向角度, 缩放)，坐标相对本节点。
## 改了参数后点检查器里的「重新生成」。实例数据在运行时生成，不写进场景文件。

@export var source: PackedScene
@export var mesh_name := ""
@export var placements := PackedVector4Array()
@export_tool_button("重新生成") var rebuild_action := _rebuild


func _ready() -> void:
	_rebuild()


func _validate_property(property: Dictionary) -> void:
	if property.name == "multimesh":
		property.usage &= ~PROPERTY_USAGE_STORAGE


func _rebuild() -> void:
	if source == null:
		return
	var scene := source.instantiate()
	var mi := scene.find_child(mesh_name, true, false) as MeshInstance3D
	var mesh: Mesh = mi.mesh if mi else null
	scene.free()
	if mesh == null:
		push_warning("%s：%s 里没有网格 %s" % [name, source.resource_path, mesh_name])
		return

	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = placements.size()
	for i in placements.size():
		var p := placements[i]
		var b := Basis(Vector3.UP, deg_to_rad(p.z)).scaled(Vector3.ONE * p.w)
		mm.set_instance_transform(i, Transform3D(b, Vector3(p.x, 0.0, p.y)))
	multimesh = mm
