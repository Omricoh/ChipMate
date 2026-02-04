"""QR code generation service.

Generates QR code PNG images for game join URLs using the qrcode library.
"""

import io
import logging

import qrcode
from qrcode.image.pil import PilImage

logger = logging.getLogger("chipmate.services.qr")


def generate_qr_code(game_code: str, base_url: str) -> bytes:
    """Generate a QR code PNG for the game join URL.

    Args:
        game_code: The 6-character game code.
        base_url: Optional application base URL. If empty, use a relative path.

    Returns:
        PNG image data as bytes.
    """
    join_url = f"{base_url.rstrip('/')}/join/{game_code}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(join_url)
    qr.make(fit=True)

    img: PilImage = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    logger.info("Generated QR code for game code %s -> %s", game_code, join_url)
    return buffer.getvalue()
