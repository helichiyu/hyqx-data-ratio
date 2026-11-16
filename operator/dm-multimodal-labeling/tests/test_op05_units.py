"""OP-05 纯函数单测：树、标签打分、阈值路由、融合、OCR。"""

from __future__ import annotations

import numpy as np

from op05_env import CORE, SAMPLES


class _FakeEmbedder:
    model_version = "fake-embedding-v1"

    def __init__(self, vector):
        self.vector = np.asarray(vector, dtype=np.float32)
        self.dimension = len(self.vector)

    def encode_document(self, text):
        return self.vector


class _FakeTree:
    tree_version = "tree-test"

    def __init__(self):
        self.labels = [
            {"path": ["A"], "text": "A"},
            {"path": ["B"], "text": "B"},
            {"path": ["C"], "text": "C"},
        ]
        self.label_texts = ["A", "B", "C"]
        self.paths = {("A",), ("B",), ("C",)}

    def is_valid(self, path):
        return tuple(path) in self.paths


def test_tree_snapshot_leaf_paths():
    cfg = CORE.load_config()
    tree = CORE.tree.LabelTree(cfg)
    assert tree.tree_version == "taxonomy-1013-pending"
    assert len(tree.labels) == 279
    assert all(len(item["path"]) == 3 for item in tree.labels)
    assert all(tree.is_valid(item["path"]) for item in tree.labels)


def test_label_high_confidence():
    cfg = CORE.load_config()
    tree = _FakeTree()
    matrix = np.eye(3, dtype=np.float32)
    embedder = _FakeEmbedder([1.0, 0.0, 0.0])
    result = CORE.labeler.label_vector(
        embedder, matrix, tree, embedder.vector, cfg, evidence={"source": "text"}
    )
    assert result["unclassified"] is False
    assert result["labels"][0]["path"] == ["A"]
    assert result["labels"][0]["confidence"] >= 0.25
    assert len(result["topK"]) == 3


def test_label_low_similarity_and_margin():
    cfg = CORE.load_config()
    tree = _FakeTree()
    matrix = np.eye(3, dtype=np.float32)
    embedder = _FakeEmbedder([0.1, 0.1, 0.1])
    result = CORE.labeler.label_vector(
        embedder, matrix, tree, embedder.vector, cfg, evidence={}
    )
    assert result["unclassified"] is True
    assert result["reasonCode"] in {
        "UNCLASSIFIED_LOW_SIMILARITY",
        "UNCLASSIFIED_LOW_CONFIDENCE",
        "UNCLASSIFIED_SMALL_MARGIN",
    }


def test_fuse_vectors_normalized():
    left = np.array([1.0, 0.0], dtype=np.float32)
    right = np.array([0.0, 1.0], dtype=np.float32)
    fused = CORE.labeler.fuse_vectors([left, right], [0.5, 0.5])
    assert abs(float(np.linalg.norm(fused)) - 1.0) < 1e-6
    assert abs(float(fused[0]) - 0.7071) < 1e-3


def test_ocr_on_sample_image():
    result = CORE.ocr.ocr_image(SAMPLES / "image" / "530384988814704640.jpg")
    assert result["chars"] > 10
    assert result["items"]
    assert result["items"][0]["score"] > 0
