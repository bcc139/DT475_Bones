# DT475_Bones
HW03 - Creating Bones for Robot Arm

DT475 Animation and Modeling. You write a Blender Python script that builds the skeleton (armature) of a robot arm:
one bone per moving part, each bone placed on its joint and parented to the bone before it. The template then binds
every mesh to its bone, so you can pose the robot and see whether your skeleton is right.

Tested with **Blender 5.2**. Your instructor's worksheet explains the task, the rules for head, tail and parent, and the grading.

## Files

| Path | What it is |
| --- | --- |
| `bone_rig/bone_rig_template.py` | The script you complete. Five functions are marked `TODO`; everything else is provided. |
| `bone_rig/robot_arms.blend` | Three test robots in one Blender file, one collection per robot. |
| `bone_rig/OBJ/` | The same three robots as OBJ files: `robot_arm_4arm.obj`, `robot_arm_3arm.obj`, `robot_arm_2arm_3fingers.obj`. |
| `bone_rig/create_robot_arm_named.py` | Optional: builds a robot with any number of arms and fingers (for the challenge). |
| `bone_rig/target_skeleton.png` | What a correct rig looks like (`robot_arm_4arm`, side view, forward to the left). |

## Quick start

1. Open Blender, go to the **Scripting** workspace, and open `bone_rig/bone_rig_template.py` (Text > Open).
2. Choose how the robot is loaded with `MODEL_SOURCE` at the top of the script:
   - `"COLLECTION"` (default): open `bone_rig/robot_arms.blend`, **click the name of one robot's collection** in the Outliner, then run.
   - `"OBJ"`: set `OBJ_PATH` to the full path of a file in `bone_rig/OBJ/` (keep the letter `r` before the quotes), then run. The scene is cleared first.
3. Complete the five `TODO` functions in order, and run the script (the play button or Alt+P) after each one.
4. Check the result in the 3D viewport: expand the armature in the Outliner, press Ctrl+Tab for Pose mode, select a bone and press `R`, `X`, `20`, `Enter`.
   Everything below that bone must bend forward with it.
5. Your script must work for **every** robot, so run it on all three, without editing a line in between.

The footnotes at the top of the template explain the Blender Python (`bpy`) functions you need.
Running the script again removes the rig of the previous run, so you can run it as often as you like.
