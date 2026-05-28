import json
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURES_DIR = PROJECT_ROOT / "captures" / "captures"
DEBUG_DIR = PROJECT_ROOT / "resultats" / "diagnostics_calibration"
OUTPUT_DIR = PROJECT_ROOT / "calibration_validee"

BOARD_WIDTH_MM = 995.0
BOARD_HEIGHT_MM = 622.0
RECEIVER_PATTERN = (8, 6)
EMITTER_PATTERN = (7, 7)
PROJECTOR_WIDTH_PX = 1280.0
PROJECTOR_HEIGHT_PX = 800.0
# Les captures recentes donnent bien 8 colonnes x 6 lignes detectees, mais
# l'ecart vertical physique correspond a un peu plus que rows+1 cases.
RECEIVER_VERTICAL_STEP_DENOMINATOR = 7.68

POINT_RADIUS = 8
PICK_RADIUS = 18


def imread(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Image illisible : {path}")
    return image


def imwrite(path, image):
    path.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(path.suffix, image)
    if not success:
        raise RuntimeError(f"Impossible d'encoder : {path}")
    encoded.tofile(str(path))


def load_mask(folder, image_shape):
    mask_path = folder / "mask_config.json"
    if not mask_path.exists():
        return None, None

    config = json.loads(mask_path.read_text(encoding="utf-8"))
    polygon = np.array(config["points"], dtype=np.int32)
    mask = np.zeros(image_shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [polygon], 255)
    return mask, polygon


def apply_mask(image, mask):
    if mask is None:
        return image.copy()
    masked = image.copy()
    masked[mask == 0] = 0
    return masked


def detect_chessboard_points(image, pattern, is_emitter=False):
    if is_emitter:
        red_minus_blue = cv2.subtract(image[:, :, 2], image[:, :, 0])
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        images_to_try = [
            gray,
            cv2.equalizeHist(gray),
            red_minus_blue,
            cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(red_minus_blue),
        ]
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        images_to_try = [
            gray,
            cv2.equalizeHist(gray),
            cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray),
        ]

    for candidate in images_to_try:
        found, corners = cv2.findChessboardCornersSB(
            candidate,
            pattern,
            flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY | cv2.CALIB_CB_NORMALIZE_IMAGE,
        )
        if not found:
            found, corners = cv2.findChessboardCorners(
                candidate,
                pattern,
                flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
            )
            if found:
                criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.001)
                corners = cv2.cornerSubPix(candidate, corners, (11, 11), (-1, -1), criteria)
        if found:
            return corners.reshape(-1, 2)

    raise RuntimeError(f"Damier {pattern} non detecte.")


def order_reading(points, cols, rows):
    sorted_by_y = points[np.argsort(points[:, 1], kind="mergesort")]
    ordered_rows = []
    for row_index in range(rows):
        row = sorted_by_y[row_index * cols : (row_index + 1) * cols]
        ordered_rows.append(row[np.argsort(row[:, 0], kind="mergesort")])
    return np.vstack(ordered_rows)


def initial_receiver_z100_points(image):
    points_8x6 = None
    try:
        points_8x6 = detect_chessboard_points(image, RECEIVER_PATTERN)
    except RuntimeError:
        pass

    if points_8x6 is not None:
        return order_reading(points_8x6, *RECEIVER_PATTERN)

    points_7x6 = detect_chessboard_points(image, (7, 6))
    grid = points_7x6.reshape(6, 7, 2)
    grid_reading_7 = np.flipud(np.fliplr(grid))
    step_right = grid_reading_7[:, -1, :] - grid_reading_7[:, -2, :]
    extra_col = grid_reading_7[:, -1, :] + step_right
    grid_reading_8 = np.concatenate([grid_reading_7, extra_col[:, None, :]], axis=1)
    return grid_reading_8.reshape(-1, 2)


