import argparse
import json
from pathlib import Path

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAPTURE_DIR = (
    REPO_ROOT
    / "UI"
    / "ProntoUI"
    / "ProntoUI"
    / "bin"
    / "Debug"
    / "captures"
    / "1"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "stockage" / "rapport_reconstruction_reelle"
DEFAULT_RECEIVER_MATRIX = REPO_ROOT / "stockage" / "rapport_calibration_reelle" / "MR_reel.txt"
DEFAULT_EMITTER_MATRIX = REPO_ROOT / "stockage" / "rapport_calibration_reelle" / "MEt_from_MR_reel.txt"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Reconstruction 3D reelle a partir des captures d'acquisition et de la calibration reelle."
    )
    parser.add_argument(
        "--captures-dir",
        default=str(DEFAULT_CAPTURE_DIR),
        help="Dossier contenant les captures capture_1.png, capture_2.png, ...",
    )
    parser.add_argument(
        "--receiver-matrix",
        default=str(DEFAULT_RECEIVER_MATRIX),
        help="Chemin vers la matrice recepteur.",
    )
    parser.add_argument(
        "--emitter-matrix",
        default=str(DEFAULT_EMITTER_MATRIX),
        help="Chemin vers la matrice emetteur.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Dossier de sortie du rapport.",
    )
    parser.add_argument(
        "--foreground-threshold",
        type=int,
        default=20,
        help="Seuil de luminance pour ignorer le fond noir sur la derniere capture.",
    )
    parser.add_argument(
        "--z-filter-mm",
        type=float,
        default=200.0,
        help="Conserve les points dans une bande de profondeur autour de la mediane.",
    )
    return parser.parse_args()


def load_capture_images(captures_dir):
    capture_paths = sorted(Path(captures_dir).glob("capture_*.png"))
    if not capture_paths:
        raise FileNotFoundError(f"Aucune capture trouvee dans {captures_dir}.")

    images = []
    for path in capture_paths:
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise FileNotFoundError(f"Capture introuvable ou illisible : {path}")
        images.append(image)

    return capture_paths, images


def compute_binary_stack(images):
    binary_images = []
    for image in images:
        threshold_value, _ = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        binary_images.append((image >= threshold_value).astype(np.uint8))
    return np.stack(binary_images, axis=0)


def localize_fringe_edges(binary_stack):
    bit_count, height, width = binary_stack.shape
    weights = (2 ** np.arange(bit_count - 1, -1, -1)).astype(np.int32)[:, None, None]
    code_map = np.sum(binary_stack * weights, axis=0)

    posi_gauche = np.zeros((height, width), dtype=np.float32)
    posi_droite = np.zeros((height, width), dtype=np.float32)
    posi_globale = np.zeros((height, width), dtype=np.float32)

    for code_value in range(1, 2**bit_count + 1, 2):
        mask = code_map == code_value
        for row_index in range(height):
            columns = np.flatnonzero(mask[row_index])
            if columns.size == 0:
                continue

            left = int(columns[0])
            right = int(columns[-1])
            posi_gauche[row_index, left] = code_value
            posi_droite[row_index, right] = code_value + 1
            posi_globale[row_index, left] = code_value
            posi_globale[row_index, right] = code_value + 1

    return code_map, posi_gauche, posi_droite, posi_globale


def reconstruct_points(mr, me, posi_gauche, last_capture, foreground_threshold, bit_count):
    height, width = posi_gauche.shape
    rows, cols = np.indices((height, width), dtype=np.float64)

    # Le code historique utilise u = ligne et v = colonne.
    mask = (posi_gauche > 0) & (last_capture > foreground_threshold)
    u_r = rows[mask]
    v_r = cols[mask]
    u_e = u_r.copy()
    v_e = posi_gauche[mask] * (width / (2**bit_count))

    point_count = len(u_r)
    if point_count == 0:
        raise RuntimeError("Aucun point de frange valide n'a ete trouve pour la reconstruction.")

    system_matrix = np.zeros((point_count, 4, 3), dtype=np.float64)
    rhs = np.zeros((point_count, 4), dtype=np.float64)

    system_matrix[:, 0, :] = u_e[:, None] * me[2, :3] - me[0, :3]
    system_matrix[:, 1, :] = v_e[:, None] * me[2, :3] - me[1, :3]
    system_matrix[:, 2, :] = u_r[:, None] * mr[2, :3] - mr[0, :3]
    system_matrix[:, 3, :] = v_r[:, None] * mr[2, :3] - mr[1, :3]

    rhs[:, 0] = me[0, 3] - u_e * me[2, 3]
    rhs[:, 1] = me[1, 3] - v_e * me[2, 3]
    rhs[:, 2] = mr[0, 3] - u_r * mr[2, 3]
    rhs[:, 3] = mr[1, 3] - v_r * mr[2, 3]

    at = np.transpose(system_matrix, (0, 2, 1))
    normal_matrix = at @ system_matrix
    normal_rhs = at @ rhs[..., None]
    xyz = np.linalg.solve(normal_matrix, normal_rhs).reshape(point_count, 3)

    intensities = last_capture[mask].astype(np.uint8)
    image_points = np.column_stack([v_r, u_r]).astype(np.float64)
    fringe_codes = posi_gauche[mask].astype(np.float64)
    return xyz, intensities, image_points, fringe_codes, mask


