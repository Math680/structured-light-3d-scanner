import json
from pathlib import Path

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "stockage" / "rapport_calibration_reelle"
RECEIVER_IMAGES = [
    REPO_ROOT / "img" / "damier0.jpg",
    REPO_ROOT / "img" / "damier100.jpg",
]
EMITTER_IMAGES = [
    REPO_ROOT
    / "UI"
    / "ProntoUI"
    / "ProntoUI"
    / "bin"
    / "Debug"
    / "captures"
    / "calibration_emetteur"
    / "capture_calibration_z0.png",
    REPO_ROOT
    / "UI"
    / "ProntoUI"
    / "ProntoUI"
    / "bin"
    / "Debug"
    / "captures"
    / "calibration_emetteur"
    / "capture_calibration_z100.png",
]
PATTERN_SIZE = (7, 6)
BOARD_WIDTH_MM = 995.0
BOARD_HEIGHT_MM = 622.0
Z_LEVELS_MM = [0.0, 100.0]
PROJECTOR_WIDTH_PX = 1280.0
PROJECTOR_HEIGHT_PX = 800.0


def build_receiver_object_points():
    step_x = BOARD_WIDTH_MM / 8.0
    step_y = BOARD_HEIGHT_MM / 7.0
    x_values = np.linspace(-BOARD_WIDTH_MM / 2 + step_x, BOARD_WIDTH_MM / 2 - step_x, PATTERN_SIZE[0])
    y_values = np.linspace(-BOARD_HEIGHT_MM / 2 + step_y, BOARD_HEIGHT_MM / 2 - step_y, PATTERN_SIZE[1])
    plane_points = np.array([[x_value, y_value] for y_value in y_values for x_value in x_values], dtype=np.float64)
    object_points = []
    for z_value in Z_LEVELS_MM:
        object_points.append(np.column_stack([plane_points, np.full((len(plane_points), 1), z_value)]))
    return plane_points, np.vstack(object_points)


def build_projector_points():
    x_values = np.linspace(PROJECTOR_WIDTH_PX / 8.0, PROJECTOR_WIDTH_PX - PROJECTOR_WIDTH_PX / 8.0, PATTERN_SIZE[0])
    y_values = np.linspace(PROJECTOR_HEIGHT_PX / 8.0, PROJECTOR_HEIGHT_PX - 2.0 * (PROJECTOR_HEIGHT_PX / 8.0), PATTERN_SIZE[1])
    plane_points = np.array([[x_value, y_value] for y_value in y_values for x_value in x_values], dtype=np.float64)
    return np.vstack([plane_points, plane_points])


