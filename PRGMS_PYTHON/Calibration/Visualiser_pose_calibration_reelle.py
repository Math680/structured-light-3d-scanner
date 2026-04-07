import json
from pathlib import Path

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[2]
CALIB_DIR = REPO_ROOT / "stockage" / "rapport_calibration_reelle"
OUTPUT_DIR = REPO_ROOT / "stockage" / "rapport_pose_calibration"
MR_PATH = CALIB_DIR / "MR_reel.txt"
ME_PATH = CALIB_DIR / "MEt_from_MR_reel.txt"


def load_pose(matrix_path):
    projection_matrix = np.loadtxt(matrix_path)
    camera_matrix, rotation_matrix, translation_homogeneous, *_ = cv2.decomposeProjectionMatrix(projection_matrix)

    center = (translation_homogeneous[:3] / translation_homogeneous[3]).reshape(3)
    forward = rotation_matrix.T @ np.array([0.0, 0.0, 1.0])
    right = rotation_matrix.T @ np.array([1.0, 0.0, 0.0])
    up = rotation_matrix.T @ np.array([0.0, 1.0, 0.0])

    forward /= np.linalg.norm(forward)
    right /= np.linalg.norm(right)
    up /= np.linalg.norm(up)

    return {
        "projection_matrix": projection_matrix,
        "center": center,
        "forward": forward,
        "right": right,
        "up": up,
        "camera_matrix": camera_matrix,
    }


def intersect_axis_with_plane(center, forward, z_value):
    scale = (z_value - center[2]) / forward[2]
    return center + scale * forward


