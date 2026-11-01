extends SceneTree
## Prints the bounds of one node of a scene as JSON (helper of scripts/godot_place.py).
##
##   godot --headless --path <project> --script <skill>/scripts/godot/aabb.gd -- <res://scene> <node path>
##
## The scene is instantiated but never added to the tree, so no game script's _ready runs.
## Transforms are chained by hand from the node up to the scene root. The node's bounds are the
## merge of its own visual AABB and those of its visible VisualInstance3D descendants, measured
## in the node's own axes. "size" is that local size times the node's global scale, "yaw_deg"
## comes from the global basis. "collisions" lists every enabled CollisionShape3D under the node
## ({"path" from the scene root, "shape" class, "size" in the node's axes times its global scale}),
## so the plan can warn when the kept collision no longer fits the new model.
## Output: one line "TRIPO_JSON:{...}" on stdout. Exit 0 ok, 3 scene/node not found, 5 nothing
## measurable under the node.

const MARK := "TRIPO_JSON:"


func _emit(data: Dictionary, code: int) -> void:
	print(MARK + JSON.stringify(data))
	quit(code)


func _v(v: Vector3) -> Array:
	return [snappedf(v.x, 0.000001), snappedf(v.y, 0.000001), snappedf(v.z, 0.000001)]


## Transform of `node` relative to `top` (an ancestor or the node itself).
func _rel(node: Node, top: Node) -> Transform3D:
	var t := Transform3D.IDENTITY
	var n := node
	while n != top and n != null:
		if n is Node3D:
			t = (n as Node3D).transform * t
		n = n.get_parent()
	return t


func _visible_up_to(node: Node, top: Node) -> bool:
	var n := node
	while n != null:
		if n is Node3D and not (n as Node3D).visible:
			return false
		if n == top:
			return true
		n = n.get_parent()
	return true


func _collect(node: Node, top: Node, acc: Array) -> void:
	if node is VisualInstance3D and _visible_up_to(node, top):
		var box := (node as VisualInstance3D).get_aabb()
		if box.size != Vector3.ZERO:
			acc.append(_rel(node, top) * box)
	for c in node.get_children():
		_collect(c, top, acc)


## AABB of a shape in its own CollisionShape3D space.
func _shape_aabb(s: Shape3D) -> AABB:
	if s is BoxShape3D:
		var sz: Vector3 = (s as BoxShape3D).size
		return AABB(-sz / 2.0, sz)
	if s is SphereShape3D:
		var r: float = (s as SphereShape3D).radius
		return AABB(Vector3(-r, -r, -r), Vector3(2 * r, 2 * r, 2 * r))
	if s is CapsuleShape3D:
		var cr: float = (s as CapsuleShape3D).radius
		var ch: float = (s as CapsuleShape3D).height
		return AABB(Vector3(-cr, -ch / 2.0, -cr), Vector3(2 * cr, ch, 2 * cr))
	if s is CylinderShape3D:
		var yr: float = (s as CylinderShape3D).radius
		var yh: float = (s as CylinderShape3D).height
		return AABB(Vector3(-yr, -yh / 2.0, -yr), Vector3(2 * yr, yh, 2 * yr))
	var m := s.get_debug_mesh()
	return m.get_aabb() if m != null else AABB()


func _collect_shapes(node: Node, top: Node, root: Node, scale: Vector3, acc: Array) -> void:
	if node is CollisionShape3D:
		var cs := node as CollisionShape3D
		if cs.shape != null and not cs.disabled:
			var box: AABB = _rel(cs, top) * _shape_aabb(cs.shape)
			acc.append({"path": String(root.get_path_to(cs)), "shape": cs.shape.get_class(),
				"size": _v(box.size * scale), "local_size": _v(box.size)})
	for c in node.get_children():
		_collect_shapes(c, top, root, scale, acc)


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 2:
		_emit({"error": "usage: aabb.gd -- <res://scene> <node path>"}, 2)
		return
	var scene_path: String = args[0]
	if not ResourceLoader.exists(scene_path):
		_emit({"error": "scene not found: %s" % scene_path}, 3)
		return
	var packed := load(scene_path) as PackedScene
	if packed == null:
		_emit({"error": "not a scene: %s" % scene_path}, 3)
		return
	var root := packed.instantiate()
	var node_path: String = args[1]
	var node := root if node_path in [".", ""] else root.get_node_or_null(NodePath(node_path))
	if node == null or not node is Node3D:
		root.free()
		_emit({"error": "node %s not found in %s (or not a Node3D)" % [node_path, scene_path]}, 3)
		return
	var boxes: Array = []
	_collect(node, node, boxes)
	if boxes.is_empty():
		root.free()
		_emit({"error": "node %s has no visible geometry to measure" % node_path}, 5)
		return
	var local: AABB = boxes[0]
	for b in boxes:
		local = local.merge(b)
	var g := _rel(node, null)  # up to and including the scene root
	var scale := g.basis.get_scale().abs()
	var center_l := local.get_center()
	var bottom_l := Vector3(center_l.x, local.position.y, center_l.z)
	var yaw := rad_to_deg(g.basis.orthonormalized().get_euler().y)
	var node_type := node.get_class()
	var shapes: Array = []
	_collect_shapes(node, node, root, scale, shapes)
	root.free()
	_emit({
		"node_type": node_type,
		"size": _v(local.size * scale),
		"center": _v(g * center_l),
		"bottom_center": _v(g * bottom_l),
		"yaw_deg": snappedf(yaw, 0.0001),
		"scale": _v(scale),
		"local_position": _v(local.position),
		"local_size": _v(local.size),
		"local_bottom_center": _v(bottom_l),
		"collisions": shapes,
	}, 0)
