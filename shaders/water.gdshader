// 占位池塘水面：深浅两色按菲涅尔混合，叠加两组正弦波纹扰动法线。
shader_type spatial;

uniform vec3 deep_color : source_color = vec3(0.08, 0.20, 0.22);
uniform vec3 shallow_color : source_color = vec3(0.30, 0.48, 0.42);
uniform float ripple_scale = 3.0;
uniform float ripple_strength = 0.12;
uniform float ripple_speed = 1.0;

void fragment() {
	vec3 wp = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float t = TIME * ripple_speed;
	vec2 slope = vec2(
		cos(wp.x * ripple_scale + t) + 0.6 * cos((wp.x + wp.z) * ripple_scale * 1.7 - t * 1.3),
		cos(wp.z * ripple_scale * 1.3 - t * 0.8) + 0.6 * cos((wp.x - wp.z) * ripple_scale * 1.9 + t * 1.1)
	) * ripple_strength;
	vec3 n = normalize(vec3(-slope.x, 1.0, -slope.y));
	NORMAL = normalize((VIEW_MATRIX * vec4(n, 0.0)).xyz);
	float fresnel = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
	ALBEDO = mix(deep_color, shallow_color, fresnel);
	ROUGHNESS = 0.08;
	SPECULAR = 0.6;
}
