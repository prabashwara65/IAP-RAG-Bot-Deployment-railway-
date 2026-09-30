"""Authenticator-app codes (TOTP) and the setup QR image."""

from __future__ import annotations

import io

import pyotp
import segno

ISSUER = "OIAP"


def new_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(*, secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def qr_svg(data: str) -> str:
    buffer = io.BytesIO()
    segno.make(data, error="m").save(
        buffer,
        kind="svg",
        xmldecl=False,
        svgns=True,
        scale=4,
    )
    return buffer.getvalue().decode("utf-8")


def totp_matches(secret: str, code: str) -> bool:
    cleaned = code.strip().replace(" ", "")
    if len(cleaned) != 6 or not cleaned.isdigit():
        return False
    return bool(pyotp.TOTP(secret).verify(cleaned, valid_window=1))
