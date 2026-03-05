"""Font texture atlas for GPU text rendering.

Renders ASCII printable characters (32-126) into a single GL texture
and stores per-character UV coordinates and metrics for quad generation.
"""

from __future__ import annotations

import logging
import numpy as np

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QFont, QFontMetrics, QImage, QPainter, QColor
from OpenGL.GL import *

logger = logging.getLogger(__name__)


class GlyphMetrics:
    """UV coords and pixel dimensions for a single character."""
    __slots__ = ('u0', 'v0', 'u1', 'v1', 'advance_px', 'height_px', 'bearing_y')

    def __init__(self, u0: float, v0: float, u1: float, v1: float,
                 advance_px: int, height_px: int, bearing_y: int):
        self.u0 = u0
        self.v0 = v0
        self.u1 = u1
        self.v1 = v1
        self.advance_px = advance_px
        self.height_px = height_px
        self.bearing_y = bearing_y


class FontAtlas:
    """Rasterizes a font into a single-channel GL texture atlas.

    Usage::

        atlas = FontAtlas(QFont("Verdana", 10))
        atlas.upload()  # call with GL context active
        # Later: atlas.texture_id, atlas.glyphs[char], atlas.line_height
    """

    def __init__(self, font: QFont, bold: bool = False, scale: float = 1.0):
        self._font = QFont(font)
        if bold:
            self._font.setBold(True)
        self._fm = QFontMetrics(self._font)
        self.line_height: int = self._fm.height()
        self.ascent: int = self._fm.ascent()
        self.glyphs: dict[str, GlyphMetrics] = {}
        self.texture_id: int = 0
        self._atlas_w: int = 0   # logical width
        self._atlas_h: int = 0   # logical height
        self._phys_w: int = 0    # physical width for GL upload
        self._phys_h: int = 0    # physical height for GL upload
        self._pixel_data: np.ndarray | None = None
        self._scale = max(scale, 1.0)
        self._generate()

    def _generate(self):
        """Rasterize ASCII 32-126 into a packed atlas image."""
        chars = [chr(c) for c in range(32, 127)]
        fm = self._fm

        # Measure all glyphs to determine atlas size
        glyph_sizes: list[tuple[str, int, int]] = []
        pad = 2  # padding between glyphs
        for ch in chars:
            w = fm.horizontalAdvance(ch) + pad
            h = fm.height() + pad
            glyph_sizes.append((ch, max(w, 1), max(h, 1)))

        # Pack into rows (simple shelf packing)
        total_area = sum(w * h for _, w, h in glyph_sizes)
        # Start with a reasonable atlas size
        atlas_w = 256
        while atlas_w * atlas_w < total_area * 2:
            atlas_w *= 2
        atlas_w = min(atlas_w, 1024)

        row_h = fm.height() + pad
        rows_needed = 1
        x_cursor = 0
        for _, gw, _ in glyph_sizes:
            if x_cursor + gw > atlas_w:
                rows_needed += 1
                x_cursor = 0
            x_cursor += gw
        atlas_h = rows_needed * row_h
        # Round up to power of 2
        atlas_h_pow2 = 64
        while atlas_h_pow2 < atlas_h:
            atlas_h_pow2 *= 2
        atlas_h = min(atlas_h_pow2, 1024)

        self._atlas_w = atlas_w
        self._atlas_h = atlas_h
        scale = self._scale
        self._phys_w = int(atlas_w * scale)
        self._phys_h = int(atlas_h * scale)

        # Render glyphs to QImage at higher physical resolution
        image = QImage(self._phys_w, self._phys_h, QImage.Format.Format_Grayscale8)
        image.setDevicePixelRatio(scale)
        image.fill(QColor(0, 0, 0))

        painter = QPainter(image)
        painter.setFont(self._font)
        painter.setPen(QColor(255, 255, 255))
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        x_cursor = 0
        y_cursor = 0
        for ch, gw, gh in glyph_sizes:
            if x_cursor + gw > atlas_w:
                x_cursor = 0
                y_cursor += row_h
            # Draw character
            painter.drawText(x_cursor, y_cursor + fm.ascent(), ch)
            # Store UV coordinates (normalized)
            u0 = x_cursor / atlas_w
            v0 = y_cursor / atlas_h
            u1 = (x_cursor + gw - pad) / atlas_w
            v1 = (y_cursor + row_h - pad) / atlas_h
            self.glyphs[ch] = GlyphMetrics(
                u0, v0, u1, v1,
                advance_px=fm.horizontalAdvance(ch),
                height_px=fm.height(),
                bearing_y=fm.ascent(),
            )
            x_cursor += gw

        painter.end()

        # Extract physical pixel data as numpy array
        ptr = image.constBits()
        if ptr is not None:
            raw = ptr.asstring(self._phys_w * self._phys_h)
            self._pixel_data = np.frombuffer(raw, dtype=np.uint8).reshape(
                (self._phys_h, self._phys_w))
        else:
            self._pixel_data = np.zeros((self._phys_h, self._phys_w), dtype=np.uint8)

    def upload(self):
        """Upload the atlas texture to OpenGL. Must be called with active GL context."""
        if self._pixel_data is None:
            return
        if self.texture_id:
            glDeleteTextures(1, [self.texture_id])

        self.texture_id = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, self.texture_id)

        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_R8,
            self._phys_w, self._phys_h, 0,
            GL_RED, GL_UNSIGNED_BYTE,
            self._pixel_data
        )
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glBindTexture(GL_TEXTURE_2D, 0)

        # Free CPU-side data after upload
        self._pixel_data = None

    def measure_text(self, text: str) -> tuple[int, int]:
        """Return (width, height) in pixels for the given text string."""
        w = 0
        for ch in text:
            g = self.glyphs.get(ch)
            if g:
                w += g.advance_px
        return (w, self.line_height)

    def dispose(self):
        if self.texture_id:
            try:
                glDeleteTextures(1, [self.texture_id])
            except Exception:
                pass
            self.texture_id = 0
