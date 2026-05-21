from __future__ import annotations

import math
import random
from collections import defaultdict
from itertools import combinations
from typing import Any

from rdkit import Chem, RDLogger
from rdkit.Chem import rdFingerprintGenerator

from app.chem.descriptors import calculate_descriptors


RDLogger.DisableLog("rdApp.warning")

FINGERPRINT_SIZE = 256
FINGERPRINT_GENERATOR = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=FINGERPRINT_SIZE)
RANDOM_SEED = 17
MAX_TSNE_LANDMARKS = 1000
REAL_TSNE_LIMIT = 500

FRAGMENT_SMILES = tuple(
    dict.fromkeys(
        [
            "[*:1]F",
            "[*:1]Cl",
            "[*:1]Br",
            "[*:1]C",
            "[*:1]CC",
            "[*:1]CCC",
            "[*:1]CCCC",
            "[*:1]CCCCC",
            "[*:1]C(C)C",
            "[*:1]C(C)(C)C",
            "[*:1]C(F)(F)F",
            "[*:1]C#N",
            "[*:1]C(=O)N",
            "[*:1]C(=O)NC",
            "[*:1]C(=O)OC",
            "[*:1]C(=O)O",
            "[*:1]C(=O)C",
            "[*:1]C(=O)CF",
            "[*:1]C(=O)N(C)C",
            "[*:1]CO",
            "[*:1]COC",
            "[*:1]COCC",
            "[*:1]CON",
            "[*:1]CN",
            "[*:1]CNC",
            "[*:1]CN(C)C",
            "[*:1]CN1CCOCC1",
            "[*:1]CN1CCNCC1",
            "[*:1]CN1CCCC1",
            "[*:1]O",
            "[*:1]OC",
            "[*:1]OCC",
            "[*:1]OCCC",
            "[*:1]OC(C)C",
            "[*:1]OC(F)F",
            "[*:1]OC(F)(F)F",
            "[*:1]OCCO",
            "[*:1]OCCN",
            "[*:1]OCCOC",
            "[*:1]OCC#N",
            "[*:1]N",
            "[*:1]NC",
            "[*:1]NCC",
            "[*:1]N(C)C",
            "[*:1]NC(=O)C",
            "[*:1]NC(=O)OC",
            "[*:1]S(C)(=O)=O",
            "[*:1]S(=O)(=O)N",
            "[*:1]S(=O)(=O)NC",
            "[*:1]c1ccccc1",
            "[*:1]c1ccc(F)cc1",
            "[*:1]c1ccc(Cl)cc1",
            "[*:1]c1ccc(C)cc1",
            "[*:1]c1ccc(OC)cc1",
            "[*:1]c1ccc(C#N)cc1",
            "[*:1]c1ccc(C(F)(F)F)cc1",
            "[*:1]c1ccncc1",
            "[*:1]c1ncccc1",
            "[*:1]c1cnccn1",
            "[*:1]c1ccoc1",
            "[*:1]c1ccsc1",
            "[*:1]c1nccs1",
            "[*:1]c1ncco1",
            "[*:1]C1CC1",
            "[*:1]C1CCC1",
            "[*:1]C1CCCC1",
            "[*:1]C1CCOCC1",
            "[*:1]C1CCNCC1",
            "[*:1]N1CCOCC1",
            "[*:1]N1CCCC1",
            "[*:1]N1CCN(C)CC1",
        ]
    )
)
DOUBLE_FRAGMENT_SMILES = FRAGMENT_SMILES[:14]