def load_points_or_detect(name, image, pattern, is_emitter=False):
    candidates = {
        "recepteur_z0": [
            DEBUG_DIR / "recepteur_z0_points_opencv_order.txt",
            DEBUG_DIR / "recepteur_z0_points.txt",
        ],
        "recepteur_z100": [
            DEBUG_DIR / "recepteur_z100_points_lecture_8x6.txt",
            DEBUG_DIR / "recepteur_z100_points_lecture.txt",
        ],
        "emetteur_z0": [
            DEBUG_DIR / "emetteur_z0_points.txt",
        ],
        "emetteur_z100": [
            DEBUG_DIR / "emetteur_z100_points.txt",
        ],
    }

    for path in candidates.get(name, []):
        if path.exists():
            points = np.loadtxt(path, dtype=np.float64)
            points = np.atleast_2d(points)
            if len(points) == pattern[0] * pattern[1]:
                return points

    if name == "recepteur_z100":
        return initial_receiver_z100_points(image)

    points = detect_chessboard_points(image, pattern, is_emitter=is_emitter)
    if name == "recepteur_z0":
        return order_reading(points, *pattern)
    return points


def receiver_object_points():
    cols, rows = RECEIVER_PATTERN
    step_x = BOARD_WIDTH_MM / (cols + 1)
    step_y = BOARD_HEIGHT_MM / RECEIVER_VERTICAL_STEP_DENOMINATOR
    x_values = np.linspace(-BOARD_WIDTH_MM / 2 + step_x, BOARD_WIDTH_MM / 2 - step_x, cols)
    y_values = np.linspace(-step_y * (rows - 1) / 2.0, step_y * (rows - 1) / 2.0, rows)
    plane = np.array([[x_value, y_value] for y_value in y_values for x_value in x_values], dtype=np.float64)
    return np.vstack(
        [
            np.column_stack([plane, np.zeros(len(plane))]),
            np.column_stack([plane, np.full(len(plane), 100.0)]),
        ]
    )


def projector_points():
    cols, rows = EMITTER_PATTERN
    x_values = np.linspace(PROJECTOR_WIDTH_PX / 8.0, PROJECTOR_WIDTH_PX - PROJECTOR_WIDTH_PX / 8.0, cols)
    y_values = np.linspace(PROJECTOR_HEIGHT_PX / 8.0, PROJECTOR_HEIGHT_PX - PROJECTOR_HEIGHT_PX / 8.0, rows)
    plane = np.array([[x_value, y_value] for y_value in y_values for x_value in x_values], dtype=np.float64)
    return np.vstack([plane, plane])


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
    return matrix_norm * (1.0 / np.linalg.norm(matrix_norm[2, :3]))


def reprojection_error(matrix, object_points, image_points):
    homogeneous = np.hstack([object_points, np.ones((len(object_points), 1))])
    projection = (matrix @ homogeneous.T).T
    projection = projection[:, :2] / projection[:, 2:3]
    errors = np.linalg.norm(projection - image_points, axis=1)
    return float(errors.mean()), float(errors.max())


def reconstruct_object_points(receiver_matrix_norm, receiver_points, depths):
    object_points = []
    for (u_value, v_value), z_value in zip(receiver_points, depths):
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
                - u_value * receiver_matrix_norm[2, 3],
                (receiver_matrix_norm[1, 2] - v_value * receiver_matrix_norm[2, 2]) * z_value
                + receiver_matrix_norm[1, 3]
                - v_value * receiver_matrix_norm[2, 3],
            ],
            dtype=np.float64,
        )
        x_value, y_value = np.linalg.solve(system_matrix, rhs)
        object_points.append([x_value, y_value, z_value])
    return np.array(object_points, dtype=np.float64)


