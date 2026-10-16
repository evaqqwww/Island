// 烟囱的烟：一条始终朝向相机（绕竖直轴）的细长条带，向上变宽、左右摆动、被风吹偏并淡出。
// 网格用竖直细分的 QuadMesh；节点原点放在烟囱口，烟从原点向上长 height 米。
// 材质的 render_priority 要高于景深后处理，烟画在景深之后，不会被景深覆盖。
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled, fog_disabled;

uniform float height = 3.5;
uniform float width_bottom = 0.05;
uniform float width_top = 0.2;
uniform float wave_amplitude = 0.3;
uniform float wave_length = 1.4;
uniform float wave_speed = 0.8;
uniform vec2 drift = vec2(0.5, -0.2);   // 顶端被风吹偏的距离（世界 XZ）
uniform vec4 color : source_color = vec4(1.0, 0.98, 0.95, 0.85);

varying float v_t;

void vertex() {
	float t = 1.0 - UV.y;   // QuadMesh 的 UV.y 顶端为 0
	v_t = t;
	float side = UV.x * 2.0 - 1.0;
	vec3 base = MODEL_MATRIX[3].xyz;
	vec3 right = normalize(vec3(INV_VIEW_MATRIX[0].x, 0.0, INV_VIEW_MATRIX[0].z));
	float y = t * height;
	float sway = sin(y / wave_length * 6.2831 - TIME * wave_speed * 6.2831) * wave_amplitude * smoothstep(0.0, 0.6, t);
	float w = mix(width_bottom, width_top, t);
	vec3 world = base + vec3(0.0, y, 0.0) + right * (side * w * 0.5 + sway) + vec3(drift.x, 0.0, drift.y) * t * t;
	POSITION = PROJECTION_MATRIX * VIEW_MATRIX * vec4(world, 1.0);
}

void fragment() {
	float edge = 1.0 - pow(abs(UV.x * 2.0 - 1.0), 2.0);
	float fade = smoothstep(0.0, 0.06, v_t) * (1.0 - smoothstep(0.5, 1.0, v_t));
	ALBEDO = color.rgb;
	ALPHA = color.a * edge * fade;
}
