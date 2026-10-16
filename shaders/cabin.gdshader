// 木屋低模：使用 Blender 从高模烘焙的颜色图、法线图和 AO 图（同一套 UV）。
// 法线图让平的屋面板和墙面恢复瓦片倾斜、木构侧面的受光变化。
// AO 除了压暗环境光，还按 ao_light_affect 部分压暗直射光，让缝隙和墙根在阳光下也有层次。
shader_type spatial;

uniform sampler2D albedo_map : source_color, hint_default_white, filter_linear_mipmap_anisotropic;
uniform sampler2D normal_map : hint_normal, filter_linear_mipmap;
uniform float normal_strength : hint_range(0.0, 2.0) = 1.0;
uniform sampler2D ao_map : hint_default_white, filter_linear_mipmap;
uniform vec3 tint : source_color = vec3(1.0);
uniform float ao_strength : hint_range(0.0, 2.0) = 1.0;
uniform float ao_light_affect : hint_range(0.0, 1.0) = 0.5;
uniform float roughness : hint_range(0.0, 1.0) = 0.85;

void fragment() {
	ALBEDO = texture(albedo_map, UV).rgb * tint;
	NORMAL_MAP = texture(normal_map, UV).rgb;
	NORMAL_MAP_DEPTH = normal_strength;
	float ao = texture(ao_map, UV).r;
	AO = clamp(1.0 - (1.0 - ao) * ao_strength, 0.0, 1.0);
	AO_LIGHT_AFFECT = ao_light_affect;
	ROUGHNESS = roughness;
	SPECULAR = 0.3;
}
