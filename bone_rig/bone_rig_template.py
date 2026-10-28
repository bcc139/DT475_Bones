"""
DT475 Animation & Modeling  -  Assignment: Bone Placement & Hierarchy for a Robot Arm
TEMPLATE (student copy)                                                    Tested with Blender 5.2

What the script does
    1. gets the robot (one mesh object per part: base, turret, arm.01 ... wrist, finger.L.01 ...), in one of two ways:
         MODEL_SOURCE = "COLLECTION"  the robot is already in the scene: use the collection you clicked in the Outliner
         MODEL_SOURCE = "OBJ"         clear the scene and import the OBJ file at OBJ_PATH
    2. reads the vertices of every part in WORLD space                                  <- TODO 1
    3. HIERARCHY : decides which bone is the parent of which                            <- TODO 2
    4. PLACEMENT : head of every bone = its joint, tail = where its children start      <- TODO 3 and TODO 4
    5. builds the Armature: one bone per part, named like the part, correctly parented  <- TODO 5
    6. (provided) binds every mesh to its bone, so you can pose the arm and the meshes follow

How to run
    A. MODEL_SOURCE = "COLLECTION": open robot_arms.blend. In the Outliner (top right) CLICK the name of ONE robot's
       collection, for example robot_4arm.
    B. MODEL_SOURCE = "OBJ": set OBJ_PATH below to the full path of an OBJ file. The script CLEARS the scene first.
    Then: Scripting workspace -> Text > Open -> choose this file -> Run Script (the play button, or Alt+P).
    The armature appears in the same collection as the robot. Look at it in the 3D viewport - see "TRY IT" at the end.
    (print() output appears in the System Console: Window > Toggle System Console)
    Change your code and run again as often as you like: the script first removes the rig of the previous run.
"""
import os

import bpy
from mathutils import Matrix, Vector

# ------------------------------------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------------------------------------
MODEL_SOURCE = "COLLECTION"   # "COLLECTION": use the robot in the collection you clicked in the Outliner
                              # "OBJ":        clear the scene, then import the OBJ file at OBJ_PATH
OBJ_PATH = r"C:\path\to\robot_arm_4arm.obj"   # used only when MODEL_SOURCE = "OBJ" (keep the letter r before the quotes)
BIND_MESHES = True            # True: parent every mesh to its bone, so the arm can be posed


