// 蓬松树冠：用世界坐标噪声沿法线推挤球体，打散规则轮廓；颜色按朝向从下到上渐变。
shader_type spatial;
render_mode diffuse_lambert_wrap;

uniform vec3 color_top : source_color = vec3(0.98, 0.64, 0.32);
uniform vec3 color_bottom : source_color = vec3(0.60, 0.25, 0.12);
uniform float noise_amount = 0.22;
uniform float noise_scale = 2.0;
uniform float sway = 0.04;

varying float v_up;

float hash(vec3 p) {
	p = fract(p * 0.3183099 + 0.1);
	p *= 17.0;
	return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float noise(vec3 x) {
	vec3 i = floor(x);
	vec3 f = fract(x);
	f = f * f * (3.0 - 2.0 * f);
	return mix(
		mix(mix(hash(i + vec3(0, 0, 0)), hash(i + vec3(1, 0, 0)), f.x),
			mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
		mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x),
			mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

void vertex() {
	vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float n = noise(wp * noise_scale) * 0.65 + noise(wp * noise_scale * 2.3) * 0.35;
	VERTEX += NORMAL * (n - 0.5) * 2.0 * noise_amount;
	VERTEX.x += sin(TIME * 0.8 + wp.x * 0.3 + wp.z * 0.2) * sway * (NORMAL.y * 0.5 + 0.5);
	v_up = NORMAL.y * 0.5 + 0.5 + (n - 0.5) * 0.3;
}

void fragment() {
	ALBEDO = mix(color_bottom, color_top, smoothstep(0.1, 0.9, v_up));
	ROUGHNESS = 1.0;
	SPECULAR = 0.1;
}
