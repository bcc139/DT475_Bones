"""
create_robot_arm_named.py   -   build the robot arm of  robot_arm_named.obj  in Blender (5.x)

Run:  Scripting workspace -> Open -> Run Script (Alt+P)
      headless:  blender -b -P create_robot_arm_named.py
The defaults below were MEASURED from robot_arm_named.obj (see measure_robot_arm_obj.py), so running
the script unchanged rebuilds that arm. Change the PARAMETERS section to build other arms.

CONVENTIONS
  * Z-up scene. The arm moves in the Y-Z plane, all hinge axes are X.
  * "forward" = -Y (where the gripper points; Blender's front view).
  * ANGLES are in degrees and RELATIVE to the previous segment:
        ARM_ANGLES[0]            vs. vertical (+Z)            ARM_ANGLES[i]   vs. arm i-1
        FINGER_ANGLES_x[0]       vs. the LAST arm             FINGER_ANGLES_x[j] vs. finger segment j-1
    + = rotate forward (toward -Y),   - = rotate backward (toward +Y).
  * FINGERS: with 2 or more segments each finger is a chain of straight articulated parts.
    With exactly ONE segment the finger is a single BENT part (SINGLE_FINGER_BEND, SINGLE_FINGER_SPLIT);
    its angle FINGER_ANGLES_x[0] is the direction of the first leg, and it bends toward the other finger.
  * LENGTHS are joint-to-joint (hinge centre to hinge centre). The last arm ends at the middle of the
    wrist plate (the line that joins the two finger hinges).

PARTS CREATED (one mesh object each; origin at the world origin like the OBJ)
  base, turret, joint.arm.01 .. joint.arm.NN, arm.01 .. arm.NN, wrist,
  finger.L.01 .. / finger.R.01 ..  and  joint.finger.L.01 .. / joint.finger.R.01 ..
  (arm.NN, the last arm, is the hand bracket with the round flange; joint.arm.k is the hinge at the START of arm.k)
"""
import os
import sys
import math

import bpy
import numpy as np

# =====================================================================================
#  PARAMETERS  (defaults = measured from robot_arm_named.obj)
# =====================================================================================
NUM_ARMS = 4                                   # number of arm segments, at least 2
ARM_LENGTHS = [2.927, 2.924, 2.127, 1.607]     # joint-to-joint length of arm.01 .. arm.NN
ARM_ANGLES = [-44.65, 88.92, 53.91, 39.49]     # relative angle of each arm   (+ forward / - backward)

NUM_FINGER_SEGMENTS = 2                        # articulated segments per finger (each = own part + own hinge)
FINGER_LENGTHS = [0.904, 1.131]                # length of each finger segment (same for both fingers)
FINGER_ANGLES_L = [35.52, -78.48]              # relative angle of each segment of finger L
FINGER_ANGLES_R = [-34.67, 78.48]              # relative angle of each segment of finger R
# A finger with ONE segment is a single bent part (a hook) so that it can still catch an object:
SINGLE_FINGER_BEND = 78.5                      # degrees the finger turns toward the other finger at its knee (0..80)
SINGLE_FINGER_SPLIT = 0.444                    # where the knee sits, as a fraction of the finger length (0.2..0.7)
                                               # (the defaults rebuild the bent finger of robot_arm_named.obj;
                                               #  FINGER_LENGTHS[0] = whole length hinge -> knee -> tip)

SHOULDER_HEIGHT = 1.677                        # height of the first hinge (joint.arm.01) above the ground
FINGER_SPACING = 1.0                           # distance between the two finger hinges on the wrist plate

MEASURE_FROM_OBJ = ""      # e.g. r"C:\...\robot_arm_named.obj"  -> re-measure all values above from that file
EXPORT_OBJ_PATH = ""       # e.g. r"C:\...\robot_arm_generated.obj" -> also export the result as OBJ
CLEAR_PREVIOUS = True      # delete the collection of a previous run first
COLLECTION_NAME = "RobotArm"
ASSIGN_COLORS = False      # True: simple coloured materials (base/turret, arms, joints, hand, fingers)

