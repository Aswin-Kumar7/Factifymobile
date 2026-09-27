# Adapted from two Apache-2.0 projects; the licence text is LICENSE beside this file.
#
#   Dual Data Alignment (Chen, Xi, Yan et al., NeurIPS 2025)
#     https://github.com/roy-ch/Dual-Data-Alignment, commit 8b9c06e (2026-05-24):
#     Inference/models/dinov2_models.py, dinov2_models_lora.py, lora.py, inference.py
#   DINOv2, Copyright (c) Meta Platforms, Inc. and affiliates
#     https://github.com/facebookresearch/dinov2: dinov2/models/vision_transformer.py,
#     dinov2/layers/{attention,block,mlp,patch_embed,layer_scale}.py, hub/backbones.py
#
# Changes from those sources: inference only, for the one configuration DDA ships
# (`dinov2_vitl14`: no registers, no chunked blocks, MLP feed-forward), so dropout,
# drop-path, masking, xFormers and weight initialisation are gone; attention always
# goes through PyTorch's fused kernel; and the LoRA adapters are added into the
# weights of the layers they adapt when the checkpoint is read, instead of running
# beside them on every call. Module names follow DINOv2's so the saved weights load
# under their own names.
"""DDA's detector: DINOv2 ViT-L/14 reading a picture, one linear layer judging it.

The DINOv2 backbone was trained by Meta to describe pictures, not to spot generators.
DDA adapted it with LoRA - small low-rank corrections to every attention and
feed-forward layer, rank 8, alpha 1 - and a single linear layer that turns DINOv2's
summary of the picture (the normalised class token) into one logit. After training a
LoRA correction is just a fixed matrix, so it is folded into the layer it corrects:
the same function, without two extra multiplications beside each of 96 layers, and
with no LoRA code to carry.
"""

from __future__ import annotations

from pathlib import Path

import torch
from torch import Tensor, nn
from torch.nn import functional

# `dinov2_vitl14` as torch.hub builds it (dinov2/hub/backbones.py, vision_transformer.py).
WIDTH = 1024
DEPTH = 24
HEADS = 16
PATCH = 14
# Its position table was learned at 518 px: 37 x 37 patches, plus the class token.
TRAINED_GRID = 37
# DINOv2's historical nudge when it resizes that table (facebookresearch/dino#8). The
# hub model keeps it for compatibility with how it was trained, so we keep it too.
INTERPOLATE_OFFSET = 0.1
NORM_EPS = 1e-6

# DDA's adapters (Training/train.sh, Inference/inference.py). The rank is read from
# the saved matrices; alpha is not saved, so it is DDA's published value.
LORA_ALPHA = 1.0

# The keys DDA's checkpoint stores the network under.
_BACKBONE = "base_model.model."
_HEAD = "base_model.fc."
# DINOv2's masked-image pretraining token: part of the saved backbone, never used when
# a whole picture is read.
_UNUSED = frozenset({"base_model.model.mask_token"})