def generate_design_space(
    molecules: list[dict[str, Any]],
    upload_id: str,
    target_count: int = 12000,
    cluster_count: int | None = None,
) -> dict[str, Any]:
    if not molecules:
        raise ValueError("Upload compounds before generating a design space.")

    target_count = max(1000, min(int(target_count), 15000))
    designed = _enumerate_designs(molecules, target_count)
    if not designed:
        raise ValueError("No designable aromatic vectors were found in the uploaded compounds.")

    vectors = [_fingerprint_vector(item["mol"]) for item in designed]
    coords, projection_method = _project_vectors(vectors)
    clusters = _cluster_points(coords, cluster_count)

    points: list[dict[str, Any]] = []
    for index, (item, coord, assigned_cluster) in enumerate(zip(designed, coords, clusters), start=1):
        point = {
            "id": index,
            "name": f"D{index:05d}",
            "smiles": item["smiles"],
            "source_molecule_id": item["source_molecule_id"],
            "source_molecule_name": item["source_molecule_name"],
            "x": round(float(coord[0]), 5),
            "y": round(float(coord[1]), 5),
            "cluster_id": int(assigned_cluster),
            "score": _score_design(item["descriptors"]),
            "properties": item["descriptors"],
        }
        points.append(point)

    cluster_summaries = _summarize_clusters(points)

    return {
        "upload_id": upload_id,
        "requested_count": target_count,
        "generated_count": len(points),
        "projection_method": projection_method,
        "cluster_count": len(cluster_summaries),
        "clusters": cluster_summaries,
        "points": points,
        "metadata": {
            "source_compound_count": len(molecules),
            "fragment_count": len(FRAGMENT_SMILES),
            "method": (
                "Aromatic vectors from uploaded structures are enumerated with a medicinal-chemistry fragment library, "
                "deduplicated by canonical SMILES, embedded by Morgan fingerprints, projected to a t-SNE map when "
                "scikit-learn is available, and clustered in the projected space."
            ),
        },
    }


def _enumerate_designs(molecules: list[dict[str, Any]], target_count: int) -> list[dict[str, Any]]:
    tested = _canonical_smiles_set(molecules)
    seen = set(tested)
    designs: list[dict[str, Any]] = []

    for molecule in molecules:
        mol = Chem.MolFromSmiles(molecule.get("smiles", ""))
        if mol is None:
            continue
        positions = _aromatic_h_positions(mol)
        if not positions:
            continue

        _append_single_substitutions(mol, molecule, positions, seen, designs, target_count)
        if len(designs) >= target_count:
            break
        _append_double_substitutions(mol, molecule, positions, seen, designs, target_count)
        if len(designs) >= target_count:
            break

    return designs


def _append_single_substitutions(
    mol: Chem.Mol,
    source: dict[str, Any],
    positions: list[int],
    seen: set[str],
    designs: list[dict[str, Any]],
    target_count: int,
) -> None:
    for atom_idx in positions:
        for fragment_smiles in FRAGMENT_SMILES:
            product = _attach_fragment(mol, atom_idx, fragment_smiles)
            _append_design(product, source, seen, designs)
            if len(designs) >= target_count:
                return


def _append_double_substitutions(
    mol: Chem.Mol,
    source: dict[str, Any],
    positions: list[int],
    seen: set[str],
    designs: list[dict[str, Any]],
    target_count: int,
) -> None:
    for left_idx, right_idx in combinations(positions, 2):
        first_products = [
            (left_fragment, _attach_fragment(mol, left_idx, left_fragment))
            for left_fragment in DOUBLE_FRAGMENT_SMILES
        ]
        for _, first in first_products:
            if first is None:
                continue
            for right_fragment in DOUBLE_FRAGMENT_SMILES:
                product = _attach_fragment(first, right_idx, right_fragment)
                _append_design(product, source, seen, designs)
                if len(designs) >= target_count:
                    return


def _append_design(
    product: Chem.Mol | None,
    source: dict[str, Any],
    seen: set[str],
    designs: list[dict[str, Any]],
) -> None:
    if product is None:
        return
    smiles = Chem.MolToSmiles(product, canonical=True)
    if smiles in seen:
        return
    seen.add(smiles)
    descriptors = calculate_descriptors(product)
    if not _passes_design_filters(descriptors):
        return
    designs.append(
        {
            "smiles": smiles,
            "mol": product,
            "descriptors": descriptors,
            "source_molecule_id": int(source["id"]),
            "source_molecule_name": source.get("name"),
        }
    )