# =====================================================================================
#  STYLE CONSTANTS  (shapes / thicknesses measured from the OBJ - normally leave as they are)
# =====================================================================================
BASE_PROFILE = [(0, -0.035), (1.538, -0.035), (1.538, 0.164), (1.0, 0.164), (1.0, 0.986),
                (0.879, 0.986), (0.879, 0.814), (0, 0.814)]      # (radius, z) of the revolved base
TURRET_DISC = dict(radius=0.814, z0=0.888, z1=1.174)
CHEEK = dict(width=1.043, back=0.298, front=0.572, corner=0.298)   # clevis tab around a hinge
CHEEK_OUT = (0.306, 0.464)                      # |x| range of outer clevis cheeks (turret, hand bracket)
CHEEK_IN = (0.140, 0.297)                       # |x| range of the bracket cheeks when it must sit INSIDE
BAR_WIDTH = 0.597                               # in-plane width of every arm bar
BAR_CORNER = 0.16                               # corner radius of the bar ends
BAR_X_SINGLE = 0.285                            # arm.01: one bar, |x| <= this
PLATE_OUT = (0.303, 0.423)                      # |x| range of outer double plates (even arms)
PLATE_IN = (0.174, 0.297)                       # |x| range of inner double plates (odd arms >= 3)
BAR_EXT_FIRST = 0.088                           # arm.01 reaches this far past its END hinge ...
BAR_EXT_OTHER = 0.093                           # ... the other bars this far back past their START hinge
PIN_ARM_RADIUS = [0.203, 0.196, 0.196, 0.191]    # joint.arm.* hinge cylinders (axis X); joint k uses entry k, extra joints reuse the last
PIN_ARM_HALF = [0.543, 0.524, 0.524, 0.553]      # half length along X
FLANGE = [(0.82, 0.498, 0.783), (0.63, 0.783, 1.03), (0.21, 0.775, 1.03)]   # (radius, from, to) along the hand axis
WRIST_SHAFT = dict(radius=0.152, start=0.914)
WRIST_PLATE = dict(width=1.46, thickness_along=0.416, back_of_fingers=0.294, half_x=0.1655, corner=0.07)
FINGER = dict(width=0.244, thickness=0.095)
PIN_FINGER = dict(radius=0.0705, half_length=0.203)
SEGMENTS = 32                                   # sides of every cylinder


# =====================================================================================
#  small 2-D helpers (the arm plane is Y-Z; a point is (y, z))
# =====================================================================================
def d_vec(angle_deg):
    """Unit direction (y, z) of an absolute angle: 0 = up (+Z), + = forward (-Y)."""
    a = math.radians(angle_deg)
    return np.array([-math.sin(a), math.cos(a)])


def normal2(d):
    """d rotated +90 degrees in the Y-Z plane."""
    return np.array([-d[1], d[0]])


def fit_list(values, n, fill, what):
    """Return a list of exactly n numbers (truncate / pad) and say so."""
    values = list(values)
    if len(values) != n:
        print(f"note: {what} has {len(values)} values but {n} are needed -> "
              f"{'truncated' if len(values) > n else 'padded'}")
    return (values + [fill if fill is not None else values[-1]] * n)[:n]


# =====================================================================================
#  mesh builders - every builder returns (vertices (N,3), faces [[i,...],...]) in world coordinates
# =====================================================================================
def _orient(V, F, centre):
    """Flip faces so normals point away from `centre` (only for convex solids)."""
    out = []
    for f in F:
        p = V[f]
        n = np.zeros(3)
        for i in range(len(f)):
            n += np.cross(p[i], p[(i + 1) % len(f)])
        out.append(f if np.dot(n, p.mean(axis=0) - centre) >= 0 else f[::-1])
    return out


