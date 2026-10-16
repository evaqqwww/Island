// 草坪地面：可平铺的草叶贴图（blender/build_grass.py 生成）按世界坐标贴图。按一张大片噪声分区，
// 一部分区域换用旋转过的贴图，打散重复感又不把草叶糊在一起（壳层草 grass.gdshader 用同样的分区，草叶对齐）；
// 再叠加大尺度的明暗斑块；空地之外逐渐压暗，模拟树林下的阴影。
shader_type spatial;

uniform sampler2D grass : source_color, filter_linear_mipmap_anisotropic, repeat_enable;  // RGB 颜色，A 草叶高度（这里不用）
uniform vec3 tint : source_color = vec3(1.0);
uniform float tile_size = 4.0;                 // 一张纹理覆盖的边长（米）
uniform float region_scale = 0.11;             // 贴图朝向分区的频率（每米）
uniform float mip_bias = -0.5;                 // 采样偏向更清晰的一级，远处草叶不被平均掉
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
	float region = smoothstep(0.4, 0.6, noise(v_world.xz * region_scale));
	vec3 c = mix(texture(grass, uv, mip_bias).rgb, texture(grass, rot * uv + 0.37, mip_bias).rgb, region);
	float macro = noise(v_world.xz * 0.06) * 0.6 + noise(v_world.xz * 0.17) * 0.4;
	c *= mix(0.88, 1.08, macro);
	float e = length((v_world.xz - clearing_center) / clearing_radii);
	c *= mix(1.0, forest_shade, smoothstep(1.0, 1.5, e));
	ALBEDO = c * tint;
	ROUGHNESS = 0.95;
	SPECULAR = 0.25;
}