def _attach_fragment(mol: Chem.Mol, atom_idx: int, fragment_smiles: str) -> Chem.Mol | None:
    fragment = Chem.MolFromSmiles(fragment_smiles)
    if fragment is None:
        return None
    dummy_atoms = [atom for atom in fragment.GetAtoms() if atom.GetAtomicNum() == 0]
    if len(dummy_atoms) != 1:
        return None
    dummy = dummy_atoms[0]
    neighbors = list(dummy.GetNeighbors())
    if len(neighbors) != 1:
        return None

    base_atom_count = mol.GetNumAtoms()
    combo = Chem.CombineMols(mol, fragment)
    editable = Chem.RWMol(combo)
    dummy_idx = base_atom_count + dummy.GetIdx()
    neighbor_idx = base_atom_count + neighbors[0].GetIdx()
    editable.AddBond(atom_idx, neighbor_idx, Chem.BondType.SINGLE)
    editable.RemoveAtom(dummy_idx)
    product = editable.GetMol()
    try:
        Chem.SanitizeMol(product)
    except Exception:
        return None
    return product


def _aromatic_h_positions(mol: Chem.Mol) -> list[int]:
    return [
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if atom.GetIsAromatic() and atom.GetAtomicNum() == 6 and atom.GetTotalNumHs() > 0
    ]


def _canonical_smiles_set(molecules: list[dict[str, Any]]) -> set[str]:
    smiles_set = set()
    for molecule in molecules:
        mol = Chem.MolFromSmiles(molecule.get("smiles", ""))
        if mol is not None:
            smiles_set.add(Chem.MolToSmiles(mol, canonical=True))
    return smiles_set


def _passes_design_filters(descriptors: dict[str, Any]) -> bool:
    return (
        120 <= float(descriptors["mol_weight"]) <= 700
        and -1.5 <= float(descriptors["logp"]) <= 7.5
        and int(descriptors["hbd"]) <= 6
        and int(descriptors["hba"]) <= 12
        and float(descriptors["tpsa"]) <= 180
        and int(descriptors["rotatable_bonds"]) <= 12
    )


def _fingerprint_vector(mol: Chem.Mol) -> list[int]:
    fingerprint = FINGERPRINT_GENERATOR.GetFingerprint(mol)
    on_bits = set(fingerprint.GetOnBits())
    return [1 if bit in on_bits else 0 for bit in range(FINGERPRINT_SIZE)]


