"""Make the pictures the media tests read: signed with content credentials, or not.

    uv run python scripts/make_media_fixtures.py

Writes to tests/fixtures/media/. The credentials are signed by a throwaway test
authority made here, so they read but do not validate against any trust list - which
is exactly what a forged or self-signed credential looks like, and what the reader
must report as untrusted.

  - ai_declared.jpg  - a C2PA manifest whose action says the picture was made by a
    trained model (the IPTC "trainedAlgorithmicMedia" digital source type), the way
    OpenAI, Adobe Firefly and Google sign theirs;
  - camera.jpg       - a manifest saying a camera captured it;
  - xmp_ai.jpg       - no manifest, only IPTC metadata declaring an AI source;
  - plain.jpg        - nothing at all, the ordinary case.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import c2pa
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "media"

AI_SOURCE = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
CAMERA_SOURCE = "http://cv.iptc.org/newscodes/digitalsourcetype/digitalCapture"


def _jpeg(colour: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), colour).save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


def _authority() -> tuple[bytes, bytes]:
    """A test CA and a signing certificate under it: (key PEM, chain PEM)."""
    now = datetime.now(UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Factify Test CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )  # fmt: skip

    key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, "Factify Test Signer"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Factify Test"),
                ]
            )
        )
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )  # fmt: skip

    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    chain = leaf.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(
        serialization.Encoding.PEM
    )
    return key_pem, chain


def _signed(image: bytes, *, source: str, agent: str) -> bytes:
    key_pem, chain = _authority()
    signer = c2pa.Signer.from_info(
        c2pa.C2paSignerInfo(alg=b"es256", sign_cert=chain, private_key=key_pem, ta_url=None)
    )
    manifest = {
        "claim_generator_info": [{"name": agent, "version": "1.0"}],
        "title": "fixture.jpg",
        "format": "image/jpeg",
        "assertions": [
            {
                "label": "c2pa.actions",
                "data": {
                    "actions": [
                        {
                            "action": "c2pa.created",
                            "digitalSourceType": source,
                            "softwareAgent": {"name": agent},
                        }
                    ]
                },
            }
        ],
    }
    with c2pa.Builder(json.dumps(manifest)) as builder:
        out = io.BytesIO()
        builder.sign(signer, "image/jpeg", io.BytesIO(image), out)
        return out.getvalue()


def _with_xmp(image: bytes, source: str) -> bytes:
    """A JPEG carrying an XMP packet with the IPTC digital source type, nothing else."""
    xmp = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" '
        f'Iptc4xmpExt:DigitalSourceType="{source}"/></rdf:RDF></x:xmpmeta>'
    ).encode()
    buffer = io.BytesIO()
    Image.open(io.BytesIO(image)).save(buffer, "JPEG", quality=90, xmp=xmp)
    return buffer.getvalue()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ai_declared.jpg").write_bytes(
        _signed(_jpeg((120, 80, 200)), source=AI_SOURCE, agent="Test Image Model")
    )
    (OUT / "camera.jpg").write_bytes(
        _signed(_jpeg((40, 140, 90)), source=CAMERA_SOURCE, agent="Test Camera")
    )
    (OUT / "xmp_ai.jpg").write_bytes(_with_xmp(_jpeg((200, 120, 40)), AI_SOURCE))
    (OUT / "plain.jpg").write_bytes(_jpeg((90, 90, 90)))
    for path in sorted(OUT.glob("*.jpg")):
        print(path.name, path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
