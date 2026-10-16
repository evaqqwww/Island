// 树冠叶片：叶片图集按 alpha 裁剪；颜色 = 图集 × COLOR。
// COLOR = 顶点色（RGB 每片叶子的色差，A 遮蔽）× MultiMesh 实例颜色（forest.gd 写入的每棵树色调）。
// 顶点色 A 是 Blender 里按高度和树冠深度算好的遮蔽；法线已在 Blender 里球形化，受光柔和。
// 叶片随风轻摆，越高摆得越多。
shader_type spatial;
render_mode cull_disabled, diffuse_lambert_wrap;

uniform sampler2D leaf_atlas : source_color, filter_linear_mipmap, repeat_disable;
uniform float alpha_cut : hint_range(0.0, 1.0) = 0.45;
uniform float ao_strength : hint_range(0.0, 1.0) = 0.85;
uniform float ao_light_affect : hint_range(0.0, 1.0) = 0.45;
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
	vec4 leaf = texture(leaf_atlas, UV);
	ALBEDO = leaf.rgb * COLOR.rgb;
	ALPHA = leaf.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_cut;
	AO = mix(1.0, COLOR.a, ao_strength);
	AO_LIGHT_AFFECT = ao_light_affect;
	ROUGHNESS = 0.85;
	SPECULAR = 0.2;
}