def robust_filter_points(xyz, intensities, image_points, fringe_codes, z_filter_mm):
    finite_mask = np.isfinite(xyz).all(axis=1)
    xyz = xyz[finite_mask]
    intensities = intensities[finite_mask]
    image_points = image_points[finite_mask]
    fringe_codes = fringe_codes[finite_mask]

    z_median = float(np.median(xyz[:, 2]))
    depth_mask = np.abs(xyz[:, 2] - z_median) <= z_filter_mm
    return (
        xyz[depth_mask],
        intensities[depth_mask],
        image_points[depth_mask],
        fringe_codes[depth_mask],
        z_median,
    )


def fit_plane(xyz):
    center = xyz.mean(axis=0)
    _, _, vh = np.linalg.svd(xyz - center, full_matrices=False)
    normal = vh[-1]
    distances = (xyz - center) @ normal
    return center, normal, distances, vh


def compute_central_plane_metrics(xyz, center, vh):
    plane_coords = (xyz - center) @ vh[:2].T
    distances = (xyz - center) @ vh[-1]
    u_min, u_max = np.percentile(plane_coords[:, 0], [5, 95])
    v_min, v_max = np.percentile(plane_coords[:, 1], [5, 95])
    mask = (
        (plane_coords[:, 0] >= u_min)
        & (plane_coords[:, 0] <= u_max)
        & (plane_coords[:, 1] >= v_min)
        & (plane_coords[:, 1] <= v_max)
    )
    central_distances = distances[mask]
    return {
        "central_point_count": int(mask.sum()),
        "central_plane_rmse": float(np.sqrt(np.mean(central_distances**2))),
        "central_plane_p95_abs": float(np.percentile(np.abs(central_distances), 95)),
    }


def save_ply(path, xyz, intensities):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii") as handle:
        handle.write("ply\n")
        handle.write("format ascii 1.0\n")
        handle.write(f"element vertex {len(xyz)}\n")
        handle.write("property float x\n")
        handle.write("property float y\n")
        handle.write("property float z\n")
        handle.write("property uchar red\n")
        handle.write("property uchar green\n")
        handle.write("property uchar blue\n")
        handle.write("end_header\n")
        for (x_value, y_value, z_value), intensity in zip(xyz, intensities):
            value = int(intensity)
            handle.write(f"{x_value:.6f} {y_value:.6f} {z_value:.6f} {value} {value} {value}\n")