# ==========================================================================================
# BPY FOOTNOTES  -  the Blender Python functions and data used in this script.
# "bpy" is Blender's Python module. Look for the numbers [1] ... [11] in the comments below.
# ==========================================================================================
# [1] bpy.data     The database of the open .blend file. Everything lives in collections:
#                  bpy.data.objects, bpy.data.meshes, bpy.data.armatures ...
#                  Loop over one:   for obj in bpy.data.objects:        Look one up by name:   bpy.data.objects["base"]
#                  Create / delete: bpy.data.armatures.new("name")      bpy.data.objects.remove(obj)
# [2] bpy.ops      "Operators" = the commands of Blender's menus (File > Import, Tab to change mode ...).
#                  They act on whatever is selected / active right now.  Used here:
#                      bpy.ops.wm.obj_import(filepath=...)       File > Import > Wavefront (.obj)
#                      bpy.ops.object.mode_set(mode='EDIT')      press Tab (use mode='OBJECT' to go back)
#                      bpy.ops.object.select_all(action='DESELECT')    click in an empty place: select nothing
# [3] bpy.context  The current state of Blender.
#                      bpy.context.view_layer.active_layer_collection.collection   the collection you clicked  [11]
#                      bpy.context.view_layer.objects.active the ACTIVE object (assign an object to make it active)
#                      bpy.context.view_layer.update()       make Blender recalculate all matrices after changes
# [4] Object       (bpy.types.Object) one item in the scene: a mesh, an armature ...
#                      obj.name   obj.type ('MESH' or 'ARMATURE')   obj.select_set(True)
#                      obj.data   the thing the object holds: a Mesh (shape) or an Armature (bones)
#                      obj.matrix_world   position / rotation / scale of the object in the scene  (see [6])
# [5] Mesh data    obj.data.vertices is the list of vertices. Each vertex has  v.co , a Vector (x, y, z)
#                  measured in the object's LOCAL space (from the object's own origin).
# [6] Matrix       obj.matrix_world is a 4x4 Matrix.  matrix @ vector  moves the vector into the matrix's space,
#                  so  obj.matrix_world @ v.co  is the vertex in WORLD space (= the scene).
#                  A robot imported from an OBJ file carries a Y-up -> Z-up rotation in this matrix, so it is never optional.
# [7] Vector       (mathutils.Vector) a 3D point or direction.   Vector((x, y, z))
#                  a + b   a - b   a * 2   a / 2   a.dot(b)   a.length   a.normalized()
# [8] Armature     bpy.data.armatures.new(name) holds the bones. It has TWO views of the bones:
#                  * armature.edit_bones   only valid in EDIT mode; here you create and move bones:
#                        eb = armature.edit_bones.new("name");   eb.head = Vector;   eb.tail = Vector
#                        eb.parent = another edit bone;          eb.use_connect = True / False
#                  * armature.bones        valid after you leave EDIT mode; read-only:
#                        bone.head_local   bone.tail_local   bone.matrix_local   bone.parent   bone.children
# [9] Modes        edit_bones can only be used while the armature is in EDIT mode. The bones are really
#                  created when you go back to OBJECT mode, so never forget that last mode_set.
# [10] Parenting a mesh to a bone    obj.parent = armature object      obj.parent_type = 'BONE'
#                  obj.parent_bone = "bone name"        obj.matrix_parent_inverse = Matrix
#                  (explained step by step inside bind_meshes_rigidly)
# [11] Collection  A folder of objects in the Outliner. The one you CLICKED is the active collection:
#                      bpy.context.view_layer.active_layer_collection.collection
#                      collection.name    collection.all_objects (its objects, also those in sub-collections)
#                      collection.objects.link(obj)       put an object into the collection
#                  Object names are unique in a whole .blend file, so the robots in robot_arms.blend are named
#                  "robot_4arm:arm.01": the text after the ":" is the name of the part, before it is the robot.
#                  (An OBJ file keeps the plain part names, which is why MODEL_SOURCE = "OBJ" clears the scene first.)


# ------------------------------------------------------------------------------------------
# PROVIDED - scene handling (you do not edit these)
# ------------------------------------------------------------------------------------------
def back_to_object_mode():
    """Leave Edit mode or Pose mode, so that objects can be changed freely."""
    active = bpy.context.view_layer.objects.active          # [3]
    if active is not None and active.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')              # [2][9]


def clear_scene():
    """Delete everything: objects, collections and their data."""
    # list(...) makes a copy of the collection: we must not delete items from a collection while looping over it
    for obj in list(bpy.data.objects):                      # [1]
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for armature in list(bpy.data.armatures):
        bpy.data.armatures.remove(armature)


