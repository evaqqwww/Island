// 地面：草叶贴图和泥土贴图（blender/build_grass.py 生成）按世界坐标贴图，按地面遮罩（ground_mask.gdshaderinc）混合，
// 小路、菜园、牧场泥地和花坛露出泥土，交界处草叶和泥土互相穿插。
// 草叶贴图按一张大片噪声分区，一部分区域换用旋转过的贴图，打散重复感又不把草叶糊在一起
// （壳层草 grass.gdshader 用同样的分区，草叶对齐）；再叠加大尺度的明暗斑块；空地之外逐渐压暗，模拟树林下的阴影。
shader_type spatial;

#include "res://shaders/ground_mask.gdshaderinc"

uniform sampler2D grass : source_color, filter_linear_mipmap_anisotropic, repeat_enable;  // RGB 颜色，A 草叶高度
uniform vec3 tint : source_color = vec3(1.0);
uniform float tile_size = 4.0;                 // 一张纹理覆盖的边长（米）
uniform float region_scale = 0.11;             // 贴图朝向分区的频率（每米）
uniform float mip_bias = -0.5;                 // 采样偏向更清晰的一级，远处草叶不被平均掉
uniform vec2 clearing_center = vec2(4.0, -1.7);
uniform vec2 clearing_radii = vec2(10.5, 8.0);
uniform float forest_shade : hint_range(0.0, 1.0) = 0.5;

varying vec3 v_world;

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 p = v_world.xz;
	vec2 uv = p / tile_size;
	mat2 rot = mat2(vec2(0.62, 0.78), vec2(-0.78, 0.62));
	float region = smoothstep(0.4, 0.6, noise(p * region_scale));
	vec4 g = mix(texture(grass, uv, mip_bias), texture(grass, rot * uv + 0.37, mip_bias), region);
	vec4 d = dirt_sample(p);
	vec3 c = mix(g.rgb, d.rgb, dirt_weight(dirt_amount(ground_mask(p), p), g.a, d.a));
	float macro = noise(p * 0.06) * 0.6 + noise(p * 0.17) * 0.4;
	c *= mix(0.88, 1.08, macro);
	float e = length((p - clearing_center) / clearing_radii);
	c *= mix(1.0, forest_shade, smoothstep(1.0, 1.5, e));
	ALBEDO = c * tint;
	ROUGHNESS = 0.95;
	SPECULAR = 0.25;
}