def create_capture_montage(capture_paths, images, output_path):
    rows = []
    for path, image in zip(capture_paths, images):
        thumb = cv2.resize(image, (320, 180), interpolation=cv2.INTER_AREA)
        thumb = cv2.cvtColor(thumb, cv2.COLOR_GRAY2BGR)
        cv2.putText(
            thumb,
            path.name,
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
        rows.append(thumb)

    montage = np.vstack(rows)
    cv2.imwrite(str(output_path), montage)


def create_edge_map(last_capture, posi_gauche, output_path):
    edge_map = cv2.cvtColor(last_capture, cv2.COLOR_GRAY2BGR)
    edge_map[posi_gauche > 0] = (0, 255, 0)
    cv2.imwrite(str(output_path), edge_map)


def create_plots(xyz, distances, vh, output_path):
    center = xyz.mean(axis=0)
    plane_coords = (xyz - center) @ vh[:2].T

    figure = plt.figure(figsize=(14, 10))
    ax_3d = figure.add_subplot(221, projection="3d")
    scatter = ax_3d.scatter(xyz[:, 0], xyz[:, 1], xyz[:, 2], c=xyz[:, 2], cmap="jet", s=0.2)
    ax_3d.set_title("Nuage 3D reconstruit")
    ax_3d.set_xlabel("X")
    ax_3d.set_ylabel("Y")
    ax_3d.set_zlabel("Z")
    ax_3d.set_box_aspect([1.2, 1.0, 0.3])
    figure.colorbar(scatter, ax=ax_3d, shrink=0.6)

    ax_profile = figure.add_subplot(222)
    ax_profile.scatter(plane_coords[:, 0], distances, s=0.2, alpha=0.35)
    ax_profile.set_title("Distance a la meilleure plane")
    ax_profile.set_xlabel("Coordonnee plane 1")
    ax_profile.set_ylabel("Residuel")
    ax_profile.grid(True, alpha=0.3)

    ax_map = figure.add_subplot(223)
    hexbin = ax_map.hexbin(
        plane_coords[:, 0],
        plane_coords[:, 1],
        C=distances,
        gridsize=120,
        reduce_C_function=np.mean,
        cmap="coolwarm",
    )
    ax_map.set_title("Carte residuelle")
    ax_map.set_xlabel("Coordonnee plane 1")
    ax_map.set_ylabel("Coordonnee plane 2")
    figure.colorbar(hexbin, ax=ax_map, shrink=0.8)

    ax_hist = figure.add_subplot(224)
    ax_hist.hist(distances, bins=120)
    ax_hist.set_title("Histogramme des residuels")
    ax_hist.set_xlabel("Distance a la meilleure plane")

    plt.tight_layout()
    figure.savefig(str(output_path), dpi=180)
    plt.close(figure)


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    receiver_matrix = np.loadtxt(args.receiver_matrix)
    emitter_matrix = np.loadtxt(args.emitter_matrix)

    capture_paths, images = load_capture_images(args.captures_dir)
    binary_stack = compute_binary_stack(images)
    code_map, posi_gauche, posi_droite, posi_globale = localize_fringe_edges(binary_stack)

    xyz, intensities, image_points, fringe_codes, _ = reconstruct_points(
        receiver_matrix,
        emitter_matrix,
        posi_gauche,
        images[-1],
        args.foreground_threshold,
        len(images),
    )

    xyz_filtered, intensities_filtered, image_points_filtered, fringe_codes_filtered, z_median = robust_filter_points(
        xyz,
        intensities,
        image_points,
        fringe_codes,
        args.z_filter_mm,
    )

    plane_center, plane_normal, plane_distances, vh = fit_plane(xyz_filtered)
    central_metrics = compute_central_plane_metrics(xyz_filtered, plane_center, vh)

    create_capture_montage(capture_paths, images, output_dir / "captures_montage.png")
    create_edge_map(images[-1], posi_gauche, output_dir / "edge_map.png")
    create_plots(xyz_filtered, plane_distances, vh, output_dir / "reconstruction_analysis.png")

    np.savetxt(output_dir / "points_3d_filtered.txt", xyz_filtered, fmt="%.9f")
    np.savetxt(output_dir / "image_points_filtered.txt", image_points_filtered, fmt="%.9f")
    np.savetxt(output_dir / "fringe_codes_filtered.txt", fringe_codes_filtered, fmt="%.9f")
    np.savetxt(output_dir / "PosiGauche.txt", posi_gauche, fmt="%.0f")
    np.savetxt(output_dir / "PosiDroite.txt", posi_droite, fmt="%.0f")
    np.savetxt(output_dir / "PosiGlobale.txt", posi_globale, fmt="%.0f")
    save_ply(output_dir / "point_cloud_filtered.ply", xyz_filtered, intensities_filtered)
    save_ply(output_dir / "point_cloud_raw.ply", xyz, intensities)

    summary = {
        "capture_count": len(capture_paths),
        "receiver_matrix_path": str(Path(args.receiver_matrix)),
        "emitter_matrix_path": str(Path(args.emitter_matrix)),
        "num_points_raw": int(len(xyz)),
        "num_points_filtered": int(len(xyz_filtered)),
        "z_median_raw": z_median,
        "plane_center": plane_center.tolist(),
        "plane_normal": plane_normal.tolist(),
        "plane_rmse": float(np.sqrt(np.mean(plane_distances**2))),
        "plane_std": float(np.std(plane_distances)),
        "plane_p95_abs": float(np.percentile(np.abs(plane_distances), 95)),
        **central_metrics,
        "z_min": float(np.min(xyz_filtered[:, 2])),
        "z_max": float(np.max(xyz_filtered[:, 2])),
        "point_cloud_filtered_ply": str(output_dir / "point_cloud_filtered.ply"),
        "point_cloud_raw_ply": str(output_dir / "point_cloud_raw.ply"),
        "analysis_image": str(output_dir / "reconstruction_analysis.png"),
        "edge_map": str(output_dir / "edge_map.png"),
        "captures_montage": str(output_dir / "captures_montage.png"),
    }

    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
