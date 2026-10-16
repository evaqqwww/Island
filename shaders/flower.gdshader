// 占位花卉（花穗、小花、花瓣、睡莲叶）：配合 scatter.gd 使用。
// 每个实例在 color_a 和 color_b 之间随机取色（INSTANCE_CUSTOM.r）；
// mesh_height 是 mesh 的局部高度（原点在中心），用来算从底部到顶部的渐变，底部 base_fraction 显示为茎叶色。
shader_type spatial;
render_mode cull_disabled;

uniform vec3 color_a : source_color = vec3(0.62, 0.42, 0.85);
uniform vec3 color_b : source_color = vec3(0.92, 0.55, 0.78);
uniform vec3 base_color : source_color = vec3(0.22, 0.40, 0.14);
uniform float base_fraction : hint_range(0.0, 1.0) = 0.0;
uniform float mesh_height = 1.0;
uniform float floret_bumps = 0.0;   // 花穗表面的颗粒起伏
uniform float sway = 0.03;

varying float v_t;
varying float v_var;

void vertex() {
	v_t = clamp(VERTEX.y / mesh_height + 0.5, 0.0, 1.0);
	v_var = INSTANCE_CUSTOM.r;
	VERTEX += NORMAL * sin(VERTEX.y * 60.0 + atan(VERTEX.z, VERTEX.x) * 3.0) * floret_bumps;
	vec3 wp = MODEL_MATRIX[3].xyz;
	VERTEX.x += sin(TIME * 1.3 + wp.x * 0.7 + wp.z * 0.5 + INSTANCE_CUSTOM.g * 6.2831) * sway * v_t;
}

void fragment() {
	vec3 flower = mix(color_a, color_b, v_var);
	float stem = smoothstep(base_fraction, base_fraction + 0.08, v_t);
	ALBEDO = mix(base_color, flower, stem) * mix(0.75, 1.0, v_t);
	ROUGHNESS = 0.8;
	SPECULAR = 0.2;
}
