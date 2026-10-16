// 地面遮罩，地面 ground.gdshader 和壳层草 grass.gdshader 共用，保证两者的草地和泥土边界一致。
// 遮罩贴图由 grass.gd 运行时生成，覆盖世界 XZ 范围 mask_rect：
//   R  能长草（在空地范围内，且不在木屋、池塘等区域里）
//   G  自然泥地（小路、菜园、牧场泥地）的有向距离：边界处 0.5，往里变大、往外变小
//   B  整齐泥地（花坛）：里面 1、外面 0
// 自然泥地的边界叠两层噪声，弯弯曲曲；交界处再按草叶和泥土的高度互相穿插（高度混合），
// 草叶一根根伸进泥地、泥土从草缝里露出来，不是一条平滑的线。花坛不加噪声，边界整齐。

uniform sampler2D mask : hint_default_black, filter_linear;
uniform vec4 mask_rect = vec4(0.0, 0.0, 1.0, 1.0);    // 起点 xy，尺寸 zw
uniform sampler2D dirt : source_color, filter_linear_mipmap_anisotropic, repeat_enable;  // RGB 颜色，A 高度
uniform float dirt_tile = 3.0;                         // 泥土贴图覆盖的边长（米）
uniform float edge_noise = 0.55;                       // 自然泥地边界的噪声幅度（遮罩 G 的单位）
uniform float edge_noise_scale = 1.3;                  // 边界噪声的频率（每米）
uniform float height_blend = 0.6;                      // 交界处草叶和泥土按高度穿插的程度

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

vec3 ground_mask(vec2 p) {
	return texture(mask, (p - mask_rect.xy) / mask_rect.zw).rgb;
}

// 泥土的程度：0 草地，1 泥地，0.5 在边界上
float dirt_amount(vec3 m, vec2 p) {
	float n = noise(p * edge_noise_scale) * 0.65 + noise(p * edge_noise_scale * 3.3 + 17.0) * 0.35;
	float natural = clamp(m.g + (n - 0.5) * 2.0 * edge_noise, 0.0, 1.0);
	return max(natural, smoothstep(0.35, 0.65, m.b));
}

// 某一点显示泥土的权重：泥土程度 + 两边的高度比较
float dirt_weight(float amount, float grass_h, float dirt_h) {
	float d = (amount * 2.0 - 1.0) + height_blend * (dirt_h - grass_h);
	return smoothstep(-0.08, 0.08, d);
}

vec4 dirt_sample(vec2 p) {
	return texture(dirt, p / dirt_tile);
}