def cylinder(centre, axis, radius, length, segs=SEGMENTS):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    ref = np.array([1.0, 0, 0]) if abs(axis[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(axis, ref); e1 /= np.linalg.norm(e1)
    e2 = np.cross(axis, e1)
    ring = [radius * (math.cos(2 * math.pi * k / segs) * e1 + math.sin(2 * math.pi * k / segs) * e2) for k in range(segs)]
    c = np.asarray(centre, float)
    V = np.array([c + axis * s * length / 2 + r for s in (-1, 1) for r in ring])
    F = [[k, (k + 1) % segs, segs + (k + 1) % segs, segs + k] for k in range(segs)]
    F += [list(range(segs)), list(range(segs, 2 * segs))]
    return V, _orient(V, F, c)


def prism(profile, x0, x1):
    """Extrude a 2-D outline (y, z) along X from x0 to x1."""
    P = np.asarray(profile, float)
    area = 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])
    if area < 0:
        P = P[::-1]
    n = len(P)
    V = np.array([(x, y, z) for x in (x0, x1) for y, z in P])
    F = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    F.append(list(range(n - 1, -1, -1)))            # cap at x0 (normal -X)
    F.append(list(range(n, 2 * n)))                 # cap at x1 (normal +X)
    return V, F


def rrect(c0, d, s_back, s_front, width, r_back, r_front, arc=4):
    """
    Rounded rectangle in the Y-Z plane: centre line starts at c0 and runs along unit vector d;
    it extends s_back behind c0 and s_front ahead of c0; corner radii r_back / r_front.
    """
    c0, d = np.asarray(c0, float), np.asarray(d, float)
    n = normal2(d)
    hw = width / 2
    pts = []

    def corner(s_c, t_c, r, a0):
        if r <= 1e-9:
            pts.append((s_c, t_c))
        else:
            for k in range(arc + 1):
                a = math.radians(a0 + 90 * k / arc)
                pts.append((s_c + r * math.cos(a), t_c + r * math.sin(a)))
    corner(s_front - r_front, -hw + r_front, r_front, -90)
    corner(s_front - r_front, hw - r_front, r_front, 0)
    corner(-s_back + r_back, hw - r_back, r_back, 90)
    corner(-s_back + r_back, -hw + r_back, r_back, 180)
    return np.array([c0 + d * s + n * t for s, t in pts])


def bent_plate(p0, knee, tip, width, arc=6):
    """
    Outline (y, z) of a flat bar that runs p0 -> knee -> tip: round start, mitred inner corner,
    rounded outer corner, flat tip.
    """
    p0, knee, tip = (np.asarray(v, float) for v in (p0, knee, tip))
    d1, d2 = (knee - p0), (tip - knee)
    d1, d2 = d1 / np.linalg.norm(d1), d2 / np.linalg.norm(d2)
    n1, n2 = normal2(d1), normal2(d2)
    hw = width / 2
    inner = 1.0 if (d1[0] * d2[1] - d1[1] * d2[0]) > 0 else -1.0     # the side the bar turns toward
    miter = (n1 + n2) / (1.0 + float(np.dot(n1, n2))) * hw

    def corner(s):                                                    # the knee point(s) on side s (+1: +n, -1: -n)
        if s == inner:
            return [knee + s * miter]
        pts = []
        for k in range(arc + 1):
            v = (1 - k / arc) * n1 + (k / arc) * n2
            pts.append(knee + s * hw * v / np.linalg.norm(v))
        return pts

    pts = [p0 + hw * (n1 * math.cos(math.pi * k / 8) - d1 * math.sin(math.pi * k / 8)) for k in range(9)]   # round start
    pts += corner(-1.0)                                                                                  # - side, forward
    pts += [tip - hw * n2, tip + hw * n2]                                                                # flat tip
    pts += corner(+1.0)[::-1]                                                                            # + side, back
    return np.array(pts)


