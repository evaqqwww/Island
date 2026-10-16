// 草坪地面：可平铺的草坪纹理按世界坐标贴图，两层不同尺度和角度混合以打散重复感，
// 再叠加大尺度的明暗斑块；空地之外逐渐压暗，模拟树林下的阴影。
shader_type spatial;

uniform sampler2D lawn : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec3 tint : source_color = vec3(1.0);
uniform float tile_size = 4.0;                 // 一张纹理覆盖的边长（米）
uniform vec2 clearing_center = vec2(4.0, -1.7);
uniform vec2 clearing_radii = vec2(10.5, 8.0);
uniform float forest_shade : hint_range(0.0, 1.0) = 0.5;

varying vec3 v_world;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 uv = v_world.xz / tile_size;
	mat2 rot = mat2(vec2(0.62, 0.78), vec2(-0.78, 0.62));
	vec3 c = mix(texture(lawn, uv).rgb, texture(lawn, rot * uv * 0.43 + 0.37).rgb, 0.4);
	float macro = noise(v_world.xz * 0.06) * 0.6 + noise(v_world.xz * 0.17) * 0.4;
	c *= mix(0.88, 1.08, macro);
	float e = length((v_world.xz - clearing_center) / clearing_radii);
	c *= mix(1.0, forest_shade, smoothstep(1.0, 1.5, e));
	ALBEDO = c * tint;
	ROUGHNESS = 0.95;
	SPECULAR = 0.25;
}
