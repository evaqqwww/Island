extends Label

## 左上角显示帧率、3D 渲染倍率（低于 1 时）和操作提示；触屏设备只提示拖动。


func _process(_delta: float) -> void:
	var parts := ["FPS %d" % Engine.get_frames_per_second()]
	var render_scale := get_viewport().scaling_3d_scale
	if render_scale < 1.0:
		parts.append("3D x%.1f" % render_scale)
	parts.append("drag: orbit" if DisplayServer.is_touchscreen_available() else "drag: orbit   wheel: zoom   F: toggle DOF")
	text = "   |   ".join(parts)