def lathe(profile, segs=SEGMENTS):
    """Revolve a (radius, z) profile around the Z axis. The profile runs counter-clockwise (outside on its right)."""
    rings, faces, V = [], [], []
    for r, z in profile:
        if r <= 1e-9:
            V.append((0.0, 0.0, z)); rings.append([len(V) - 1])
        else:
            ids = []
            for k in range(segs):
                a = 2 * math.pi * k / segs
                V.append((r * math.cos(a), r * math.sin(a), z)); ids.append(len(V) - 1)
            rings.append(ids)
    V = np.array(V)
    for i in range(len(profile) - 1):
        (r0, z0), (r1, z1) = profile[i], profile[i + 1]
        out = np.array([z1 - z0, -(r1 - r0)])               # outward normal in (z, r) -> (nz, nr) handled below
        nr, nz = (z1 - z0), -(r1 - r0)                      # rotate edge (dr,dz) by -90deg: (dz, -dr)
        A, B = rings[i], rings[i + 1]
        if len(A) == 1 and len(B) == 1:
            continue
        if len(A) == 1 or len(B) == 1:                      # cap: fan -> n-gon on the full ring
            ring = B if len(A) == 1 else A
            faces.append(_face_dir(V, ring, np.array([0, 0, nz if nz else 1.0]), nz))
            continue
        for k in range(segs):
            q = [A[k], A[(k + 1) % segs], B[(k + 1) % segs], B[k]]
            ang = 2 * math.pi * (k + 0.5) / segs
            expect = np.array([nr * math.cos(ang), nr * math.sin(ang), nz])
            faces.append(_face_dir(V, q, expect, 1))
    return V, faces


def _face_dir(V, ids, expect, _):
    p = V[ids]
    n = np.zeros(3)
    for i in range(len(ids)):
        n += np.cross(p[i], p[(i + 1) % len(ids)])
    return ids if np.dot(n, expect) >= 0 else ids[::-1]


def merge(shapes):
    V, F, off = [], [], 0
    for sv, sf in shapes:
        V.append(np.asarray(sv, float))
        F += [[i + off for i in f] for f in sf]
        off += len(sv)
    return np.vstack(V), F


# =====================================================================================
#  the robot
# =====================================================================================
def validate_and_fit():
    global NUM_ARMS, ARM_LENGTHS, ARM_ANGLES, NUM_FINGER_SEGMENTS, FINGER_LENGTHS, FINGER_ANGLES_L, FINGER_ANGLES_R
    global SINGLE_FINGER_BEND, SINGLE_FINGER_SPLIT
    if not 0.0 <= SINGLE_FINGER_BEND <= 80.0:
        print(f"note: SINGLE_FINGER_BEND {SINGLE_FINGER_BEND} -> limited to 0..80 degrees (a larger bend folds the hook back on itself)")
        SINGLE_FINGER_BEND = min(max(SINGLE_FINGER_BEND, 0.0), 80.0)
    if not 0.2 <= SINGLE_FINGER_SPLIT <= 0.7:
        print(f"note: SINGLE_FINGER_SPLIT {SINGLE_FINGER_SPLIT} -> limited to 0.2..0.7")
        SINGLE_FINGER_SPLIT = min(max(SINGLE_FINGER_SPLIT, 0.2), 0.7)
    if NUM_ARMS < 2:
        raise ValueError("NUM_ARMS must be at least 2")
    if NUM_FINGER_SEGMENTS < 1:
        raise ValueError("NUM_FINGER_SEGMENTS must be at least 1")
    ARM_LENGTHS = fit_list(ARM_LENGTHS, NUM_ARMS, None, "ARM_LENGTHS")
    ARM_ANGLES = fit_list(ARM_ANGLES, NUM_ARMS, 0.0, "ARM_ANGLES")
    FINGER_LENGTHS = fit_list(FINGER_LENGTHS, NUM_FINGER_SEGMENTS, None, "FINGER_LENGTHS")
    FINGER_ANGLES_L = fit_list(FINGER_ANGLES_L, NUM_FINGER_SEGMENTS, 0.0, "FINGER_ANGLES_L")
    FINGER_ANGLES_R = fit_list(FINGER_ANGLES_R, NUM_FINGER_SEGMENTS, 0.0, "FINGER_ANGLES_R")
    min_last = WRIST_SHAFT["start"] + WRIST_PLATE["back_of_fingers"]
    if ARM_LENGTHS[-1] < min_last:
        print(f"warning: the last arm is shorter than {min_last:.2f}; the wrist plate then overlaps the hand flange")