def detect_chessboard_points(image_path, label):
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Image introuvable : {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCornersSB(
        gray,
        PATTERN_SIZE,
        flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY,
    )
    if not found:
        raise RuntimeError(f"Damier {PATTERN_SIZE} non detecte dans {image_path}.")

    points = corners.reshape(-1, 2)
    annotated = image.copy()
    cv2.drawChessboardCorners(annotated, PATTERN_SIZE, corners, found)

    for index, (x_value, y_value) in enumerate(points, start=1):
        cv2.putText(
            annotated,
            str(index),
            (int(x_value) + 6, int(y_value) - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{label}_points.png"
    cv2.imwrite(str(output_path), annotated)
    return points, output_path


def compute_projection_matrix(object_points, image_points):
    point_count = len(object_points)
    b_matrix = np.zeros((2 * point_count, 11), dtype=np.float64)
    c_vector = np.zeros((2 * point_count, 1), dtype=np.float64)

    for index, ((x_value, y_value, z_value), (u_value, v_value)) in enumerate(zip(object_points, image_points)):
        row = 2 * index
        b_matrix[row] = [
            x_value,
            y_value,
            z_value,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            -u_value * x_value,
            -u_value * y_value,
            -u_value * z_value,
        ]
        c_vector[row] = u_value

        b_matrix[row + 1] = [
            0.0,
            0.0,
            0.0,
            0.0,
            x_value,
            y_value,
            z_value,
            1.0,
            -v_value * x_value,
            -v_value * y_value,
            -v_value * z_value,
        ]
        c_vector[row + 1] = v_value

    solution = np.linalg.pinv(b_matrix) @ c_vector
    return np.append(solution.flatten(), 1.0).reshape(3, 4)


def denormalize_projection_matrix(matrix_norm):
    scale = 1.0 / np.linalg.norm(matrix_norm[2, :3])
    return matrix_norm * scale


def reprojection_error(matrix, object_points, image_points):
    homogeneous_points = np.hstack([object_points, np.ones((len(object_points), 1))])
    projection = (matrix @ homogeneous_points.T).T
    projection = projection[:, :2] / projection[:, 2:3]
    errors = np.linalg.norm(projection - image_points, axis=1)
    return float(errors.mean()), float(errors.max()), projection


def reconstruct_object_points(receiver_matrix_norm, receiver_image_points):
    reconstructed_points = []
    depths = np.array([0.0] * (len(receiver_image_points) // 2) + [100.0] * (len(receiver_image_points) // 2), dtype=np.float64)

    for (u_value, v_value), z_value in zip(receiver_image_points, depths):
        system_matrix = np.array(
            [
                [
                    u_value * receiver_matrix_norm[2, 0] - receiver_matrix_norm[0, 0],
                    u_value * receiver_matrix_norm[2, 1] - receiver_matrix_norm[0, 1],
                ],
                [
                    v_value * receiver_matrix_norm[2, 0] - receiver_matrix_norm[1, 0],
                    v_value * receiver_matrix_norm[2, 1] - receiver_matrix_norm[1, 1],
                ],
            ],
            dtype=np.float64,
        )

        rhs = np.array(
            [
                (receiver_matrix_norm[0, 2] - u_value * receiver_matrix_norm[2, 2]) * z_value
                + receiver_matrix_norm[0, 3]
                - u_value,
                (receiver_matrix_norm[1, 2] - v_value * receiver_matrix_norm[2, 2]) * z_value
                + receiver_matrix_norm[1, 3]
                - v_value,
            ],
            dtype=np.float64,
        )

        x_value, y_value = np.linalg.solve(system_matrix, rhs)
        reconstructed_points.append([x_value, y_value, z_value])

    return np.array(reconstructed_points, dtype=np.float64)


def create_summary_image(receiver_image_path, emitter_image_path):
    receiver_image = cv2.imread(str(receiver_image_path))
    emitter_image = cv2.imread(str(emitter_image_path))

    target_width = 900
    receiver_scale = target_width / receiver_image.shape[1]
    emitter_scale = target_width / emitter_image.shape[1]

    receiver_resized = cv2.resize(receiver_image, (target_width, int(receiver_image.shape[0] * receiver_scale)))
    emitter_resized = cv2.resize(emitter_image, (target_width, int(emitter_image.shape[0] * emitter_scale)))

    separator = np.full((24, target_width, 3), 35, dtype=np.uint8)
    canvas = np.vstack([receiver_resized, separator, emitter_resized])

    cv2.putText(canvas, "Calibration recepteur", (20, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(
        canvas,
        "Calibration emetteur",
        (20, receiver_resized.shape[0] + separator.shape[0] + 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    output_path = OUTPUT_DIR / "resume_calibration.png"
    cv2.imwrite(str(output_path), canvas)
    return output_path


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    receiver_plane_points, receiver_object_points = build_receiver_object_points()
    projector_points = build_projector_points()

    receiver_detections = []
    receiver_outputs = []
    for image_path, label in zip(RECEIVER_IMAGES, ["recepteur_z0", "recepteur_z100"]):
        detected_points, output_path = detect_chessboard_points(image_path, label)
        receiver_detections.append(detected_points)
        receiver_outputs.append(output_path)

    receiver_image_points = np.vstack(receiver_detections)
    receiver_matrix_norm = compute_projection_matrix(receiver_object_points, receiver_image_points)
    receiver_matrix = denormalize_projection_matrix(receiver_matrix_norm)
    receiver_mean_error, receiver_max_error, _ = reprojection_error(receiver_matrix, receiver_object_points, receiver_image_points)

    np.savetxt(OUTPUT_DIR / "MRN_reel.txt", receiver_matrix_norm, fmt="%.9f")
    np.savetxt(OUTPUT_DIR / "MR_reel.txt", receiver_matrix, fmt="%.9f")

    emitter_detections = []
    emitter_outputs = []
    for image_path, label in zip(EMITTER_IMAGES, ["emetteur_z0", "emetteur_z100"]):
        detected_points, output_path = detect_chessboard_points(image_path, label)
        emitter_detections.append(detected_points)
        emitter_outputs.append(output_path)

    emitter_camera_points = np.vstack(emitter_detections)
    reconstructed_object_points = reconstruct_object_points(receiver_matrix_norm / receiver_matrix_norm[2, 3], emitter_camera_points)
    emitter_matrix_norm = compute_projection_matrix(reconstructed_object_points, projector_points)
    emitter_legacy_path = REPO_ROOT / "stockage" / "MEt.txt"
    t3_emitter = np.loadtxt(emitter_legacy_path)[2, 3] if emitter_legacy_path.exists() else 1.0
    emitter_matrix = emitter_matrix_norm * t3_emitter
    emitter_mean_error, emitter_max_error, _ = reprojection_error(emitter_matrix_norm, reconstructed_object_points, projector_points)

    np.savetxt(OUTPUT_DIR / "MEt_from_MR_reel_norm.txt", emitter_matrix_norm, fmt="%.9f")
    np.savetxt(OUTPUT_DIR / "MEt_from_MR_reel.txt", emitter_matrix, fmt="%.9f")
    np.savetxt(OUTPUT_DIR / "points_objet_reconstruits_emetteur.txt", reconstructed_object_points, fmt="%.9f")

    summary_image = create_summary_image(receiver_outputs[0], emitter_outputs[0])

    summary = {
        "receiver_mean_reprojection_error_px": receiver_mean_error,
        "receiver_max_reprojection_error_px": receiver_max_error,
        "emitter_mean_reprojection_error_px": emitter_mean_error,
        "emitter_max_reprojection_error_px": emitter_max_error,
        "receiver_images": [str(path) for path in receiver_outputs],
        "emitter_images": [str(path) for path in emitter_outputs],
        "summary_image": str(summary_image),
        "receiver_matrix_path": str(OUTPUT_DIR / "MR_reel.txt"),
        "emitter_matrix_path": str(OUTPUT_DIR / "MEt_from_MR_reel.txt"),
    }
    (OUTPUT_DIR / "resume_final.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
