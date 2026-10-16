// 全屏景深后处理。
// 挂在相机子节点的 2x2 QuadMesh 上，顶点直接输出到裁剪空间，覆盖整个画面。
// 按深度算出弥散圆半径（CoC），再在半径内做金角螺旋采样。
// 先在周围探测更近且更模糊的前景，让前景轮廓可以溢出到清晰区域。
// Compatibility 渲染器的屏幕纹理没有 mipmap，所以每个像素随机旋转螺旋，把重影打散成细颗粒。
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, depth_test_disabled, shadows_disabled, ambient_light_disabled, fog_disabled;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear, repeat_disable;
uniform sampler2D depth_tex : hint_depth_texture, filter_nearest, repeat_disable;

uniform float focus_distance = 16.0;   // 对焦距离（米），由相机脚本每帧写入
uniform float focus_range = 1.5;       // 对焦平面前后保持清晰的范围（米）
uniform float blur_strength = 80.0;    // 模糊强度：CoC = (|深度 - 对焦距离| - 清晰范围) / 深度 × 强度（短边 1080 像素时）
uniform float max_radius = 48.0;       // 短边 1080 像素时的最大模糊半径
uniform int sample_count : hint_range(8, 96) = 40;
uniform bool show_coc = false;         // 调焦用：把模糊半径显示成灰度

float linear_depth(vec2 uv, mat4 inv_proj) {
	float d = textureLod(depth_tex, uv, 0.0).r;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	vec3 ndc = vec3(uv, d) * 2.0 - 1.0;
#else
	vec3 ndc = vec3(uv * 2.0 - 1.0, d);
#endif
	vec4 view = inv_proj * vec4(ndc, 1.0);
	return -view.z / view.w;
}

float coc(float depth, float scale) {
	float c = max(abs(depth - focus_distance) - focus_range, 0.0) / max(depth, 0.01);
	return min(c * blur_strength, max_radius) * scale;
}

void vertex() {
	POSITION = vec4(VERTEX.xy, 0.5, 1.0);
}

void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 px = 1.0 / VIEWPORT_SIZE;
	float scale = min(VIEWPORT_SIZE.x, VIEWPORT_SIZE.y) / 1080.0;
	float max_r = max_radius * scale;
	float noise = fract(52.9829189 * fract(dot(FRAGCOORD.xy, vec2(0.06711056, 0.00583715))));

	vec3 base = textureLod(screen_tex, uv, 0.0).rgb;
	float d0 = linear_depth(uv, INV_PROJECTION_MATRIX);
	float c0 = coc(d0, scale);

	float radius = c0;
	for (int i = 0; i < 12; i++) {
		float ring = i < 6 ? 0.4 : 0.85;
		float a = float(i) * 1.0472 + (i < 6 ? 0.0 : 0.5236) + noise;
		vec2 suv = uv + vec2(cos(a), sin(a)) * ring * max_r * px;
		float ds = linear_depth(suv, INV_PROJECTION_MATRIX);
		if (ds < d0) {
			radius = max(radius, coc(ds, scale));
		}
	}
	radius = min(radius, max_r);

	vec3 col = base;
	if (radius > 0.75) {
		float n = float(sample_count);
		vec3 acc = vec3(0.0);
		for (int i = 0; i < sample_count; i++) {
			float fi = float(i) + noise;
			float r = sqrt(fi / n) * radius;
			float a = fi * 2.39996323 + noise * 6.2831853;
			vec2 suv = uv + vec2(cos(a), sin(a)) * r * px;
			float ds = linear_depth(suv, INV_PROJECTION_MATRIX);
			// 背后的模糊不能盖过更清晰的当前像素
			float eff = ds > d0 ? min(coc(ds, scale), c0) : coc(ds, scale);
			float w = clamp(eff - r + 1.0, 0.0, 1.0);
			acc += mix(base, textureLod(screen_tex, suv, 0.0).rgb, w);
		}
		col = acc / n;
	}

	ALBEDO = show_coc ? vec3(c0 / max_r) : col;
}
