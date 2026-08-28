"""QR-code helper: URL -> base64 PNG data URI."""

from __future__ import annotations

import base64
import io


def make_qr_data_uri(url: str, box_size: int = 8, border: int = 2) -> str:
    """Return a `data:image/png;base64,...` string for `url`.

    Degrades to an empty string if `qrcode`/`Pillow` aren't installed so the
    endpoint still works (the frontend just falls back to showing the link).
    """
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
    except Exception:  # noqa: BLE001
        return ""

    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=box_size, border=border)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"
