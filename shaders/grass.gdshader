// 壳层草：grass.gd 把同一块网格叠成几层，UV2.x 是层高（贴地 0 → 草尖 1），顶点按层高抬起。
// 每层采样和地面相同的草叶贴图（A 通道是草叶高度），只保留高过当前层的草叶，叠起来就是从地面贴图里「长」出来的立体草，
// 草叶的形状、朝向和疏密都来自贴图，不按格子排列。分区和贴图朝向与地面 ground.gdshader 一致，草叶对齐。
// 越往上采样点沿梳向偏移一点，草叶有倾斜，再叠加随风摆动；大片噪声让草有高低起伏。
// 地面遮罩（ground_mask.gdshaderinc，与地面共用）决定哪里长草：泥地里没有草，交界处按同样的高度混合，
// 地面上露出泥土的地方草也长不出来，立体草和地面对得上。缓慢变化的量都在顶点里算（网格每米一个顶点）。
shader_type spatial;
render_mode cull_back, diffuse_lambert_wrap;

#include "res://shaders/ground_mask.gdshaderinc"

uniform sampler2D grass : source_color, filter_linear_mipmap_anisotropic, repeat_enable;  // RGB 颜色，A 草叶高度
uniform vec3 tint : source_color = vec3(1.0);         // 与地面一致
uniform float tile_size = 4.0;                        // 与地面一致
uniform float region_scale = 0.11;                    // 与地面一致
uniform float mip_bias = -1.0;                        // 采样偏向更清晰的一级，草叶高度不被平均成一片
uniform float height = 0.18;                          // 最高的草有多高（米）
uniform float tip_light = 0.15;                       // 草尖比贴地处亮多少
uniform float clump_scale = 0.22;                     // 草高起伏的频率（每米）
uniform float lean = 0.06;                            // 草尖相对根部的偏移（米）
uniform float lean_scale = 0.15;                      // 梳向变化的频率（每米）
uniform float wind_strength = 0.03;
uniform float wind_speed = 1.3;

varying vec3 v_world;
varying float v_h;
varying float v_region;
varying float v_clump;
varying vec2 v_bend;

void vertex() {
	v_h = UV2.x;
	VERTEX.y += v_h * height;
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec2 p = v_world.xz;
	v_region = smoothstep(0.4, 0.6, noise(p * region_scale));
	v_clump = mix(0.75, 1.2, noise(p * clump_scale) * 0.7 + noise(p * clump_scale * 3.1) * 0.3);
	float a = noise(p * lean_scale + 11.0) * 6.2832;
	v_bend = vec2(cos(a), sin(a)) * lean
			+ vec2(sin(TIME * wind_speed + p.x * 0.4 + p.y * 0.25), cos(TIME * wind_speed * 0.7 + p.y * 0.35 + p.x * 0.1)) * wind_strength;
}

void fragment() {
	float h = v_h;
	vec2 q = v_world.xz - v_bend * h;   // 这根草叶的根部
	vec2 uv = q / tile_size;
	mat2 rot = mat2(vec2(0.62, 0.78), vec2(-0.78, 0.62));
	vec4 g = mix(texture(grass, uv, mip_bias), texture(grass, rot * uv + 0.37, mip_bias), v_region);
	vec3 m = ground_mask(q);
	float grass_here = smoothstep(0.1, 0.9, m.r) * (1.0 - dirt_weight(dirt_amount(m, q), g.a, dirt_sample(q).a));
	if (h > g.a * grass_here * v_clump) {
		discard;
	}
	ALBEDO = g.rgb * tint * (1.0 + tip_light * h);
	ROUGHNESS = 0.9;
	SPECULAR = 0.2;
}
