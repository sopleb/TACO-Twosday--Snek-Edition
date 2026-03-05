"""Batched GPU text renderer using font texture atlas.

Collects text and rectangle draw commands, then flushes everything
in minimal draw calls (one for rects, one per atlas for text).
"""

from __future__ import annotations

import ctypes
import logging
import numpy as np

from OpenGL.GL import *
from taco.rendering.shader import Shader
from taco.rendering.font_atlas import FontAtlas

logger = logging.getLogger(__name__)

# Vertex format: x, y, u, v, r, g, b, a  (8 floats per vertex)
VERTEX_FLOATS = 8
FLOATS_PER_QUAD = VERTEX_FLOATS * 6  # 2 triangles = 6 vertices


class TextRenderer:
    """Batched 2D text and rectangle renderer.

    Usage each frame::

        renderer.begin_frame(width, height)
        renderer.add_rect(x, y, w, h, fill, border)
        renderer.add_text(x, y, text, atlas, color)
        renderer.flush()
    """

    def __init__(self, shader: Shader):
        self._shader = shader
        self._vao: int = 0
        self._vbo: int = 0
        self._vbo_capacity: int = 0  # in floats
        self._screen_w: int = 1
        self._screen_h: int = 1

        # Batched vertex data: list of (atlas_texture_id, float_array)
        # texture_id=0 means untextured (colored rect)
        self._batches: dict[int, list[float]] = {}

    def init_gl(self):
        """Create VAO/VBO. Must be called with active GL context."""
        self._vao = glGenVertexArrays(1)
        glBindVertexArray(self._vao)

        self._vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)

        stride = VERTEX_FLOATS * 4  # bytes
        # position (x, y)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        # texcoord (u, v)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(8))
        glEnableVertexAttribArray(1)
        # color (r, g, b, a)
        glVertexAttribPointer(2, 4, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(16))
        glEnableVertexAttribArray(2)

        glBindVertexArray(0)

    def begin_frame(self, screen_w: int, screen_h: int):
        """Reset batches and set screen dimensions for orthographic projection."""
        self._screen_w = max(screen_w, 1)
        self._screen_h = max(screen_h, 1)
        self._batches.clear()

    def add_text(self, x: float, y: float, text: str, atlas: FontAtlas,
                 r: float = 0.78, g: float = 0.78, b: float = 0.78, a: float = 0.9):
        """Append textured quads for each character in *text*."""
        if not text or not atlas.texture_id:
            return
        tex_id = atlas.texture_id
        batch = self._batches.setdefault(tex_id, [])
        cx = x
        for ch in text:
            glyph = atlas.glyphs.get(ch)
            if glyph is None:
                glyph = atlas.glyphs.get('?')
                if glyph is None:
                    continue
            # Quad corners in screen pixels
            x0 = cx
            y0 = y
            x1 = cx + glyph.advance_px
            y1 = y + glyph.height_px
            u0, v0, u1, v1 = glyph.u0, glyph.v0, glyph.u1, glyph.v1
            # Two triangles (6 vertices)
            batch.extend([
                x0, y0, u0, v0, r, g, b, a,
                x1, y0, u1, v0, r, g, b, a,
                x1, y1, u1, v1, r, g, b, a,
                x0, y0, u0, v0, r, g, b, a,
                x1, y1, u1, v1, r, g, b, a,
                x0, y1, u0, v1, r, g, b, a,
            ])
            cx += glyph.advance_px

    def add_rect(self, x: float, y: float, w: float, h: float,
                 fr: float = 0.0, fg: float = 0.0, fb: float = 0.0, fa: float = 0.7,
                 br: float = -1.0, bg: float = 0.0, bb: float = 0.0, ba: float = 0.0,
                 border_width: float = 1.0):
        """Append a filled rectangle, optionally with a 1px border.

        Fill color: (fr, fg, fb, fa).  Border color: (br, bg, bb, ba).
        Pass br < 0 to skip the border.
        """
        batch = self._batches.setdefault(0, [])  # texture_id=0 = untextured
        # Fill quad
        x0, y0, x1, y1 = x, y, x + w, y + h
        batch.extend([
            x0, y0, 0, 0, fr, fg, fb, fa,
            x1, y0, 0, 0, fr, fg, fb, fa,
            x1, y1, 0, 0, fr, fg, fb, fa,
            x0, y0, 0, 0, fr, fg, fb, fa,
            x1, y1, 0, 0, fr, fg, fb, fa,
            x0, y1, 0, 0, fr, fg, fb, fa,
        ])
        # Border (4 thin edge quads)
        if br >= 0:
            bw = border_width
            edges = [
                (x0, y0, x1, y0 + bw),       # top
                (x0, y1 - bw, x1, y1),       # bottom
                (x0, y0, x0 + bw, y1),       # left
                (x1 - bw, y0, x1, y1),       # right
            ]
            for ex0, ey0, ex1, ey1 in edges:
                batch.extend([
                    ex0, ey0, 0, 0, br, bg, bb, ba,
                    ex1, ey0, 0, 0, br, bg, bb, ba,
                    ex1, ey1, 0, 0, br, bg, bb, ba,
                    ex0, ey0, 0, 0, br, bg, bb, ba,
                    ex1, ey1, 0, 0, br, bg, bb, ba,
                    ex0, ey1, 0, 0, br, bg, bb, ba,
                ])

    def flush(self):
        """Upload all batched quads and draw. Call once per frame after all add_* calls."""
        if not self._batches:
            return

        # Build orthographic projection: screen pixels -> clip space
        # top-left = (0,0), bottom-right = (w, h)
        w = float(self._screen_w)
        h = float(self._screen_h)
        ortho = np.array([
            [2.0 / w,  0.0,      0.0, -1.0],
            [0.0,     -2.0 / h,  0.0,  1.0],
            [0.0,      0.0,     -1.0,  0.0],
            [0.0,      0.0,      0.0,  1.0],
        ], dtype=np.float32)

        self._shader.bind()
        self._shader.set_uniform_mat4("projection", ortho)

        glBindVertexArray(self._vao)

        # Disable depth test for 2D overlay
        glDisable(GL_DEPTH_TEST)

        # Draw untextured rects first (batch key = 0)
        rect_data = self._batches.pop(0, None)
        if rect_data:
            self._shader.set_uniform_1i("useTexture", 0)
            self._upload_and_draw(rect_data)

        # Draw textured batches (one per atlas)
        for tex_id, text_data in self._batches.items():
            if not text_data:
                continue
            self._shader.set_uniform_1i("useTexture", 1)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, tex_id)
            self._shader.set_uniform_1i("tex", 0)
            self._upload_and_draw(text_data)

        glEnable(GL_DEPTH_TEST)
        glBindVertexArray(0)
        Shader.unbind()

    def _upload_and_draw(self, data: list[float]):
        """Upload vertex data to VBO and issue draw call."""
        arr = np.array(data, dtype=np.float32)
        nbytes = arr.nbytes

        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        if nbytes > self._vbo_capacity * 4:
            # Grow VBO (with headroom)
            new_cap = max(len(data), self._vbo_capacity * 2, 4096)
            glBufferData(GL_ARRAY_BUFFER, new_cap * 4, None, GL_DYNAMIC_DRAW)
            self._vbo_capacity = new_cap
        glBufferSubData(GL_ARRAY_BUFFER, 0, nbytes, arr)

        vertex_count = len(data) // VERTEX_FLOATS
        glDrawArrays(GL_TRIANGLES, 0, vertex_count)

    def dispose(self):
        try:
            if self._vbo:
                glDeleteBuffers(1, [self._vbo])
            if self._vao:
                glDeleteVertexArrays(1, [self._vao])
        except Exception:
            pass
        self._vbo = 0
        self._vao = 0
