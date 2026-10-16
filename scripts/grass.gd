@tool
extends MeshInstance3D

## 草地：在 area 多边形（外扩 margin 米，伸进林缘树冠下）上叠 shell_count 层水平网格（壳层草），
## grass.gdshader 按地面草叶贴图的高度通道，把高过每层的草叶抬起来，叠出有厚度、会随风摆动的草坪。
## exclude_areas（小路、池塘、菜园、泥地、花圃、木屋）不长草：运行时把区域画成遮罩贴图传给着色器，
## 遮罩按双线性插值采样，区域边缘的草逐渐变矮。只在有草的格子里生成网格，减少重叠绘制。
## 网格和遮罩在运行时生成，不写进场景文件。改了区域或参数后点「重新生成」。

@export var area: NodePath
@export var exclude_areas: Array[NodePath] = []
## area 向外扩展的距离（米），让草一直长到林缘的树冠下面。
@export var margin := 1.5
@export var shell_count := 5
## 每层网格的格子边长（米）。
@export var cell_size := 1.0
## 遮罩贴图每个像素对应的边长（米）。
@export var mask_resolution := 0.15
@export_tool_button("重新生成") var rebuild_action := _rebuild


func _ready() -> void:
	_rebuild()


func _validate_property(property: Dictionary) -> void:
	if property.name == "mesh":
		property.usage &= ~PROPERTY_USAGE_STORAGE


func _rebuild() -> void:
	mesh = null
	var base := Regions.from_node(get_node_or_null(area))
	var mat := material_override as ShaderMaterial
	if base.is_empty() or mat == null or shell_count < 1:
		return
	var grown := Geometry2D.offset_polygon(base.polygon, margin, Geometry2D.JOIN_ROUND)
	if grown.is_empty():
		return
	var region := {"polygon": grown[0], "bounds": Rect2()}
	var bounds := Rect2(grown[0][0], Vector2.ZERO)
	for v in grown[0]:
		bounds = bounds.expand(v)
	region.bounds = bounds
	var excludes := Regions.collect(self, exclude_areas)

	# 遮罩：有草为 1，没草为 0
	var w := ceili(bounds.size.x / mask_resolution) + 1
	var h := ceili(bounds.size.y / mask_resolution) + 1
	var pixels := PackedByteArray()
	pixels.resize(w * h)
	for y in h:
		for x in w:
			var p := bounds.position + Vector2(x, y) * mask_resolution
			var grass := Regions.inside_any(p, [region]) and not Regions.inside_any(p, excludes)
			pixels[y * w + x] = 255 if grass else 0
	var image := Image.create_from_data(w, h, false, Image.FORMAT_L8, pixels)
	mat.set_shader_parameter("mask", ImageTexture.create_from_image(image))
	# 像素中心对齐：第 0 个像素的中心在 bounds.position
	var half := Vector2.ONE * mask_resolution * 0.5
	mat.set_shader_parameter("mask_rect", Vector4(bounds.position.x - half.x, bounds.position.y - half.y,
			w * mask_resolution, h * mask_resolution))

	# 网格：只保留四角或中心有草的格子；层从上往下排
	var inv := global_transform.affine_inverse()
	var cells: Array[Vector2] = []
	var nx := ceili(bounds.size.x / cell_size)
	var nz := ceili(bounds.size.y / cell_size)
	for iz in nz:
		for ix in nx:
			var c := bounds.position + Vector2(ix, iz) * cell_size
			for s in [Vector2(0, 0), Vector2(1, 0), Vector2(0, 1), Vector2(1, 1), Vector2(0.5, 0.5)]:
				var q: Vector2 = (c + s * cell_size - bounds.position) / mask_resolution
				var px := clampi(roundi(q.x), 0, w - 1)
				var pz := clampi(roundi(q.y), 0, h - 1)
				if pixels[pz * w + px] > 0:
					cells.append(c)
					break

	var verts := PackedVector3Array()
	var uv2 := PackedVector2Array()
	var normals := PackedVector3Array()
	var indices := PackedInt32Array()
	for layer in range(shell_count, 0, -1):
		var t := float(layer) / shell_count
		for c in cells:
			var i := verts.size()
			for s in [Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)]:
				var p: Vector2 = c + s * cell_size
				verts.append(inv * Vector3(p.x, global_position.y, p.y))
				uv2.append(Vector2(t, 0.0))
				normals.append(Vector3.UP)
			indices.append_array([i, i + 1, i + 2, i, i + 2, i + 3])
	if verts.is_empty():
		return
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV2] = uv2
	arrays[Mesh.ARRAY_INDEX] = indices
	var am := ArrayMesh.new()
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var height: float = mat.get_shader_parameter("height") if mat.get_shader_parameter("height") != null else 0.3
	var aabb := am.get_aabb()
	aabb.size.y = height + 0.1
	am.custom_aabb = aabb
	mesh = am