def apply_measurement(path):
    """Overwrite the parameters with values measured from an OBJ (needs measure_robot_arm_obj.py next to this script)."""
    global NUM_ARMS, ARM_LENGTHS, ARM_ANGLES, NUM_FINGER_SEGMENTS, FINGER_LENGTHS
    global FINGER_ANGLES_L, FINGER_ANGLES_R, SHOULDER_HEIGHT, FINGER_SPACING
    try:
        folder = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        folder = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()
    sys.path.insert(0, folder)
    import measure_robot_arm_obj as m
    r = m.measure(path)
    NUM_ARMS, ARM_LENGTHS, ARM_ANGLES = r["num_arms"], r["arm_lengths"], r["arm_angles"]
    FINGER_LENGTHS = r["finger_L_lengths"]
    NUM_FINGER_SEGMENTS = len(FINGER_LENGTHS)
    FINGER_ANGLES_L, FINGER_ANGLES_R = r["finger_L_angles"], r["finger_R_angles"]
    SHOULDER_HEIGHT, FINGER_SPACING = r["shoulder_height"], r["finger_spacing"]
    print("measured from", path)


def single_finger_path(start, first_angle, length, sgn):
    """Knee and tip (y, z) of a one-segment finger: leg 1 along first_angle, then a bend toward the other finger."""
    knee = start + SINGLE_FINGER_SPLIT * length * d_vec(first_angle)
    tip = knee + (1.0 - SINGLE_FINGER_SPLIT) * length * d_vec(first_angle - sgn * SINGLE_FINGER_BEND)
    return knee, tip


