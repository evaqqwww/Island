// 木屋上的藤蔓和墙根花丛：颜色和 AO 由 Blender 烘焙进顶点色（RGB 颜色，A 为 AO）。
// UV.x 是摆动权重（茎接近 0，叶尖为 1），UV.y 是每片叶子的随机相位。
shader_type spatial;
render_mode cull_disabled, diffuse_lambert_wrap;

uniform vec3 tint : source_color = vec3(1.0);
uniform float ao_strength : hint_range(0.0, 2.0) = 0.8;
uniform float ao_light_affect : hint_range(0.0, 1.0) = 0.3;
uniform float flutter = 0.015;
uniform float flutter_speed = 2.5;

void vertex() {
	vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float phase = UV.y * 6.2831;
	vec3 offset = vec3(
		sin(TIME * flutter_speed + phase + wp.y * 2.0),
		sin(TIME * flutter_speed * 1.3 + phase * 1.7) * 0.6,
		cos(TIME * flutter_speed * 0.9 + phase + wp.x * 2.0));
	VERTEX += offset * flutter * UV.x;
}

void fragment() {
	ALBEDO = COLOR.rgb * tint;
	AO = clamp(1.0 - (1.0 - COLOR.a) * ao_strength, 0.0, 1.0);
	AO_LIGHT_AFFECT = ao_light_affect;
	ROUGHNESS = 0.8;
	SPECULAR = 0.2;
}
