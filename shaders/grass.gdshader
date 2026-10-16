// 草叶：UV.y 从根部 0 到叶尖 1。
// INSTANCE_CUSTOM.r 控制颜色变化，INSTANCE_CUSTOM.g 是风的相位。
// 法线统一朝上，让整片草像绒毯一样柔和受光。
shader_type spatial;
render_mode cull_disabled, world_vertex_coords;

uniform vec3 root_color : source_color = vec3(0.30, 0.15, 0.06);
uniform vec3 tip_color : source_color = vec3(0.98, 0.68, 0.36);
uniform vec3 tip_color_alt : source_color = vec3(0.90, 0.44, 0.24);
uniform float tip_glow = 0.10;
uniform vec2 wind_direction = vec2(1.0, 0.35);
uniform float wind_strength = 0.10;
uniform float wind_speed = 1.4;
uniform float wind_scale = 0.18;

varying float v_height;
varying float v_variation;

void vertex() {
	float h = UV.y;
	v_height = h;
	v_variation = INSTANCE_CUSTOM.r;

	vec2 dir = normalize(wind_direction);
	float along = dot(VERTEX.xz, dir);
	float wave = sin(TIME * wind_speed + along * wind_scale * 6.2831 + INSTANCE_CUSTOM.g * 6.2831);
	float gust = sin(TIME * wind_speed * 0.37 + along * wind_scale * 1.7) * 0.5 + 0.5;
	VERTEX.xz += dir * (wave * 0.35 + gust * 0.65) * wind_strength * h * h;
}

void fragment() {
	vec3 tip = mix(tip_color, tip_color_alt, v_variation);
	vec3 c = mix(root_color, tip, smoothstep(0.0, 1.0, v_height));
	ALBEDO = c * mix(0.85, 1.1, fract(v_variation * 7.31));
	NORMAL = normalize((VIEW_MATRIX * vec4(0.0, 1.0, 0.0, 0.0)).xyz);
	ROUGHNESS = 0.9;
	SPECULAR = 0.15;
	EMISSION = tip * tip_glow * v_height * v_height;
}
