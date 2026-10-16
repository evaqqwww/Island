@tool
extends Camera3D

## 环绕目标点的相机：左键或单指拖动旋转（水平 360°，俯仰限制在 pitch_limits 内），
## 滚轮缩放，空闲几秒后在当前角度附近来回摆动，F 键开关景深。
## 每帧把到目标点的距离写入景深材质的 focus_distance，保证焦点始终落在目标上。

@export var target := Vector3(0.0, 2.0, 0.0)
@export var distance := 16.0
@export var yaw_deg := 35.0
@export var pitch_deg := 6.0
@export var pitch_limits := Vector2(2.0, 40.0)
@export var distance_limits := Vector2(8.0, 30.0)
@export var sway_degrees := 15.0
@export var sway_period := 24.0
@export var idle_delay := 4.0

@onready var _dof: MeshInstance3D = $DOF

var _dragging := false
var _idle := 0.0
var _sway_time := 0.0


func _ready() -> void:
	_apply()


func _unhandled_input(event: InputEvent) -> void:
	if Engine.is_editor_hint():
		return
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT:
			_dragging = mb.pressed
		elif mb.pressed and mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			distance = clampf(distance * 0.92, distance_limits.x, distance_limits.y)
		elif mb.pressed and mb.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			distance = clampf(distance / 0.92, distance_limits.x, distance_limits.y)
		_idle = 0.0
	elif event is InputEventMouseMotion and _dragging:
		var mm := event as InputEventMouseMotion
		yaw_deg = fposmod(yaw_deg - mm.relative.x * 0.25, 360.0)
		pitch_deg = clampf(pitch_deg + mm.relative.y * 0.2, pitch_limits.x, pitch_limits.y)
		_idle = 0.0
	elif event is InputEventKey and event.pressed and not event.echo:
		if (event as InputEventKey).keycode == KEY_F:
			_dof.visible = not _dof.visible


func _process(delta: float) -> void:
	if Engine.is_editor_hint():
		return
	_idle += delta
	if _idle > idle_delay:
		_sway_time += delta
	_apply()


func _apply() -> void:
	var yaw := deg_to_rad(yaw_deg + sin(_sway_time * TAU / sway_period) * sway_degrees)
	var pitch := deg_to_rad(pitch_deg)
	position = target + Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * distance
	look_at_from_position(position, target, Vector3.UP)
	var mat := _dof.material_override as ShaderMaterial
	if mat:
		mat.set_shader_parameter("focus_distance", distance)
