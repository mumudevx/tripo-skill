extends SceneTree
## Headless rig acceptance check of one GLB (helper of scripts/godot_place.py, spec section 14.5).
##
##   godot --headless --path <project> --script <skill>/scripts/godot/rig_accept.gd -- <model.glb>
##
## Imports the GLB with Godot's runtime glTF importer (textures discarded: the check needs only
## the skeleton, the skin weights and the animations), then reports:
##   skeletons       number of Skeleton3D nodes
##   bones           bone count of the first skeleton
##   single_root     the first skeleton has exactly one bone without a parent
##   max_influences  most non-zero skin weights on any vertex, over every skinned surface
##   animations      animation names of every AnimationPlayer
##   bonemap_auto    a name-based match of the bones against SkeletonProfileHumanoid. Godot's own
##                   BoneMapper auto-mapping is editor-only, so this is a heuristic; it is reported,
##                   never judged, until the first paid rig run settles the Godot `spec`.
## The verdict is decided by godot_place.py. Output: one line "TRIPO_JSON:{...}" on stdout.
## Exit 0 ok, 3 file not found, 4 import failed.

const MARK := "TRIPO_JSON:"
const WEIGHT_EPS := 0.0001

## Extra spellings per humanoid profile bone (lowercase, separators removed). Mixamo, Unreal,
## Blender Rigify-like and generic names; the profile name itself is always tried first.
const ALIASES := {
	"Hips": ["pelvis", "hip"],
	"Spine": ["spine0", "spine01"],
	"Chest": ["spine1", "spine02", "chest"],
	"UpperChest": ["spine2", "spine03", "upperchest"],
	"Neck": ["neck0", "neck01"],
	"Head": ["head0"],
	"LeftShoulder": ["clavicleleft", "claviclel", "lclavicle", "shoulderl"],
	"RightShoulder": ["clavicleright", "clavicler", "rclavicle", "shoulderr"],
	"LeftUpperArm": ["leftarm", "upperarml", "lupperarm", "arml"],
	"RightUpperArm": ["rightarm", "upperarmr", "rupperarm", "armr"],
	"LeftLowerArm": ["leftforearm", "lowerarml", "forearml", "lforearm"],
	"RightLowerArm": ["rightforearm", "lowerarmr", "forearmr", "rforearm"],
	"LeftHand": ["handl", "lhand"],
	"RightHand": ["handr", "rhand"],
	"LeftUpperLeg": ["leftupleg", "thighl", "lthigh", "upperlegl"],
	"RightUpperLeg": ["rightupleg", "thighr", "rthigh", "upperlegr"],
	"LeftLowerLeg": ["leftleg", "calfl", "lcalf", "shinl", "lowerlegl"],
	"RightLowerLeg": ["rightleg", "calfr", "rcalf", "shinr", "lowerlegr"],
	"LeftFoot": ["footl", "lfoot"],
	"RightFoot": ["footr", "rfoot"],
	"LeftToes": ["lefttoebase", "balll", "toel", "ltoe"],
	"RightToes": ["righttoebase", "ballr", "toer", "rtoe"],
}
const PREFIXES := ["mixamorig", "tripo", "def", "bip01", "armature"]


func _emit(data: Dictionary, code: int) -> void:
	print(MARK + JSON.stringify(data))
	quit(code)


func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)


func _norm(name: String) -> String:
	var s := name.to_lower()
	for sep in [":", "_", "-", ".", " "]:
		s = s.replace(sep, "")
	for p in PREFIXES:
		if s.begins_with(p):
			s = s.substr(p.length())
	return s


func _max_influences(arrays: Array, format: int) -> int:
	var weights = arrays[Mesh.ARRAY_WEIGHTS]
	if weights == null or weights.is_empty():
		return 0
	var per := 8 if (format & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS) != 0 else 4
	var most := 0
	for v in range(weights.size() / per):
		var count := 0
		for k in range(per):
			if weights[v * per + k] > WEIGHT_EPS:
				count += 1
		most = maxi(most, count)
	return most


func _bonemap(sk: Skeleton3D) -> Dictionary:
	var by_norm := {}
	for i in sk.get_bone_count():
		by_norm[_norm(sk.get_bone_name(i))] = sk.get_bone_name(i)
	var profile := SkeletonProfileHumanoid.new()
	var mapped := 0
	var unmapped: Array = []
	for i in profile.bone_size:
		var pname := String(profile.get_bone_name(i))
		var hit := by_norm.has(_norm(pname))
		for alias in ALIASES.get(pname, []):
			hit = hit or by_norm.has(alias)
		if hit:
			mapped += 1
		elif profile.is_required(i):
			unmapped.append(pname)
	return {"method": "name_heuristic", "profile_bones": profile.bone_size,
			"mapped": mapped, "unmapped": unmapped}


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1:
		_emit({"error": "usage: rig_accept.gd -- <model.glb>"}, 2)
		return
	if not FileAccess.file_exists(args[0]):
		_emit({"error": "file not found: %s" % args[0]}, 3)
		return
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	# Headless runs crash while decoding embedded textures; the check does not need them.
	state.handle_binary_image = GLTFState.HANDLE_BINARY_IMAGE_MODE_DISCARD_TEXTURES
	var err := doc.append_from_file(args[0], state)
	if err != OK:
		_emit({"error": "glTF import failed (%s)" % error_string(err)}, 4)
		return
	var root := doc.generate_scene(state)
	if root == null:
		_emit({"error": "glTF import produced no scene"}, 4)
		return
	var nodes: Array = []
	_walk(root, nodes)
	var skeletons: Array = []
	var animations: Array = []
	var influences := 0
	for n in nodes:
		if n is Skeleton3D:
			skeletons.append(n)
		elif n is ImporterMeshInstance3D and n.mesh != null:
			var m: ImporterMesh = n.mesh
			for s in m.get_surface_count():
				influences = maxi(influences, _max_influences(m.get_surface_arrays(s), m.get_surface_format(s)))
		elif n is MeshInstance3D and n.mesh != null:
			var am: Mesh = n.mesh
			for s in am.get_surface_count():
				influences = maxi(influences, _max_influences(am.surface_get_arrays(s), am.surface_get_format(s)))
		elif n is AnimationPlayer:
			for a in n.get_animation_list():
				animations.append(String(a))
	var out := {"skeletons": skeletons.size(), "bones": 0, "roots": 0, "max_influences": influences,
				"animations": animations, "bonemap_auto": {"method": "name_heuristic", "mapped": 0, "unmapped": []}}
	if not skeletons.is_empty():
		var sk: Skeleton3D = skeletons[0]
		var roots := 0
		for i in sk.get_bone_count():
			if sk.get_bone_parent(i) == -1:
				roots += 1
		out["bones"] = sk.get_bone_count()
		out["roots"] = roots
		out["bonemap_auto"] = _bonemap(sk)
	root.free()
	_emit(out, 0)