def import_obj(path):
    """
    OBJ mode: clear the scene, import the OBJ file into a new collection and return that collection.
    The OBJ file has one object (one 'o' line) per part, and the importer keeps those names.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError("OBJ_PATH is not a file: " + path)
    clear_scene()
    name = os.path.splitext(os.path.basename(path))[0]      # 'models/robot_arm_4arm.obj' -> 'robot_arm_4arm'
    collection = bpy.data.collections.new(name)             # [1][11]
    bpy.context.scene.collection.children.link(collection)  # [3] show the collection in the scene
    # new objects go into the ACTIVE collection, so make ours the active one
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[name]   # [3]
    bpy.ops.wm.obj_import(filepath=path)                    # [2] same as File > Import > Wavefront (.obj)
    return collection


def get_collection():
    """The collection that holds the robot: the one you clicked, or a new one made from the OBJ file."""
    if MODEL_SOURCE == "OBJ":
        return import_obj(OBJ_PATH)
    if MODEL_SOURCE == "COLLECTION":
        return bpy.context.view_layer.active_layer_collection.collection      # [3][11] the one you clicked
    raise ValueError('MODEL_SOURCE must be "COLLECTION" or "OBJ", not ' + repr(MODEL_SOURCE))


def part_name_of(obj):
    """The name of the part: 'robot_4arm:arm.01' -> 'arm.01'. A name without ':' stays as it is."""
    return obj.name.split(":")[-1]                          # [4] the text after the last ':'


def get_parts(collection):
    """
    Returns a dictionary {part name: object} for the meshes in the collection, for example parts["arm.01"].
    By now the robot is in the scene, whichever way it got there.
    """
    parts = {}
    for obj in collection.all_objects:                      # [11]
        if obj.type == 'MESH':
            name = part_name_of(obj)
            if name in parts:
                raise ValueError("The collection '" + collection.name + "' holds two parts called '" + name +
                                 "'. Click the collection of ONE robot in the Outliner and run again.")
            parts[name] = obj
    # the same thing as one line (a "dictionary comprehension"), without the check for doubles:
    # parts = {part_name_of(obj): obj for obj in collection.all_objects if obj.type == 'MESH'}
    if "base" not in parts:
        raise ValueError("No robot found in the collection '" + collection.name +
                         "'. Click the collection of a robot in the Outliner and run again.")
    return parts


def remove_old_rig(collection):
    """Undo a previous run of this script on the collection, so that you can run it again and again."""
    for obj in list(collection.all_objects):                # list(...) = a copy, we change the collection in the loop
        if obj.type == 'MESH' and obj.parent is not None and obj.parent.type == 'ARMATURE':
            obj.parent = None                               # [4] free the mesh from its bone ...
            obj.matrix_parent_inverse = Matrix.Identity(4)  # ... and forget the old binding correction
    for obj in list(collection.all_objects):
        if obj.type == 'ARMATURE':
            arm_data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)    # [1] delete the armature object ...
            bpy.data.armatures.remove(arm_data)             # ... and its data
    bpy.context.view_layer.update()                         # [3] the meshes are back at their original place


def mean_point(points):
    """The average (centre) of a list of Vectors."""
    total = Vector((0.0, 0.0, 0.0))                         # [7]
    for p in points:
        total += p
    return total / len(points)


def end_point(points, direction, fraction=0.05):
    """
    The 'end' of a part in a given direction: the centre of the points that lie furthest along `direction`.
    Example: end_point(verts["base"], Vector((0, 0, 1)))  is the centre of the TOP of the base.
    `fraction` = how much of the part's length counts as 'the end' (0.05 = the last 5 %).
    """
    d = direction.normalized()                              # a direction of length 1

    # how far does each point lie along d?  (p.dot(d) is the distance of p measured along d)  [7]
    along = []
    for p in points:
        along.append(p.dot(d))
    # the same thing as one line (a "list comprehension"):
    # along = [p.dot(d) for p in points]

    low = min(along)
    high = max(along)
    limit = high - fraction * (high - low)                  # points beyond `limit` are 'the end'

    far_points = []
    for p in points:
        if p.dot(d) >= limit:
            far_points.append(p)
    # the same thing as one line (zip() walks through two lists together, point by point):
    # far_points = [p for p, a in zip(points, along) if a >= limit]

    return mean_point(far_points)


def names_starting_with(names, prefix):
    """The names that begin with `prefix`, in alphabetical order.  names_starting_with(["arm.02", "arm.01", "base"], "arm.")  ->  ["arm.01", "arm.02"]"""
    found = []
    for n in names:
        if n.startswith(prefix):
            found.append(n)
    found.sort()
    return found
    # the same thing as one line:
    # return sorted(n for n in names if n.startswith(prefix))


# ------------------------------------------------------------------------------------------
# TODO 1 - vertices in world space
# ------------------------------------------------------------------------------------------
def world_vertices(obj):
    """
    Return the vertices of `obj` as a list of Vectors in WORLD space.

    Why world space?  A vertex's `.co` is measured from the object's own origin [5], and the object may have been
    moved, rotated or scaled in the scene [6]. Bones live in the scene, so they must be placed with scene coordinates.

    Footnotes: [4] obj   [5] obj.data.vertices, v.co   [6] obj.matrix_world   [7] Vector
    Pattern:
        result = []
        for v in <all vertices of the mesh>:
            result.append( <v.co moved into world space> )
        return result
    """
    # TODO 1: replace the next line
    raise NotImplementedError("TODO 1: world_vertices")


# ------------------------------------------------------------------------------------------
# TODO 2 - hierarchy: who is whose parent?
# ------------------------------------------------------------------------------------------
def build_hierarchy(names):
    """
    names : every object name in the file, e.g. ["base", "turret", "arm.01", "arm.02", "wrist", "joint.arm.01", ...]
    returns {bone name: parent bone name}   (the root has parent None; a parent must come BEFORE its children)

    The robot is one chain with a fork at the end:

        base -> turret -> arm.01 -> arm.02 -> ... -> arm.NN -> wrist -+-> finger.L.01 -> finger.L.02 -> ...
                                                                      +-> finger.R.01 -> finger.R.02 -> ...

    * It must work for ANY number of arms (NN) and ANY number of finger segments - use loops, not fixed names.
    * Objects called joint.* are hinge pins, not links: they get NO bone.
    * names_starting_with(names, "arm.") (provided above) gives you ["arm.01", "arm.02", ...] in order.
    Pattern for a chain:
        previous = "turret"
        for name in <the arm names>:
            parent[name] = previous
            previous = name
    """
    # TODO 2: build and return the {bone: parent} dictionary
    raise NotImplementedError("TODO 2: build_hierarchy")


# ------------------------------------------------------------------------------------------
# TODO 3 - placement: the HEAD of every bone (its joint)
# ------------------------------------------------------------------------------------------
def compute_heads(verts, parent):
    """
    verts  : {object name: [world-space Vectors]}   (also contains the joint.* pins)
    parent : {bone: parent}   (from TODO 2)
    returns {bone: head position}

    The head of a bone is its JOINT - the point where the bone pivots on its parent.
      * arm.k and finger.S.k : the hinge pin  joint.<bone name>  marks the joint  ->  its centre is the head
      * base                 : the bottom of the base                               (the root of the whole rig)
      * turret               : it stands on top of the base, so its joint is the top of the base
      * wrist                : no pin.  Its joint is the end of the wrist that faces the last arm:
                               take the direction from the last arm's head to the wrist's centre, and use the
                               end of the wrist in the OPPOSITE direction.
    Tools: mean_point(points) and end_point(points, direction) are provided above.
    Pattern:  for bone in parent:  if bone == "base": ...  elif bone == "turret": ...  elif ...  else: ...
    Remember: bones are processed parent-first, so heads[parent[bone]] already exists when you need it.
    """
    heads = {}
    # TODO 3: fill `heads` for every bone in `parent`
    raise NotImplementedError("TODO 3: compute_heads")


# ------------------------------------------------------------------------------------------
# TODO 4 - placement: the TAIL of every bone
# ------------------------------------------------------------------------------------------
def compute_tails(heads, verts, parent):
    """
    returns {bone: tail position}

    A bone ends where its children begin:
      * the bone has children  : the tail is the average of its children's heads   (the wrist has two!)
      * the bone has no child  : a fingertip - the tail is the far end of the part, seen from the head
                                 (direction = centre of the part - head;  use end_point)
    Hint: first build {bone: [children]} from the parent dictionary:
        children = {}
        for bone in parent:
            children[bone] = []          # everybody starts with no children
        for bone in parent:
            ... add `bone` to the children list of its parent (the root has no parent!) ...
    """
    # TODO 4: build and return the {bone: tail} dictionary
    raise NotImplementedError("TODO 4: compute_tails")


# ------------------------------------------------------------------------------------------
# TODO 5 - build the armature
# ------------------------------------------------------------------------------------------
def create_armature(heads, tails, parent, collection):
    """
    Create an Armature object with one bone per entry of `parent`.  Each bone is named like its part
    (so the bone "arm.02" belongs to the mesh "arm.02").

    `collection` is the collection of the robot; the armature is put into it.
    Steps (the first two are done for you):
      1. create the armature data + object, link it to the collection, make it active, enter EDIT mode
      2. for every bone, parent first:  eb = arm_data.edit_bones.new(bone_name);  eb.head = ...;  eb.tail = ...   [8]
      3. set eb.parent to the parent's edit bone  (arm_data.edit_bones[parent_name]);  the root has no parent
      4. if the parent has exactly ONE child, also set eb.use_connect = True   (a chain is connected,
         a fork - wrist -> two fingers - is not).  Count how many bones in `parent` have this parent.
      5. leave EDIT mode (back to OBJECT mode) and return the armature object          (done for you)
    """
    name = collection.name + "_Armature"
    arm_data = bpy.data.armatures.new(name)          # [1][8] the Armature DATA: it will hold the bones
    arm_obj = bpy.data.objects.new(name, arm_data)   # [1][4] an OBJECT that shows this armature in the scene
    collection.objects.link(arm_obj)                 # [11] put it into the same collection as the robot
    bpy.ops.object.select_all(action='DESELECT')     # [2] select nothing ...
    bpy.context.view_layer.objects.active = arm_obj  # [3] ... make the armature the active object ...
    arm_obj.select_set(True)                         # [4] ... and select it
    bpy.ops.object.mode_set(mode='EDIT')             # [2][9] edit_bones can only be used in EDIT mode

    # TODO 5: create, place and parent the bones

    bpy.ops.object.mode_set(mode='OBJECT')           # [9] leaving EDIT mode creates the real bones
    arm_obj.show_in_front = True                     # draw the bones in front of the meshes, so we can see them
    return arm_obj


# ------------------------------------------------------------------------------------------
# PROVIDED - binding the meshes to the bones (you do not edit these, but please read them!)
# ------------------------------------------------------------------------------------------
def bone_of(part_name):
    """Which bone drives this part?  joint.arm.02 is driven by the bone arm.02; every other part by its own name."""
    if part_name.startswith("joint."):
        return part_name[len("joint."):]            # cut off the first 6 letters, "joint."
    return part_name
    # the same thing as one line (a "conditional expression"):
    # return part_name[len("joint."):] if part_name.startswith("joint.") else part_name


def bind_meshes_rigidly(arm_obj, parts):
    """
    Bind every mesh to its bone, so the mesh moves when the bone moves.
    "Rigid" = each mesh follows exactly ONE bone, 100 %. (No weights, no blending between bones.)

    THE IDEA
      In Blender every object can have a parent, and the position of a child is worked out like this:

          child.matrix_world = PARENT @ INVERSE @ BASIS

          PARENT   where the parent (here: the bone) is right now          (Blender updates it when you pose the bone)
          BASIS    the child's own location / rotation / scale             (we never touch it)
          INVERSE  obj.matrix_parent_inverse - a "correction" that we choose

      Imagine we set only the parent and leave INVERSE as "nothing" (the identity matrix). Then
      child = PARENT @ BASIS: the mesh is carried to the bone and its old position is lost - it JUMPS.
      The fix: remember where the bone was at the moment of binding (call it REST) and store
      INVERSE = REST^-1 (the undo of REST). At the moment of binding:
          child = REST @ REST^-1 @ BASIS = BASIS      -> nothing moves, the mesh stays where it was.
      Later, when you pose the bone, PARENT changes to a new matrix NOW, and
          child = NOW @ REST^-1 @ BASIS               -> the mesh moves by exactly the CHANGE of the bone.
      That is all there is to "binding": the inverse remembers the rest pose. (The menu command Ctrl+P > Bone
      computes the same inverse for you; here we do it by hand to see what happens.)  [10]
    """
    for part_name in parts:
        obj = parts[part_name]
        # the same loop in one line (.items() gives the name and the object together):
        # for part_name, obj in parts.items():

        # STEP 1 - find the bone that drives this part. `bones` is the read-only list of finished bones [8].
        bone = arm_obj.data.bones[bone_of(part_name)]

        # STEP 2 - make the bone the parent of the mesh.
        obj.parent = arm_obj                # the parent object is the armature ...
        obj.parent_type = 'BONE'            # ... and the child follows one BONE of it, not the whole armature
        obj.parent_bone = bone.name         # which bone

        # STEP 3 - compute REST: the matrix of the bone at the moment of binding, in world space.
        # bone.matrix_local = position (head) and orientation of the bone, measured inside the armature, so we
        # put the armature's own matrix_world in front of it. @ is matrix multiplication [6].
        rest = arm_obj.matrix_world @ bone.matrix_local
        # Blender's 'BONE' parenting measures from the bone's TAIL, not from its head. So REST must use the tail
        # as its position, or all meshes would be shifted by one bone length. translation = the position part of a matrix.
        rest.translation = arm_obj.matrix_world @ bone.tail_local

        # STEP 4 - INVERSE = the undo of REST. Now  REST @ INVERSE = nothing  -> the mesh stays exactly where it is.
        obj.matrix_parent_inverse = rest.inverted()

    bpy.context.view_layer.update()         # [3] let Blender recalculate everything


def print_bones(arm_obj):
    """Print the bones, one per line: name, parent, head, tail. Handy to compare with what you expect."""
    for bone in arm_obj.data.bones:                            # [8] the finished bones
        parent_name = "-"
        if bone.parent is not None:
            parent_name = bone.parent.name
        head = bone.head_local
        tail = bone.tail_local
        print(f"{bone.name:14} parent {parent_name:12}"
              f" head ({head.x:6.2f}, {head.y:6.2f}, {head.z:6.2f})"
              f" tail ({tail.x:6.2f}, {tail.y:6.2f}, {tail.z:6.2f})")


# ------------------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------------------
def main():
    back_to_object_mode()
    collection = get_collection()                   # the robot's collection (see MODEL_SOURCE)
    remove_old_rig(collection)                      # the rig of a previous run, if any
    parts = get_parts(collection)                   # {part name: object}
    print("robot", collection.name, "has", len(parts), "parts")

    # the vertices of every part in world space: verts["arm.01"] is a list of Vectors
    verts = {}
    for name in parts:
        verts[name] = world_vertices(parts[name])
    # the same thing as one line (a "dictionary comprehension"; .items() gives name and object together):
    # verts = {name: world_vertices(obj) for name, obj in parts.items()}

    parent = build_hierarchy(list(parts))           # list(parts) = the list of all the names
    heads = compute_heads(verts, parent)
    tails = compute_tails(heads, verts, parent)
    arm_obj = create_armature(heads, tails, parent, collection)

    if BIND_MESHES:
        bind_meshes_rigidly(arm_obj, parts)
    print_bones(arm_obj)


# ------------------------------------------------------------------------------------------
# TRY IT - test your rig in the 3D viewport (no extra code needed)
# ------------------------------------------------------------------------------------------
#  1. Outliner (top right): open "RobotArm_Armature". The bone tree must match the diagram of the worksheet.
#     With BIND_MESHES = True every mesh also appears under its bone.
#  2. Click the armature, press Ctrl+Tab to enter POSE mode, click a bone and type   R  X  20  Enter .
#     That bone and EVERYTHING BELOW IT must bend forward as one piece.
#     A part that stays behind = wrong parent (TODO 2) or wrong head (TODO 3).  Reset the pose with Alt+R.
#  3. Press Tab (EDIT mode) on the armature: each bone must start on a hinge pin and end where the next bone starts.
#  4. Rig the OTHER robots: click another collection (or set OBJ_PATH to another OBJ file) and run again.
#     The same code must work for any number of arms and fingers.
#     Run it a second time on the same robot: the old rig is removed first, so you never get two.
#  5. Break it on purpose (then undo it): in bind_meshes_rigidly comment out  obj.matrix_parent_inverse = ...
#     and run again - the meshes jump. Now keep that line but comment out  rest.translation = ...  - what happens?
if __name__ == "__main__":
    main()
