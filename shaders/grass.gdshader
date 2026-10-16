// 壳层草：grass.gd 把同一块网格叠成很多层，UV2.x 是层高（贴地 0 → 草尖 1），顶点按层高抬起。
// 片元把地面切成小格，每格一簇草：随机高度、随机位置，越往上越细；当前层高过了这簇的高度或落在草簇外就丢弃，
// 层层叠起来就是一簇簇有厚度的草。越往上采样点按「梳向」偏移，草叶整片朝同一方向倾斜（方向随位置缓慢变化），
// 斜看时能看到草叶的长度；再叠加随风摆动。颜色从根部的暗绿过渡到草尖的黄绿，大片噪声让草坪有高低和深浅的起伏。
// 遮罩贴图（grass.gd 运行时生成）决定哪里长草，边缘按插值逐渐变矮。
// 变化缓慢的大片噪声、梳向和风在顶点里算（网格每米一个顶点），片元只做每簇草的随机数，减轻手机上的开销。
shader_type spatial;
render_mode cull_back, diffuse_lambert_wrap;

uniform sampler2D mask : hint_default_black, filter_linear;
uniform vec4 mask_rect = vec4(0.0, 0.0, 1.0, 1.0);   // 遮罩覆盖的世界 XZ 范围：起点 xy，尺寸 zw
uniform float height = 0.32;                          // 最高的草有多高（米）
uniform float density = 7.0;                          // 每米多少簇
uniform float thickness : hint_range(0.1, 1.0) = 0.8; // 草簇根部直径（相对格子）
uniform float lean = 0.12;                            // 草尖相对根部的偏移（米）
uniform float lean_scale = 0.15;                      // 梳向变化的频率（每米）
uniform vec3 root_color : source_color = vec3(0.3, 0.45, 0.12);
uniform vec3 tip_color : source_color = vec3(0.68, 0.82, 0.32);
uniform vec3 patch_color : source_color = vec3(0.82, 0.84, 0.4);  // 草坪里偏黄的大片
uniform float patch_scale = 0.22;                     // 大片起伏的频率（每米）
uniform float wind_strength = 0.05;
uniform float wind_speed = 1.3;

varying vec3 v_world;
varying float v_h;
varying vec2 v_bend;
varying float v_clump;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

vec2 hash2(vec2 p) {
	return fract(sin(vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)))) * 43758.5453);
}

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

void vertex() {
	v_h = UV2.x;
	VERTEX.y += v_h * height;
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec2 p = v_world.xz;
	v_clump = noise(p * patch_scale) * 0.7 + noise(p * patch_scale * 3.1) * 0.3;
	float a = noise(p * lean_scale + 11.0) * 6.2832;
	v_bend = vec2(cos(a), sin(a)) * lean
			+ vec2(sin(TIME * wind_speed + p.x * 0.4 + p.y * 0.25), cos(TIME * wind_speed * 0.7 + p.y * 0.35 + p.x * 0.1)) * wind_strength;
}

void fragment() {
	float h = v_h;
	vec2 p = v_world.xz;
	float m = texture(mask, (p - mask_rect.xy) / mask_rect.zw).r;
	float clump = v_clump;
	vec2 g = (p - v_bend * h * h) * density;
	vec2 cell = floor(g);
	float blade = mix(0.35, 1.0, hash(cell + 7.13)) * smoothstep(0.1, 0.9, m) * mix(0.65, 1.15, clump);
	if (h > blade) {
		discard;
	}
	float t = h / blade;
	vec2 d = fract(g) - (0.3 + hash2(cell) * 0.4);
	if (length(d) > thickness * 0.5 * (1.0 - t * 0.85)) {
		discard;
	}
	vec3 tip = mix(tip_color, patch_color, smoothstep(0.5, 0.85, clump));
	ALBEDO = mix(root_color, tip, smoothstep(0.0, 1.0, t)) * mix(0.88, 1.08, hash(cell + 3.7));
	ROUGHNESS = 0.9;
	SPECULAR = 0.2;
}