class _Attention(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.qkv = nn.Linear(WIDTH, WIDTH * 3)
        self.proj = nn.Linear(WIDTH, WIDTH)

    def forward(self, x: Tensor) -> Tensor:
        batch, tokens, width = x.shape
        qkv = self.qkv(x).reshape(batch, tokens, 3, HEADS, width // HEADS)
        q, k, v = (part.transpose(1, 2) for part in qkv.unbind(2))
        x = functional.scaled_dot_product_attention(q, k, v)
        out: Tensor = self.proj(x.transpose(1, 2).reshape(batch, tokens, width))
        return out


class _Mlp(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.fc1 = nn.Linear(WIDTH, WIDTH * 4)
        self.act = nn.GELU()
        self.fc2 = nn.Linear(WIDTH * 4, WIDTH)

    def forward(self, x: Tensor) -> Tensor:
        out: Tensor = self.fc2(self.act(self.fc1(x)))
        return out


class _LayerScale(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.gamma = nn.Parameter(torch.ones(WIDTH))

    def forward(self, x: Tensor) -> Tensor:
        return x * self.gamma


class _Block(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.norm1 = nn.LayerNorm(WIDTH, eps=NORM_EPS)
        self.attn = _Attention()
        self.ls1 = _LayerScale()
        self.norm2 = nn.LayerNorm(WIDTH, eps=NORM_EPS)
        self.mlp = _Mlp()
        self.ls2 = _LayerScale()

    def forward(self, x: Tensor) -> Tensor:
        x = x + self.ls1(self.attn(self.norm1(x)))
        out: Tensor = x + self.ls2(self.mlp(self.norm2(x)))
        return out


class _PatchEmbed(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.proj = nn.Conv2d(3, WIDTH, kernel_size=PATCH, stride=PATCH)

    def forward(self, x: Tensor) -> Tensor:
        patches: Tensor = self.proj(x)
        return patches.flatten(2).transpose(1, 2)


class DinoV2Large(nn.Module):
    """DINOv2 ViT-L/14, returning only what DDA reads: the normalised class token."""

    def __init__(self) -> None:
        super().__init__()
        self.patch_embed = _PatchEmbed()
        self.cls_token = nn.Parameter(torch.zeros(1, 1, WIDTH))
        self.pos_embed = nn.Parameter(torch.zeros(1, TRAINED_GRID**2 + 1, WIDTH))
        self.blocks = nn.ModuleList(_Block() for _ in range(DEPTH))
        self.norm = nn.LayerNorm(WIDTH, eps=NORM_EPS)

    def positions(self, height: int, width: int) -> Tensor:
        """The position table resized to this picture's grid of patches.

        DINOv2's `interpolate_pos_encoding`: bicubic, no antialiasing, scaled by
        (grid + 0.1) / 37. The offset shifts where each sample is read from, so
        leaving it out would feed the network positions it was never trained on.
        """
        rows, columns = height // PATCH, width // PATCH
        if rows == columns == TRAINED_GRID:
            return self.pos_embed
        table = self.pos_embed.float()
        grid = table[:, 1:].reshape(1, TRAINED_GRID, TRAINED_GRID, WIDTH).permute(0, 3, 1, 2)
        grid = functional.interpolate(
            grid,
            scale_factor=(
                (rows + INTERPOLATE_OFFSET) / TRAINED_GRID,
                (columns + INTERPOLATE_OFFSET) / TRAINED_GRID,
            ),
            mode="bicubic",
            antialias=False,
        )
        if tuple(grid.shape[-2:]) != (rows, columns):
            raise ValueError(f"position grid {tuple(grid.shape[-2:])} for {rows}x{columns}")
        grid = grid.permute(0, 2, 3, 1).reshape(1, rows * columns, WIDTH)
        return torch.cat((table[:, :1], grid), dim=1).to(self.pos_embed.dtype)

    def forward(self, x: Tensor) -> Tensor:
        _, _, height, width = x.shape
        tokens = self.patch_embed(x)
        tokens = torch.cat((self.cls_token.expand(tokens.shape[0], -1, -1), tokens), dim=1)
        tokens = tokens + self.positions(height, width)
        for block in self.blocks:
            tokens = block(tokens)
        normalised: Tensor = self.norm(tokens)
        return normalised[:, 0]


class DdaNetwork(nn.Module):
    """A batch of normalised 336 x 336 pictures in, one logit per picture out."""

    def __init__(self) -> None:
        super().__init__()
        self.backbone = DinoV2Large()
        self.fc = nn.Linear(WIDTH, 1)

    def forward(self, x: Tensor) -> Tensor:
        logits: Tensor = self.fc(self.backbone(x))
        return logits


def load(path: Path) -> DdaNetwork:
    """The network from DDA's released checkpoint, ready for inference.

    The file is memory-mapped rather than read, and the network is first built with
    no storage at all (the meta device), so loading costs about one copy of the
    weights (1.2 GB) instead of three: file, random initialisation, loaded copy.
    `weights_only` keeps a tampered checkpoint from running code when unpickled.
    """
    checkpoint = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
    state = merged(checkpoint["model"])
    del checkpoint
    with torch.device("meta"):
        network = DdaNetwork()
    network.load_state_dict(state, strict=True, assign=True)
    return network.eval().requires_grad_(False)


def merged(saved: dict[str, Tensor]) -> dict[str, Tensor]:
    """DDA's state dict with each LoRA pair folded into its layer, under our names.

    DDA's LoRA layer returns `original(x) + (alpha / rank) * x A^T B^T`, which is the
    original layer with weight `W + (alpha / rank) * B A` - so that is the weight
    kept. Every tensor is copied out of the memory-mapped file, so nothing in the
    loaded network still points into it and the mapping goes when loading ends.
    """
    state: dict[str, Tensor] = {}
    adapters = {key.removesuffix(".lora.lora_A") for key in saved if key.endswith(".lora.lora_A")}
    folded = 0
    for key, value in saved.items():
        if key in _UNUSED or ".lora.lora_" in key:
            continue
        if key.startswith(_BACKBONE):
            name = "backbone." + key.removeprefix(_BACKBONE)
        elif key.startswith(_HEAD):
            name = "fc." + key.removeprefix(_HEAD)
        else:
            raise ValueError(f"unexpected key in the DDA checkpoint: {key}")
        layer, marker, parameter = key.partition(".original_layer.")
        if marker:
            name = name.replace(".original_layer.", ".")
            if parameter == "weight" and layer in adapters:
                down = saved[f"{layer}.lora.lora_A"].float()
                up = saved[f"{layer}.lora.lora_B"].float()
                state[name] = value.float() + (LORA_ALPHA / down.shape[0]) * (up @ down)
                folded += 1
                continue
        state[name] = value.float().clone()
    if folded != len(adapters):
        raise ValueError(f"folded {folded} of {len(adapters)} LoRA adapters")
    return state