def _project_vectors(vectors: list[list[int]]) -> tuple[list[tuple[float, float]], str]:
    if len(vectors) == 1:
        return [(0.0, 0.0)], "single point"

    if len(vectors) > REAL_TSNE_LIMIT:
        return _random_projection(vectors), "fast t-SNE approximation"

    try:
        import numpy as np
        from sklearn.decomposition import PCA
        from sklearn.manifold import TSNE
        from sklearn.neighbors import NearestNeighbors

        matrix = np.asarray(vectors, dtype=float)
        landmark_count = min(len(vectors), MAX_TSNE_LANDMARKS)
        rng = np.random.default_rng(RANDOM_SEED)
        landmark_indices = np.sort(rng.choice(len(vectors), size=landmark_count, replace=False))
        landmarks = matrix[landmark_indices]

        pca_dims = min(32, landmarks.shape[0] - 1, landmarks.shape[1])
        reduced_landmarks = PCA(n_components=max(2, pca_dims), random_state=RANDOM_SEED).fit_transform(landmarks)
        perplexity = max(5, min(35, landmark_count // 3))
        tsne = TSNE(
            n_components=2,
            perplexity=perplexity,
            init="pca",
            learning_rate="auto",
            random_state=RANDOM_SEED,
        )
        landmark_coords = tsne.fit_transform(reduced_landmarks)

        if landmark_count == len(vectors):
            return [(float(x), float(y)) for x, y in landmark_coords], "t-SNE"

        neighbors = NearestNeighbors(n_neighbors=1, metric="jaccard").fit(landmarks)
        _, nearest = neighbors.kneighbors(matrix)
        coords = landmark_coords[nearest[:, 0]].astype(float)
        jitter = rng.normal(0, max(float(np.std(landmark_coords)) * 0.018, 0.01), size=coords.shape)
        coords = coords + jitter
        coords[landmark_indices] = landmark_coords
        return [(float(x), float(y)) for x, y in coords], "t-SNE landmarks"
    except Exception:
        return _random_projection(vectors), "fingerprint projection"


def _random_projection(vectors: list[list[int]]) -> list[tuple[float, float]]:
    rng = random.Random(RANDOM_SEED)
    weights_x = [rng.uniform(-1.0, 1.0) for _ in range(FINGERPRINT_SIZE)]
    weights_y = [rng.uniform(-1.0, 1.0) for _ in range(FINGERPRINT_SIZE)]
    coords = []
    for vector in vectors:
        active = max(sum(vector), 1)
        x = sum(bit * weight for bit, weight in zip(vector, weights_x)) / active
        y = sum(bit * weight for bit, weight in zip(vector, weights_y)) / active
        coords.append((x, y))
    return coords


def _pca_projection(vectors: list[list[int]]) -> list[tuple[float, float]]:
    try:
        import numpy as np
        from sklearn.decomposition import PCA

        matrix = np.asarray(vectors, dtype=float)
        coords = PCA(n_components=2, random_state=RANDOM_SEED).fit_transform(matrix)
        return [(float(x), float(y)) for x, y in coords]
    except Exception:
        return _random_projection(vectors)


def _cluster_points(
    coords: list[tuple[float, float]],
    cluster_count: int | None,
) -> list[int]:
    desired = cluster_count or max(8, min(36, int(math.sqrt(len(coords) / 12))))
    desired = max(2, min(desired, len(coords)))
    if len(coords) > REAL_TSNE_LIMIT:
        return _grid_clusters(coords, desired)
    try:
        import numpy as np
        from sklearn.cluster import MiniBatchKMeans

        matrix = np.asarray(coords, dtype=float)
        labels = MiniBatchKMeans(n_clusters=desired, random_state=RANDOM_SEED, n_init="auto", batch_size=512).fit_predict(matrix)
        return [int(label) + 1 for label in labels]
    except Exception:
        return _grid_clusters(coords, desired)


def _grid_clusters(coords: list[tuple[float, float]], cluster_count: int) -> list[int]:
    xs = [coord[0] for coord in coords]
    ys = [coord[1] for coord in coords]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    bins = max(2, int(math.sqrt(cluster_count)))
    labels = []
    for x, y in coords:
        x_bin = min(bins - 1, int((x - min_x) / ((max_x - min_x) or 1) * bins))
        y_bin = min(bins - 1, int((y - min_y) / ((max_y - min_y) or 1) * bins))
        labels.append(y_bin * bins + x_bin + 1)
    return labels


def _score_design(descriptors: dict[str, Any]) -> float:
    score = 100.0
    score -= abs(float(descriptors["mol_weight"]) - 420) / 12
    score -= abs(float(descriptors["logp"]) - 3.0) * 7
    score -= max(0, int(descriptors["hbd"]) - 3) * 7
    score -= max(0, int(descriptors["hba"]) - 8) * 4
    score -= max(0, float(descriptors["tpsa"]) - 120) / 3
    score -= max(0, int(descriptors["rotatable_bonds"]) - 8) * 5
    return round(max(1.0, min(99.0, score)), 1)


def _summarize_clusters(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for point in points:
        grouped[int(point["cluster_id"])].append(point)

    summaries = []
    for cluster_id, members in sorted(grouped.items()):
        centroid_x = sum(float(member["x"]) for member in members) / len(members)
        centroid_y = sum(float(member["y"]) for member in members) / len(members)
        representative = min(
            members,
            key=lambda member: (
                (float(member["x"]) - centroid_x) ** 2 + (float(member["y"]) - centroid_y) ** 2,
                -float(member["score"]),
            ),
        )
        summaries.append(
            {
                "cluster_id": cluster_id,
                "size": len(members),
                "centroid_x": round(centroid_x, 5),
                "centroid_y": round(centroid_y, 5),
                "avg_score": round(sum(float(member["score"]) for member in members) / len(members), 1),
                "representative": representative,
            }
        )
    return summaries
