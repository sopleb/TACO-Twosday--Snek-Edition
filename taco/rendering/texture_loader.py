"""Load PNG images to OpenGL textures using QImage.

Uses PyQt6's ``QImage`` for image decoding and converts to RGBA before
uploading to an OpenGL 2D texture.
"""

from __future__ import annotations

import ctypes
import logging
from typing import Optional

import numpy as np
from OpenGL.GL import *
from PyQt6.QtGui import QImage

logger = logging.getLogger(__name__)


def load_texture(filepath: str, generate_mipmaps: bool = True) -> int:
    """Load an image from *filepath* and upload it as an OpenGL 2D texture.

    Parameters
    ----------
    filepath:
        Path to an image file (PNG, JPG, BMP, etc.) readable by ``QImage``.
    generate_mipmaps:
        If ``True`` (the default), call ``glGenerateMipmap`` after uploading
        and set min-filter to ``GL_LINEAR_MIPMAP_LINEAR``.

    Returns
    -------
    int
        The OpenGL texture name (id).  Returns ``0`` if loading fails.
    """
    image = QImage(filepath)
    if image.isNull():
        logger.error("texture_loader: failed to load image '%s'", filepath)
        return 0

    # Convert to a consistent RGBA8888 format regardless of source format.
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)

    width: int = image.width()
    height: int = image.height()

    # QImage stores rows with potential padding; constBits gives us the
    # contiguous pixel buffer.  We copy the data into a numpy array so
    # it remains valid after the QImage is garbage-collected.
    ptr = image.constBits()
    if ptr is None:
        logger.error("texture_loader: constBits() returned None for '%s'", filepath)
        return 0

    # sip wraps the pointer as a sip.voidptr; asarray gives us a view.
    raw_bytes: bytes = ptr.asstring(width * height * 4)
    pixel_data: np.ndarray = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((height, width, 4))

    # Flip vertically -- OpenGL expects the first pixel to be at the
    # bottom-left, whereas QImage stores top-left first.
    pixel_data = np.ascontiguousarray(np.flipud(pixel_data))

    # --- GL upload --------------------------------------------------------
    texture_id: int = int(glGenTextures(1))
    glBindTexture(GL_TEXTURE_2D, texture_id)

    # Texture parameters
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)

    if generate_mipmaps:
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
    else:
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

    glTexImage2D(
        GL_TEXTURE_2D,
        0,                  # mip level
        GL_RGBA,            # internal format
        width,
        height,
        0,                  # border (must be 0)
        GL_RGBA,            # format
        GL_UNSIGNED_BYTE,   # type
        pixel_data,
    )

    if generate_mipmaps:
        glGenerateMipmap(GL_TEXTURE_2D)

    glBindTexture(GL_TEXTURE_2D, 0)

    return texture_id


def delete_texture(texture_id: int) -> None:
    """Delete a previously created OpenGL texture."""
    if texture_id > 0:
        glDeleteTextures(1, [texture_id])
