"""The network behind the DDA detector, vendored so the server never fetches code.

DDA's own code builds its backbone with `torch.hub.load("facebookresearch/dinov2")`,
which downloads Meta's repository at run time and then 1.2 GB of pretrained weights
that the DDA checkpoint overwrites anyway. The few classes that make up the network
live here instead, so loading needs nothing but the checkpoint file.

Apache-2.0, like both sources (LICENSE in this folder); what came from where, and
what was changed, is at the top of `network.py`. Importing this package imports
PyTorch, so `app.media.detectors.dda` imports it only when the model is loaded.
"""

from app.media.detectors.dda_model.network import DdaNetwork, load

__all__ = ["DdaNetwork", "load"]