def draw_points(view):
    image = view["display"].copy()
    points = view["points"]
    for index, (x_value, y_value) in enumerate(points, start=1):
        is_selected = index - 1 == view["selected"]
        color = (0, 255, 255) if is_selected else (0, 255, 0)
        point = (int(round(x_value)), int(round(y_value)))
        cv2.circle(image, point, POINT_RADIUS, color, 2)
        cv2.circle(image, point, 3, (0, 0, 255), -1)
        cv2.putText(
            image,
            str(index),
            (point[0] + 7, point[1] - 7),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    if view["polygon"] is not None:
        cv2.polylines(image, [view["polygon"]], True, (255, 0, 255), 2, cv2.LINE_AA)

    cv2.rectangle(image, (0, 0), (image.shape[1], 58), (0, 0, 0), -1)
    cv2.putText(image, view["title"], (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(
        image,
        "S=sauver  N/P=image  clic+glisser=deplacer  WASD=1px  R=recharger  Q=quitter",
        (12, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return image


def save_calibration(views):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    points = {view["name"]: view["points"].copy() for view in views}

    for name, values in points.items():
        np.savetxt(OUTPUT_DIR / f"{name}_points.txt", values, fmt="%.6f")

    receiver_image_points = np.vstack([points["recepteur_z0"], points["recepteur_z100"]])
    receiver_points_3d = receiver_object_points()
    receiver_matrix_norm = compute_projection_matrix(receiver_points_3d, receiver_image_points)
    receiver_matrix = denormalize_projection_matrix(receiver_matrix_norm)
    receiver_mean_error, receiver_max_error = reprojection_error(receiver_matrix, receiver_points_3d, receiver_image_points)

    emitter_camera_points = np.vstack([points["emetteur_z0"], points["emetteur_z100"]])
    emitter_depths = np.concatenate(
        [
            np.zeros(len(points["emetteur_z0"]), dtype=np.float64),
            np.full(len(points["emetteur_z100"]), 100.0, dtype=np.float64),
        ]
    )
    emitter_points_3d = reconstruct_object_points(receiver_matrix_norm / receiver_matrix_norm[2, 3], emitter_camera_points, emitter_depths)
    emitter_matrix_norm = compute_projection_matrix(emitter_points_3d, projector_points())
    emitter_matrix = denormalize_projection_matrix(emitter_matrix_norm)
    emitter_mean_error, emitter_max_error = reprojection_error(emitter_matrix_norm, emitter_points_3d, projector_points())

    np.savetxt(OUTPUT_DIR / "MR_normalise.txt", receiver_matrix_norm, fmt="%.9f")
    np.savetxt(OUTPUT_DIR / "MR.txt", receiver_matrix, fmt="%.9f")
    np.savetxt(OUTPUT_DIR / "ME_normalise.txt", emitter_matrix_norm, fmt="%.9f")
    np.savetxt(OUTPUT_DIR / "ME.txt", emitter_matrix, fmt="%.9f")
    np.savetxt(OUTPUT_DIR / "points_objet_emetteur.txt", emitter_points_3d, fmt="%.9f")

    # Copies gardees pour pouvoir relire les resultats plus anciens sans changer les scripts.
    np.savetxt(OUTPUT_DIR / "MRN_corrige.txt", receiver_matrix_norm, fmt="%.9f")
    np.savetxt(OUTPUT_DIR / "MR_corrige.txt", receiver_matrix, fmt="%.9f")
    np.savetxt(OUTPUT_DIR / "ME_corrige_norm.txt", emitter_matrix_norm, fmt="%.9f")
    np.savetxt(OUTPUT_DIR / "ME_corrige.txt", emitter_matrix, fmt="%.9f")
    np.savetxt(OUTPUT_DIR / "points_objet_emetteur_corriges.txt", emitter_points_3d, fmt="%.9f")

    summary = {
        "receiver_mean_reprojection_error_px": receiver_mean_error,
        "receiver_max_reprojection_error_px": receiver_max_error,
        "emitter_mean_reprojection_error_px": emitter_mean_error,
        "emitter_max_reprojection_error_px": emitter_max_error,
        "receiver_matrix_path": str(OUTPUT_DIR / "MR.txt"),
        "emitter_matrix_path": str(OUTPUT_DIR / "ME.txt"),
    }
    (OUTPUT_DIR / "resume_calibration.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "resume_calibration_corrigee.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    for view in views:
        imwrite(OUTPUT_DIR / f"{view['name']}_controle.png", draw_points(view))

    print(json.dumps(summary, indent=2))
    print(f"Calibration sauvegardee dans : {OUTPUT_DIR}")


def build_views():
    items = [
        {
            "name": "recepteur_z0",
            "title": "Recepteur Z=0 - 8x6",
            "path": CAPTURES_DIR / "calibration_recepteur" / "damier0.png",
            "pattern": RECEIVER_PATTERN,
            "mask_folder": CAPTURES_DIR / "calibration_recepteur",
            "is_emitter": False,
        },
        {
            "name": "recepteur_z100",
            "title": "Recepteur Z=100 - 8x6",
            "path": CAPTURES_DIR / "calibration_recepteur" / "damier100.png",
            "pattern": RECEIVER_PATTERN,
            "mask_folder": CAPTURES_DIR / "calibration_recepteur",
            "is_emitter": False,
        },
        {
            "name": "emetteur_z0",
            "title": "Emetteur Z=0 - 7x7",
            "path": CAPTURES_DIR / "calibration_emetteur" / "capture_calibration_z0.png",
            "pattern": EMITTER_PATTERN,
            "mask_folder": CAPTURES_DIR / "calibration_emetteur",
            "is_emitter": True,
        },
        {
            "name": "emetteur_z100",
            "title": "Emetteur Z=100 - 7x7",
            "path": CAPTURES_DIR / "calibration_emetteur" / "capture_calibration_z100.png",
            "pattern": EMITTER_PATTERN,
            "mask_folder": CAPTURES_DIR / "calibration_emetteur",
            "is_emitter": True,
        },
    ]

    views = []
    for item in items:
        image = imread(item["path"])
        polygon = None
        display = image
        if item["mask_folder"] is not None:
            mask, polygon = load_mask(item["mask_folder"], image.shape)
            display = apply_mask(image, mask)

        points = load_points_or_detect(
            item["name"],
            display,
            item["pattern"],
            is_emitter=item["is_emitter"],
        )
        views.append(
            {
                **item,
                "image": image,
                "display": display,
                "points": points.astype(np.float64),
                "initial_points": points.astype(np.float64).copy(),
                "polygon": polygon,
                "selected": -1,
                "dragging": False,
            }
        )
    return views


def main():
    views = build_views()
    state = {"index": 0}
    window_name = "Ajustement points calibration"

    def active_view():
        return views[state["index"]]

    def mouse_callback(event, x_value, y_value, flags, param):
        view = active_view()
        if event == cv2.EVENT_LBUTTONDOWN:
            distances = np.linalg.norm(view["points"] - np.array([x_value, y_value], dtype=np.float64), axis=1)
            nearest = int(np.argmin(distances))
            if distances[nearest] <= PICK_RADIUS:
                view["selected"] = nearest
                view["dragging"] = True
                view["points"][nearest] = [x_value, y_value]
        elif event == cv2.EVENT_MOUSEMOVE and view["dragging"] and view["selected"] >= 0:
            view["points"][view["selected"]] = [x_value, y_value]
        elif event == cv2.EVENT_LBUTTONUP:
            view["dragging"] = False

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)
    cv2.setMouseCallback(window_name, mouse_callback)

    print("Commandes :")
    print("  clic + glisser : deplacer un point")
    print("  N / P : image suivante / precedente")
    print("  W A S D : deplacer le point selectionne de 1 pixel")
    print("  R : recharger les points initiaux de l'image courante")
    print("  S : sauvegarder points + matrices MR/ME")
    print("  Q ou Echap : quitter")

    while True:
        view = active_view()
        cv2.imshow(window_name, draw_points(view))
        key = cv2.waitKeyEx(20)
        if key < 0:
            continue

        key_char = chr(key & 0xFF).lower() if key < 256 else ""
        if key_char == "q" or key == 27:
            break
        if key_char == "n":
            state["index"] = (state["index"] + 1) % len(views)
        elif key_char == "p":
            state["index"] = (state["index"] - 1) % len(views)
        elif key_char == "r":
            view["points"] = view["initial_points"].copy()
        elif key_char == "s":
            save_calibration(views)
        elif key_char in ("w", "a", "s", "d") and view["selected"] >= 0:
            delta = {
                "w": np.array([0.0, -1.0]),
                "a": np.array([-1.0, 0.0]),
                "s": np.array([0.0, 1.0]),
                "d": np.array([1.0, 0.0]),
            }[key_char]
            view["points"][view["selected"]] += delta

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
