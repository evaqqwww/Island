extends Node

## 手机浏览器上降低渲染开销，桌面浏览器和编辑器里保持原画质：
## 3D 以较低分辨率渲染再放大（移轴模糊下几乎看不出差别），景深减少采样，阴影贴图缩小、阴影距离缩短。

@export var dof_path: NodePath
@export var sun_path: NodePath
@export var mobile_render_scale := 0.6
@export var mobile_dof_samples := 24
@export var mobile_shadow_size := 2048
@export var mobile_shadow_distance := 75.0


static func is_mobile_web() -> bool:
	return OS.has_feature("web_android") or OS.has_feature("web_ios")


func _ready() -> void:
	if not is_mobile_web():
		return
	var vp := get_viewport()
	vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
	vp.scaling_3d_scale = mobile_render_scale
	var dof := get_node_or_null(dof_path) as GeometryInstance3D
	if dof and dof.material_override is ShaderMaterial:
		(dof.material_override as ShaderMaterial).set_shader_parameter("sample_count", mobile_dof_samples)
	var sun := get_node_or_null(sun_path) as DirectionalLight3D
	if sun:
		sun.directional_shadow_max_distance = mobile_shadow_distance
	RenderingServer.directional_shadow_atlas_set_size(mobile_shadow_size, true)