def build_parts():
    """Return {name: (vertices, faces)} for every part, in creation order."""
    n = NUM_ARMS
    # ---- joint positions (y, z) and absolute angles -------------------------------------
    J = [np.array([0.0, SHOULDER_HEIGHT])]
    absang, a = [], 0.0
    for L, rel in zip(ARM_LENGTHS, ARM_ANGLES):
        a += rel
        absang.append(a)
        J.append(J[-1] + L * d_vec(a))                 # J[k] = start of arm k+1 ; J[n] = wrist plate centre line
    axis = d_vec(absang[-1])                           # direction of the hand bracket / wrist
    parts = {}

    # ---- base & turret ------------------------------------------------------------------
    parts["base"] = lathe(BASE_PROFILE)
    td = TURRET_DISC
    shapes = [cylinder((0, 0, (td["z0"] + td["z1"]) / 2), (0, 0, 1), td["radius"], td["z1"] - td["z0"])]
    for sgn in (-1, 1):
        x0, x1 = sorted((sgn * CHEEK_OUT[0], sgn * CHEEK_OUT[1]))
        prof = rrect(J[0], np.array([0.0, -1.0]), CHEEK["back"], CHEEK["front"], CHEEK["width"], CHEEK["corner"], 0.0)
        shapes.append(prism(prof, x0, x1))
    parts["turret"] = merge(shapes)

    # ---- hinge pins joint.arm.01 .. NN --------------------------------------------------
    for k in range(n):
        parts[f"joint.arm.{k + 1:02d}"] = cylinder((0, J[k][0], J[k][1]), (1, 0, 0),
                                                   PIN_ARM_RADIUS[min(k, len(PIN_ARM_RADIUS) - 1)],
                                                   2 * PIN_ARM_HALF[min(k, len(PIN_ARM_HALF) - 1)])

    # ---- arms ---------------------------------------------------------------------------
    for k in range(n - 1):                              # arm.01 .. arm.(N-1): plate arms
        S, E = J[k], J[k + 1]
        d = (E - S) / np.linalg.norm(E - S)
        L = np.linalg.norm(E - S)
        hw = BAR_WIDTH / 2
        ext_s, ext_e = (0.0, BAR_EXT_FIRST) if k == 0 else (BAR_EXT_OTHER, 0.0)
        prof = rrect(S, d, hw + ext_s, L + hw + ext_e, BAR_WIDTH, BAR_CORNER, BAR_CORNER)
        if k == 0:
            shapes = [prism(prof, -BAR_X_SINGLE, BAR_X_SINGLE)]
        else:
            lo, hi = PLATE_OUT if (k + 1) % 2 == 0 else PLATE_IN
            shapes = [prism(prof, -hi, -lo), prism(prof, lo, hi)]
        parts[f"arm.{k + 1:02d}"] = merge(shapes)
    # last arm = hand bracket: clevis cheeks + round flange (3 coaxial discs)
    S = J[n - 1]
    lo, hi = CHEEK_OUT if n % 2 == 0 else CHEEK_IN
    prof = rrect(S, axis, CHEEK["back"] + 0.003, CHEEK["front"] + 0.002, CHEEK["width"], CHEEK["corner"], 0.0)
    shapes = [prism(prof, -hi, -lo), prism(prof, lo, hi)]
    for radius, a0, a1 in FLANGE:
        c = S + axis * (a0 + a1) / 2
        shapes.append(cylinder((0, c[0], c[1]), (0, axis[0], axis[1]), radius, a1 - a0))
    parts[f"arm.{n:02d}"] = merge(shapes)

    # ---- wrist: shaft + plate ------------------------------------------------------------
    W = J[n]                                           # centre line of the finger hinges
    wp = WRIST_PLATE
    plate_start = W - axis * wp["back_of_fingers"]
    shaft_a0, shaft_a1 = WRIST_SHAFT["start"], np.dot(plate_start - S, axis) + 0.01
    c = S + axis * (shaft_a0 + shaft_a1) / 2
    plate = rrect(plate_start, axis, 0.0, wp["thickness_along"], wp["width"], wp["corner"], wp["corner"])
    parts["wrist"] = merge([cylinder((0, c[0], c[1]), (0, axis[0], axis[1]), WRIST_SHAFT["radius"], shaft_a1 - shaft_a0),
                            prism(plate, -wp["half_x"], wp["half_x"])])

    # ---- fingers: chains of articulated segments -------------------------------------------
    fw, ft = FINGER["width"], FINGER["thickness"]
    for side, sgn, angles in (("L", +1, FINGER_ANGLES_L), ("R", -1, FINGER_ANGLES_R)):
        S0 = W + normal2(axis) * sgn * FINGER_SPACING / 2    # L sits on the +90 degree side of the hand axis
        pos, a = S0, absang[-1]
        if NUM_FINGER_SEGMENTS == 1:                              # ONE segment: a single bent hook, one hinge
            knee, tip = single_finger_path(S0, a + angles[0], FINGER_LENGTHS[0], sgn)
            parts[f"finger.{side}.01"] = prism(bent_plate(S0, knee, tip, fw), -ft / 2, ft / 2)
            parts[f"joint.finger.{side}.01"] = cylinder((0, S0[0], S0[1]), (1, 0, 0), PIN_FINGER["radius"],
                                                        2 * PIN_FINGER["half_length"])
            continue
        for j, (L, rel) in enumerate(zip(FINGER_LENGTHS, angles)):
            a += rel
            d = d_vec(a)
            last = j == NUM_FINGER_SEGMENTS - 1
            r_end = 0.0 if last else fw / 2
            prof = rrect(pos, d, fw / 2, L + r_end, fw, fw / 2, r_end)
            t = ft if j % 2 == 0 else 0.8 * ft         # every plate is centred on x = 0; alternate thickness avoids coplanar faces
            name = f"{side}.{j + 1:02d}"
            parts[f"finger.{name}"] = prism(prof, -t / 2, t / 2)
            parts[f"joint.finger.{name}"] = cylinder((0, pos[0], pos[1]), (1, 0, 0), PIN_FINGER["radius"],
                                                     2 * PIN_FINGER["half_length"])
            pos = pos + L * d
    # keep a sensible order: base, turret, joint.*, arm.*, wrist, fingers
    order = (["base", "turret"] + [k for k in parts if k.startswith("joint.arm")] +
             [k for k in parts if k.startswith("arm.")] + ["wrist"] +
             [k for k in parts if k.startswith("finger")] + [k for k in parts if k.startswith("joint.finger")])
    return {k: parts[k] for k in order}


