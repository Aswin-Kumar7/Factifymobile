"""GenD's network: a Perception Encoder whose LayerNorms were fine-tuned, and a line.

Adapted from `src/hf/modeling_gend.py` in https://github.com/yermandy/GenD
(MIT licence, copyright (c) 2025 Andy; see LICENSE in this folder). What changed, and
why:

  - only the Perception Encoder backbone is kept - the checkpoint we ship is GenD_PE_L;
  - the backbone is built with `pretrained=False`: every one of its weights is in
    GenD's own checkpoint, so fetching timm's copy first would download 1.2 GB for
    nothing, and a server must never download at load time anyway;
  - `GenD` is a plain `nn.Module`, not a transformers `PreTrainedModel`: loading is a
    strict state-dict load from the safetensors file, so a renamed layer in a future
    timm fails loudly instead of leaving a layer at random initialisation.

The module and attribute names (`feature_extractor.backbone`, `model.linear`) are
theirs, unchanged: they are the checkpoint's keys.
"""

from __future__ import annotations

from pathlib import Path

import timm
import torch
import torch.nn.functional as F
from PIL import Image
from safetensors.torch import load_file
from timm.data.config import resolve_model_data_config
from timm.data.transforms_factory import create_transform
from timm.models.eva import Eva
from torch import nn

# Their training labels: every "real" source is 0, every manipulation is 1 or more,
# folded to 1 for the two-way head (src/dataset/dataset.py; app/run.py reads probs[1]).
FAKE = 1

# The Perception Encoder was trained at 336 px; GenD fine-tuned and evaluated it at
# 224 px, with the position embeddings resampled (`dynamic_img_size`).
INPUT_SIZE = 224


class LinearProbe(nn.Module):
    """Their head. `LinearNorm` = unit-length features before the line: GenD's
    "hyperspherical feature manifold"."""

    def __init__(self, input_dim: int, num_classes: int, normalize_inputs: bool = False) -> None:
        super().__init__()
        self.linear = nn.Linear(input_dim, num_classes)
        self.normalize_inputs = normalize_inputs

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.normalize_inputs:
            x = F.normalize(x, p=2, dim=1)
        return self.linear(x)  # type: ignore[no-any-return]


class PerceptionEncoder(nn.Module):
    """The timm Perception Encoder with its classification head removed."""

    def __init__(self, model_name: str = "vit_pe_core_large_patch14_336") -> None:
        super().__init__()
        backbone = timm.create_model(model_name, pretrained=False, dynamic_img_size=True)
        if not isinstance(backbone, Eva):
            raise TypeError(f"{model_name} is not a Perception Encoder: {type(backbone)}")
        self.backbone: Eva = backbone

        # The backbone's own normalisation and resize (bicubic, mean and std 0.5), at
        # the size GenD used.
        data_config = resolve_model_data_config(self.backbone)  # type: ignore[no-untyped-call]
        data_config["input_size"] = (3, INPUT_SIZE, INPUT_SIZE)
        self._preprocess = create_transform(**data_config, is_training=False)

        self.backbone.head = nn.Identity()
        self.features_dim: int = int(self.backbone.num_features)

    def preprocess(self, image: Image.Image) -> torch.Tensor:
        return self._preprocess(image)  # type: ignore[no-any-return]

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.backbone(inputs)  # type: ignore[no-any-return]


class GenD(nn.Module):
    def __init__(self, *, backbone: str, head: str) -> None:
        super().__init__()
        if "vit_pe" not in backbone.lower():
            raise ValueError(f"only the Perception Encoder GenD is vendored, not {backbone}")
        self.feature_extractor = PerceptionEncoder(backbone)
        match head:
            case "linear":
                self.model = LinearProbe(self.feature_extractor.features_dim, 2)
            case "LinearNorm":
                self.model = LinearProbe(self.feature_extractor.features_dim, 2, True)
            case _:
                raise ValueError(f"Unknown head: {head}")

    def preprocess(self, image: Image.Image) -> torch.Tensor:
        return self.feature_extractor.preprocess(image)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.model(self.feature_extractor(inputs))  # type: ignore[no-any-return]


def load(weights: Path, *, backbone: str, head: str) -> GenD:
    """The network with the checkpoint's weights, every key accounted for, in eval mode."""
    model = GenD(backbone=backbone, head=head)
    model.load_state_dict(load_file(str(weights), device="cpu"), strict=True)
    return model.eval()