def create_pose_figure(receiver_pose, emitter_pose, output_path, invert_forward=False):
    plane_x = np.linspace(-200, 800, 2)
    plane_y = np.linspace(-350, 350, 2)
    mesh_x, mesh_y = np.meshgrid(plane_x, plane_y)

    figure = plt.figure(figsize=(16, 10))
    ax_3d = figure.add_subplot(221, projection="3d")
    ax_top = figure.add_subplot(222)
    ax_side = figure.add_subplot(224)

    for z_value, color, alpha in ((0.0, "#dfe7f5", 0.35), (100.0, "#fde2e2", 0.25)):
        mesh_z = np.full_like(mesh_x, z_value)
        ax_3d.plot_surface(mesh_x, mesh_y, mesh_z, color=color, alpha=alpha, shade=False)
        ax_side.fill_between([plane_x.min(), plane_x.max()], z_value - 1.0, z_value + 1.0, color=color, alpha=0.35)
        ax_top.plot([plane_x.min(), plane_x.max()], [0.0, 0.0], alpha=0.0)

    for label, pose, color in (("Camera", receiver_pose, "#1f77b4"), ("Projecteur", emitter_pose, "#d62728")):
        center = pose["center"]
        forward = -pose["forward"] if invert_forward else pose["forward"]
        right = pose["right"]
        up = pose["up"]
        axis_length = 220.0
        z0_point = intersect_axis_with_plane(center, forward, 0.0)

        ax_3d.scatter(*center, color=color, s=55)
        ax_3d.quiver(*center, *(forward * axis_length), color=color, linewidth=2)
        ax_3d.quiver(*center, *(right * (axis_length * 0.55)), color="#2ca02c", linewidth=1.2)
        ax_3d.quiver(*center, *(up * (axis_length * 0.55)), color="#9467bd", linewidth=1.2)
        ax_3d.plot([center[0], z0_point[0]], [center[1], z0_point[1]], [center[2], z0_point[2]], color=color, linestyle="--", alpha=0.85)
        ax_3d.text(center[0], center[1], center[2] + 20.0, label, color=color)

        ax_top.scatter(center[0], center[1], color=color, s=55)
        ax_top.arrow(center[0], center[1], forward[0] * axis_length, forward[1] * axis_length, color=color, width=3.0, length_includes_head=True)
        ax_top.plot([center[0], z0_point[0]], [center[1], z0_point[1]], color=color, linestyle="--", alpha=0.85)
        ax_top.text(center[0] + 10.0, center[1] + 10.0, label, color=color)

        ax_side.scatter(center[0], center[2], color=color, s=55)
        ax_side.arrow(center[0], center[2], forward[0] * axis_length, forward[2] * axis_length, color=color, width=4.0, length_includes_head=True)
        ax_side.plot([center[0], z0_point[0]], [center[2], z0_point[2]], color=color, linestyle="--", alpha=0.85)
        ax_side.text(center[0] + 10.0, center[2] + 10.0, label, color=color)

    baseline = np.linalg.norm(receiver_pose["center"] - emitter_pose["center"])
    ax_3d.plot(
        [receiver_pose["center"][0], emitter_pose["center"][0]],
        [receiver_pose["center"][1], emitter_pose["center"][1]],
        [receiver_pose["center"][2], emitter_pose["center"][2]],
        color="black",
        linewidth=1.2,
    )
    ax_top.plot(
        [receiver_pose["center"][0], emitter_pose["center"][0]],
        [receiver_pose["center"][1], emitter_pose["center"][1]],
        color="black",
        linewidth=1.2,
    )
    ax_top.text(
        (receiver_pose["center"][0] + emitter_pose["center"][0]) * 0.5,
        (receiver_pose["center"][1] + emitter_pose["center"][1]) * 0.5 + 12.0,
        f"Baseline ~ {baseline:.1f} mm",
        color="black",
    )

    ax_3d.set_title("Vue 3D a l'echelle")
    ax_3d.set_xlabel("X (mm)")
    ax_3d.set_ylabel("Y (mm)")
    ax_3d.set_zlabel("Z (mm)")
    ax_3d.set_box_aspect((1.2, 1.0, 0.9))
    ax_3d.view_init(elev=20, azim=-55)

    ax_top.set_title("Vue de dessus (X/Y)")
    ax_top.set_xlabel("X (mm)")
    ax_top.set_ylabel("Y (mm)")
    ax_top.grid(True, alpha=0.25)
    ax_top.axis("equal")

    ax_side.set_title("Vue de profil (X/Z)")
    ax_side.set_xlabel("X (mm)")
    ax_side.set_ylabel("Z (mm)")
    ax_side.grid(True, alpha=0.25)
    ax_side.axis("equal")

    title_suffix = " (fleches inversees)" if invert_forward else ""
    figure.suptitle(f"Position relative Camera / Projecteur issue de la calibration reelle{title_suffix}", fontsize=14)
    plt.tight_layout()
    figure.savefig(str(output_path), dpi=180)
    plt.close(figure)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    receiver_pose = load_pose(MR_PATH)
    emitter_pose = load_pose(ME_PATH)

    receiver_center = receiver_pose["center"]
    emitter_center = emitter_pose["center"]
    receiver_forward = receiver_pose["forward"]
    emitter_forward = emitter_pose["forward"]

    baseline = float(np.linalg.norm(receiver_center - emitter_center))
    optical_angle_deg = float(
        np.degrees(np.arccos(np.clip(np.dot(receiver_forward, emitter_forward), -1.0, 1.0)))
    )

    receiver_hit_z0 = intersect_axis_with_plane(receiver_center, receiver_forward, 0.0)
    emitter_hit_z0 = intersect_axis_with_plane(emitter_center, emitter_forward, 0.0)
    receiver_hit_z100 = intersect_axis_with_plane(receiver_center, receiver_forward, 100.0)
    emitter_hit_z100 = intersect_axis_with_plane(emitter_center, emitter_forward, 100.0)

    figure_path = OUTPUT_DIR / "pose_camera_projecteur.png"
    figure_inverted_path = OUTPUT_DIR / "pose_camera_projecteur_fleches_inversees.png"
    create_pose_figure(receiver_pose, emitter_pose, figure_path, invert_forward=False)
    create_pose_figure(receiver_pose, emitter_pose, figure_inverted_path, invert_forward=True)

    summary = {
        "receiver_center_mm": receiver_center.tolist(),
        "receiver_forward": receiver_forward.tolist(),
        "emitter_center_mm": emitter_center.tolist(),
        "emitter_forward": emitter_forward.tolist(),
        "baseline_mm": baseline,
        "optical_axis_angle_deg": optical_angle_deg,
        "receiver_optical_axis_intersection_z0_mm": receiver_hit_z0.tolist(),
        "emitter_optical_axis_intersection_z0_mm": emitter_hit_z0.tolist(),
        "receiver_optical_axis_intersection_z100_mm": receiver_hit_z100.tolist(),
        "emitter_optical_axis_intersection_z100_mm": emitter_hit_z100.tolist(),
        "figure_path": str(figure_path),
        "figure_inverted_path": str(figure_inverted_path),
    }

    (OUTPUT_DIR / "resume_pose.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