def bone_ground_truth():
    """
    {bone name: (head, tail)} that a correct rig must have, from forward kinematics of the current parameters
    (model coordinates, before any object move / scale). Used by the instructor's grader.
    """
    n = NUM_ARMS
    J = [np.array([0.0, SHOULDER_HEIGHT])]
    absang, a = [], 0.0
    for L, rel in zip(ARM_LENGTHS, ARM_ANGLES):
        a += rel
        absang.append(a)
        J.append(J[-1] + L * d_vec(a))
    axis = d_vec(absang[-1])

    def P(yz):
        return (0.0, float(yz[0]), float(yz[1]))
    z_bottom, z_top = BASE_PROFILE[0][1], max(z for _, z in BASE_PROFILE)
    wrist_head = J[n - 1] + axis * WRIST_SHAFT["start"]
    truth = {"base": ((0.0, 0.0, z_bottom), (0.0, 0.0, z_top)),
             "turret": ((0.0, 0.0, z_top), P(J[0]))}
    for k in range(n):
        tail = J[k + 1] if k < n - 1 else wrist_head
        truth[f"arm.{k + 1:02d}"] = (P(J[k]), P(tail))
    truth["wrist"] = (P(wrist_head), P(J[n]))
    for side, sgn, angles in (("L", +1, FINGER_ANGLES_L), ("R", -1, FINGER_ANGLES_R)):
        pos, a = J[n] + normal2(axis) * sgn * FINGER_SPACING / 2, absang[-1]
        if NUM_FINGER_SEGMENTS == 1:                              # bent hook: the bone runs from the hinge to the tip
            truth[f"finger.{side}.01"] = (P(pos), P(single_finger_path(pos, a + angles[0], FINGER_LENGTHS[0], sgn)[1]))
            continue
        for j, (L, rel) in enumerate(zip(FINGER_LENGTHS, angles)):
            a += rel
            nxt = pos + L * d_vec(a)
            truth[f"finger.{side}.{j + 1:02d}"] = (P(pos), P(nxt))
            pos = nxt
    return truth


