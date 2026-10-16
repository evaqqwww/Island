// 树冠叶片：叶片图集按 alpha 裁剪；颜色 = 图集 × COLOR。
// COLOR = 顶点色（RGB 每片叶子的色差，A 遮蔽）× MultiMesh 实例颜色（forest.gd 写入的每棵树色调）。
// 顶点色 A 是 Blender 里按高度和树冠深度算好的遮蔽；法线已在 Blender 里球形化，受光柔和。
// 叶片双面渲染，背面沿用正面的球形化法线（不翻转朝向树冠内部），避免背面发黑。
// 自定义光照：包裹漫反射让受光柔和；接收的阴影只保留 shadow_strength 的深度，
// 叶片之间互相投下的细碎阴影变浅，树冠成片不斑驳。叶片随风轻摆，越高摆得越多。
// 前景压暗：比对焦平面近 foreground_range.x～y 米的树冠逐渐乘上 foreground_tint，镜头底部的前景树冠更暗更冷，
// 和被照亮的空地拉开层次。对焦距离按相机朝向和对焦点高度现算（环绕相机始终看向对焦点），任何朝向都成立。
shader_type spatial;
render_mode cull_disabled;

uniform sampler2D leaf_atlas : source_color, filter_linear_mipmap, repeat_disable;
uniform float alpha_cut : hint_range(0.0, 1.0) = 0.45;
uniform float ao_strength : hint_range(0.0, 1.0) = 0.85;
uniform float ao_light_affect : hint_range(0.0, 1.0) = 0.45;
uniform float wrap : hint_range(0.0, 1.0) = 0.85;             // 包裹漫反射，越大背光面越亮
uniform float shadow_strength : hint_range(0.0, 1.0) = 1.0;   // 接收阴影的深度，0 不受阴影
uniform vec3 foreground_tint : source_color = vec3(1.0);
uniform vec2 foreground_range = vec2(6.0, 22.0);
uniform float focus_height = 0.5;                             // 对焦点（相机目标）的高度
uniform float wind_strength = 0.05;
uniform float wind_speed = 1.1;
uniform float canopy_height = 4.5;   // 网格局部高度，用来算摆动权重

void vertex() {
	vec3 wp = MODEL_MATRIX[3].xyz;
	float w = clamp(VERTEX.y / canopy_height, 0.0, 1.0);
	float t = TIME * wind_speed;
	VERTEX += vec3(sin(t + wp.x * 0.4 + VERTEX.y), 0.0, cos(t * 0.9 + wp.z * 0.4 + VERTEX.x)) * wind_strength * w;
}

void fragment() {
	if (!FRONT_FACING) {
		NORMAL = -NORMAL;
	}
	vec4 leaf = texture(leaf_atlas, UV);
	vec3 cam = INV_VIEW_MATRIX[3].xyz;
	float focus = (focus_height - cam.y) / min(-INV_VIEW_MATRIX[2].y, -0.05);
	float fg = smoothstep(foreground_range.x, foreground_range.y, focus + VERTEX.z);
	ALBEDO = leaf.rgb * COLOR.rgb * mix(vec3(1.0), foreground_tint, fg);
	ALPHA = leaf.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_cut;
	AO = mix(1.0, COLOR.a, ao_strength);
	AO_LIGHT_AFFECT = ao_light_affect;
	ROUGHNESS = 0.85;
	SPECULAR = 0.2;
}

void light() {
	float ndl = max(0.0, (dot(NORMAL, LIGHT) + wrap) / ((1.0 + wrap) * (1.0 + wrap)));
	DIFFUSE_LIGHT += LIGHT_COLOR * ndl * mix(1.0, ATTENUATION, shadow_strength) / PI;
}
