from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator

from app.storage.database import update_cluster_ids


FINGERPRINT_GENERATOR = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


def cluster_molecules(molecules: list[dict[str, Any]], threshold: float = 0.55) -> list[dict[str, Any]]:
    valid: list[tuple[int, Chem.Mol, Any]] = []
    for molecule in molecules:
        mol = Chem.MolFromSmiles(molecule["smiles"])
        if mol is not None:
            fp = FINGERPRINT_GENERATOR.GetFingerprint(mol)
            valid.append((molecule["id"], mol, fp))

    graph: dict[int, set[int]] = defaultdict(set)
    for i, (left_id, _, left_fp) in enumerate(valid):
        graph[left_id].add(left_id)
        for right_id, _, right_fp in valid[i + 1 :]:
            similarity = DataStructs.TanimotoSimilarity(left_fp, right_fp)
            if similarity >= threshold:
                graph[left_id].add(right_id)
                graph[right_id].add(left_id)

    assignments: dict[int, int] = {}
    cluster_id = 1
    for molecule_id, _, _ in valid:
        if molecule_id in assignments:
            continue
        queue = deque([molecule_id])
        assignments[molecule_id] = cluster_id
        while queue:
            current = queue.popleft()
            for neighbor in graph[current]:
                if neighbor not in assignments:
                    assignments[neighbor] = cluster_id
                    queue.append(neighbor)
        cluster_id += 1

    update_cluster_ids(assignments)
    return _summarize_clusters(molecules, assignments)


def _summarize_clusters(
    molecules: list[dict[str, Any]],
    assignments: dict[int, int],
) -> list[dict[str, Any]]:
    by_cluster: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for molecule in molecules:
        cluster_id = assignments.get(molecule["id"], molecule.get("cluster_id"))
        if cluster_id is not None:
            molecule["cluster_id"] = cluster_id
            by_cluster[int(cluster_id)].append(molecule)

    summaries = []
    for cluster_id, members in sorted(by_cluster.items()):
        representative = members[0]
        summaries.append(
            {
                "cluster_id": cluster_id,
                "size": len(members),
                "representative_id": representative["id"],
                "representative_smiles": representative["smiles"],
                "avg_mol_weight": _average(member.get("mol_weight") for member in members),
                "avg_logp": _average(member.get("logp") for member in members),
            }
        )
    return summaries


def _average(values: Any) -> float | None:
    usable = [float(value) for value in values if value is not None]
    if not usable:
        return None
    return round(sum(usable) / len(usable), 3)
