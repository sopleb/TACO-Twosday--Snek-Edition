"""GLSL shader compile/link wrapper using PyOpenGL.

Ported from Taco.Classes.Shader (Shader.cs).
Provides compile, link, uniform setters, bind/unbind, and texture binding.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import numpy as np
from OpenGL.GL import *

logger = logging.getLogger(__name__)


class Shader:
    """Vertex + Fragment shader program wrapper.

    Compiles GLSL source, links into a program, and exposes typed uniform
    setters that mirror the original C# overloads of ``SetVariable``.
    Uniform locations are cached in an internal dict so repeated lookups
    are free after the first call.

    Can be constructed with shader sources for immediate compilation::

        shader = Shader(vert_source, frag_source)

    Or constructed empty and compiled later::

        shader = Shader()
        shader.compile(vert_source, frag_source)
    """

    def __init__(self, vert_source: str = "", frag_source: str = "") -> None:
        self._program: int = 0
        self._uniforms: dict[str, int] = {}
        if vert_source or frag_source:
            self.compile(vert_source, frag_source)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def program_id(self) -> int:
        """Return the raw OpenGL program handle."""
        return self._program

    # ------------------------------------------------------------------
    # Compile / Link
    # ------------------------------------------------------------------

    def compile(self, vert_source: str = "", frag_source: str = "") -> bool:
        """Compile vertex/fragment sources and link the program.

        Either *vert_source* or *frag_source* (or both) must be non-empty.
        Returns ``True`` on success.
        """
        if not vert_source and not frag_source:
            logger.error("Shader.compile: nothing to compile (both sources empty)")
            return False

        # Clean up a previous program if we are recompiling.
        if self._program > 0:
            glDeleteProgram(self._program)
        self._uniforms.clear()

        self._program = glCreateProgram()

        # --- vertex shader ---------------------------------------------------
        if vert_source:
            vert_shader = glCreateShader(GL_VERTEX_SHADER)
            glShaderSource(vert_shader, vert_source)
            glCompileShader(vert_shader)

            if glGetShaderiv(vert_shader, GL_COMPILE_STATUS) != GL_TRUE:
                info = glGetShaderInfoLog(vert_shader)
                if isinstance(info, bytes):
                    info = info.decode("utf-8", errors="replace")
                logger.error("Failed to compile vertex shader:\n%s", info)
                glDeleteShader(vert_shader)
                glDeleteProgram(self._program)
                self._program = 0
                return False

            glAttachShader(self._program, vert_shader)
            glDeleteShader(vert_shader)

        # --- fragment shader --------------------------------------------------
        if frag_source:
            frag_shader = glCreateShader(GL_FRAGMENT_SHADER)
            glShaderSource(frag_shader, frag_source)
            glCompileShader(frag_shader)

            if glGetShaderiv(frag_shader, GL_COMPILE_STATUS) != GL_TRUE:
                info = glGetShaderInfoLog(frag_shader)
                if isinstance(info, bytes):
                    info = info.decode("utf-8", errors="replace")
                logger.error("Failed to compile fragment shader:\n%s", info)
                glDeleteShader(frag_shader)
                glDeleteProgram(self._program)
                self._program = 0
                return False

            glAttachShader(self._program, frag_shader)
            glDeleteShader(frag_shader)

        # --- link -------------------------------------------------------------
        glLinkProgram(self._program)

        if glGetProgramiv(self._program, GL_LINK_STATUS) != GL_TRUE:
            info = glGetProgramInfoLog(self._program)
            if isinstance(info, bytes):
                info = info.decode("utf-8", errors="replace")
            logger.error("Failed to link shader program:\n%s", info)
            glDeleteProgram(self._program)
            self._program = 0
            return False

        return True

    # ------------------------------------------------------------------
    # Uniform location cache
    # ------------------------------------------------------------------

    def _get_uniform_location(self, name: str) -> int:
        """Return the cached uniform location for *name*, or query and cache it."""
        if name in self._uniforms:
            return self._uniforms[name]

        location: int = glGetUniformLocation(self._program, name)
        if location == -1:
            logger.warning("Shader: uniform '%s' not found in program %d", name, self._program)
        else:
            self._uniforms[name] = location
        return location

    # ------------------------------------------------------------------
    # Bind / Unbind
    # ------------------------------------------------------------------

    def bind(self) -> None:
        """Bind this shader program for rendering."""
        if self._program > 0:
            glUseProgram(self._program)

    @staticmethod
    def unbind() -> None:
        """Unbind any active shader program."""
        glUseProgram(0)

    # ------------------------------------------------------------------
    # Uniform setters
    #
    # These assume the program is already bound via bind().
    # ------------------------------------------------------------------

    def set_uniform_mat4(self, name: str, matrix: np.ndarray, transpose: bool = True) -> None:
        """Set a ``mat4`` uniform.

        *matrix* must be a (4, 4) or (16,) float32 numpy array.
        *transpose* defaults to ``True`` because numpy matrices are row-major
        while OpenGL expects column-major data.
        """
        loc = self._get_uniform_location(name)
        if loc != -1:
            mat = np.asarray(matrix, dtype=np.float32)
            glUniformMatrix4fv(loc, 1, GL_TRUE if transpose else GL_FALSE, mat)

    def set_uniform_1f(self, name: str, value: float) -> None:
        """Set a ``float`` uniform."""
        loc = self._get_uniform_location(name)
        if loc != -1:
            glUniform1f(loc, value)

    def set_uniform_1i(self, name: str, value: int) -> None:
        """Set an ``int`` uniform."""
        loc = self._get_uniform_location(name)
        if loc != -1:
            glUniform1i(loc, value)

    def set_uniform_1iv(self, name: str, values: Sequence[int]) -> None:
        """Set an ``int[]`` uniform (``uniform int name[N]``)."""
        loc = self._get_uniform_location(name)
        if loc != -1:
            arr = np.asarray(values, dtype=np.int32)
            glUniform1iv(loc, len(arr), arr)

    def set_uniform_1fv(self, name: str, values: Sequence[float]) -> None:
        """Set a ``float[]`` uniform (``uniform float name[N]``)."""
        loc = self._get_uniform_location(name)
        if loc != -1:
            arr = np.asarray(values, dtype=np.float32)
            glUniform1fv(loc, len(arr), arr)

    def set_uniform_vec2(self, name: str, x: float, y: float) -> None:
        """Set a ``vec2`` uniform."""
        loc = self._get_uniform_location(name)
        if loc != -1:
            glUniform2f(loc, x, y)

    def set_uniform_vec3(self, name: str, x: float, y: float, z: float) -> None:
        """Set a ``vec3`` uniform."""
        loc = self._get_uniform_location(name)
        if loc != -1:
            glUniform3f(loc, x, y, z)

    def set_uniform_vec4(self, name: str, x: float, y: float, z: float, w: float) -> None:
        """Set a ``vec4`` uniform."""
        loc = self._get_uniform_location(name)
        if loc != -1:
            glUniform4f(loc, x, y, z, w)

    # ------------------------------------------------------------------
    # Texture binding
    # ------------------------------------------------------------------

    def bind_texture(self, texture_id: int, texture_unit: int, name: str) -> None:
        """Bind *texture_id* to *texture_unit* and set the sampler uniform *name*.

        *texture_unit* is the zero-based texture unit index (0 for
        ``GL_TEXTURE0``, 1 for ``GL_TEXTURE1``, etc.).

        Assumes the program is already bound via :meth:`bind`.
        """
        loc = self._get_uniform_location(name)
        if loc != -1:
            glActiveTexture(GL_TEXTURE0 + texture_unit)
            glBindTexture(GL_TEXTURE_2D, texture_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glUniform1i(loc, texture_unit)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def dispose(self) -> None:
        """Delete the program from the GPU."""
        if self._program != 0:
            glDeleteProgram(self._program)
            self._program = 0
            self._uniforms.clear()

    def __del__(self) -> None:
        # Best-effort cleanup; the GL context may already be gone.
        try:
            self.dispose()
        except Exception:
            pass
