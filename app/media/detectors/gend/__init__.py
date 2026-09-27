"""GenD, the face-swap model, trimmed to what our server needs to run it.

From https://github.com/yermandy/GenD (commit 387a422, MIT licence, copyright (c) 2025
Andy; the full text is in LICENSE beside this file). The paper: Yermakov, Cech, Matas
and Fritz, "Deepfake detection that generalizes across benchmarks", WACV 2026.

Vendored rather than imported because their code is a research repository, not a
package, and their Hugging Face loader builds the backbone with `pretrained=True` -
it would download a second 1.2 GB copy of the Perception Encoder weights only to
overwrite every one of them with the copy already in GenD's own checkpoint.

`modeling` holds the network (it needs PyTorch and timm, so nothing imports it until
the face check loads); `align` holds their face alignment, rewritten over NumPy and
Pillow so that cropping can be tested without either.
"""