def create_in_blender(parts):
    if CLEAR_PREVIOUS and COLLECTION_NAME in bpy.data.collections:
        col = bpy.data.collections[COLLECTION_NAME]
        for ob in list(col.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.collections.remove(col)
    col = bpy.data.collections.new(COLLECTION_NAME)
    bpy.context.scene.collection.children.link(col)
    palette = {"base": (.35, .37, .40), "turret": (.15, .35, .75), "arm": (.90, .45, .10),
               "joint": (.75, .75, .78), "wrist": (.65, .25, .65), "finger": (.20, .65, .35)}
    mats = {}
    objs = {}
    for name, (V, F) in parts.items():
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([tuple(v) for v in V], [], [list(map(int, f)) for f in F])
        mesh.update()
        ob = bpy.data.objects.new(name, mesh)
        col.objects.link(ob)
        if ASSIGN_COLORS:
            group = name.split(".")[0]
            if group not in mats:
                m = bpy.data.materials.new(f"robot_{group}")
                m.diffuse_color = (*palette.get(group, (.6, .6, .6)), 1.0)
                mats[group] = m
            mesh.materials.append(mats[group])
        objs[name] = ob
    return objs


def export_obj(path):
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in bpy.data.collections[COLLECTION_NAME].objects:
        ob.select_set(True)
    bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True, export_materials=ASSIGN_COLORS)
    print("exported", path)


def main():
    if MEASURE_FROM_OBJ:
        apply_measurement(MEASURE_FROM_OBJ)
    validate_and_fit()
    parts = build_parts()
    objs = create_in_blender(parts)
    print(f"created {len(objs)} parts: {', '.join(objs)}")
    if EXPORT_OBJ_PATH:
        export_obj(EXPORT_OBJ_PATH)
    return objs


_PARAMETER_NAMES = {"NUM_ARMS", "ARM_LENGTHS", "ARM_ANGLES", "NUM_FINGER_SEGMENTS", "FINGER_LENGTHS", "FINGER_ANGLES_L",
                    "FINGER_ANGLES_R", "SINGLE_FINGER_BEND", "SINGLE_FINGER_SPLIT", "SHOULDER_HEIGHT", "FINGER_SPACING", "MEASURE_FROM_OBJ", "EXPORT_OBJ_PATH",
                    "CLEAR_PREVIOUS", "COLLECTION_NAME", "ASSIGN_COLORS"}


def create_robot_arm(remove_arm=None, **params):
    """
    Build the arm with the given parameters (anything left out keeps the defaults at the top of the file).

        create_robot_arm()                                  # the original 4-arm robot
        create_robot_arm(remove_arm=3)                      # drop arm.03 -> 3 arms (lengths/angles of arm.04 move up to arm.03)
        create_robot_arm(arm_lengths=[3, 3], arm_angles=[20, -30], num_arms=2)
        create_robot_arm(num_finger_segments=3, finger_lengths=[.7, .7, .7],
                         finger_angles_l=[30, -40, -40], finger_angles_r=[-30, 40, 40])

    remove_arm : 1-based number of the arm segment to delete (its length and angle are removed from the lists,
                 so every later arm is renumbered and the hand moves with the chain).
    params     : lower-case names of the parameters at the top (num_arms, arm_lengths, arm_angles,
                 num_finger_segments, finger_lengths, finger_angles_l, finger_angles_r,
                 shoulder_height, finger_spacing, assign_colors, export_obj_path, measure_from_obj).
    """
    for key, value in params.items():
        name = key.upper()
        if name not in _PARAMETER_NAMES:
            raise TypeError(f"unknown parameter '{key}'")
        globals()[name] = list(value) if isinstance(value, (list, tuple)) else value
    if remove_arm is not None:
        k = int(remove_arm) - 1
        if not 0 <= k < NUM_ARMS:
            raise ValueError(f"remove_arm must be between 1 and {NUM_ARMS}")
        globals()["ARM_LENGTHS"] = fit_list(ARM_LENGTHS, NUM_ARMS, None, "ARM_LENGTHS")
        globals()["ARM_ANGLES"] = fit_list(ARM_ANGLES, NUM_ARMS, 0.0, "ARM_ANGLES")
        del ARM_LENGTHS[k], ARM_ANGLES[k]
        globals()["NUM_ARMS"] = NUM_ARMS - 1
    return main()


if __name__ == "__main__":
    # ---- choose ONE of these ----
    create_robot_arm(remove_arm=3)      # 3 arms: arm.03 removed
    # create_robot_arm()                # the original robot (4 arms)
