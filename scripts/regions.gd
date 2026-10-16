class_name Regions
extends RefCounted

## 地面区域工具：把平铺在地面上的 CSGPolygon3D 换算成世界 XZ 平面的多边形，
## 供撒点和种树判断点在不在区域里、离区域边缘多远。
## 每个区域是 {"polygon": PackedVector2Array, "bounds": Rect2}。


static func from_node(node: Node) -> Dictionary:
	var csg := node as CSGPolygon3D
	if csg == null or csg.polygon.size() < 3:
		return {}
	var poly := PackedVector2Array()
	for v in csg.polygon:
		var w := csg.global_transform * Vector3(v.x, v.y, 0.0)
		poly.append(Vector2(w.x, w.z))
	var bounds := Rect2(poly[0], Vector2.ZERO)
	for v in poly:
		bounds = bounds.expand(v)
	return {"polygon": poly, "bounds": bounds}


static func collect(owner: Node, paths: Array[NodePath]) -> Array:
	var result := []
	for path in paths:
		var area := from_node(owner.get_node_or_null(path))
		if not area.is_empty():
			result.append(area)
	return result


static func inside_any(p: Vector2, areas: Array) -> bool:
	for a in areas:
		if a.bounds.has_point(p) and Geometry2D.is_point_in_polygon(p, a.polygon):
			return true
	return false


static func merged_bounds(areas: Array) -> Rect2:
	var bounds: Rect2 = areas[0].bounds
	for a in areas:
		bounds = bounds.merge(a.bounds)
	return bounds


static func distance_to_edge(p: Vector2, area: Dictionary) -> float:
	var poly: PackedVector2Array = area.polygon
	var best := INF
	for i in poly.size():
		var q := Geometry2D.get_closest_point_to_segment(p, poly[i], poly[(i + 1) % poly.size()])
		best = minf(best, p.distance_to(q))
	return best
