"""VBO / VAO create and upload helpers using PyOpenGL.

Provides lightweight functions for the most common buffer operations
needed by the T.A.C.O. renderer.
"""

from __future__ import annotations

import ctypes
from typing import Optional

import numpy as np
from OpenGL.GL import *


def create_vbo(data: np.ndarray, usage: int = GL_STATIC_DRAW) -> int:
    """Create a new VBO, upload *data*, and return the buffer id.

    Parameters
    ----------
    data:
        Numpy array whose raw bytes will be uploaded.  Should already be
        the correct dtype (e.g. ``np.float32``).
    usage:
        OpenGL usage hint -- ``GL_STATIC_DRAW``, ``GL_DYNAMIC_DRAW``, etc.

    Returns
    -------
    int
        The OpenGL buffer object name (id).
    """
    vbo_id: int = int(glGenBuffers(1))
    glBindBuffer(GL_ARRAY_BUFFER, vbo_id)
    glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, usage)
    glBindBuffer(GL_ARRAY_BUFFER, 0)
    return vbo_id


def create_vao() -> int:
    """Create and return a new Vertex Array Object id."""
    vao_id: int = int(glGenVertexArrays(1))
    return vao_id


def update_vbo(vbo_id: int, data: np.ndarray, usage: int = GL_DYNAMIC_DRAW) -> None:
    """Re-upload *data* into an existing VBO.

    The entire buffer store is replaced via ``glBufferData``.

    Parameters
    ----------
    vbo_id:
        Existing buffer object name.
    data:
        Numpy array to upload.
    usage:
        OpenGL usage hint.
    """
    glBindBuffer(GL_ARRAY_BUFFER, vbo_id)
    glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, usage)
    glBindBuffer(GL_ARRAY_BUFFER, 0)


def bind_vbo(vbo_id: int) -> None:
    """Bind an existing VBO to ``GL_ARRAY_BUFFER``.

    Parameters
    ----------
    vbo_id:
        Buffer object name to bind.  Pass ``0`` to unbind.
    """
    glBindBuffer(GL_ARRAY_BUFFER, vbo_id)


def unbind_vbo() -> None:
    """Unbind the currently bound ``GL_ARRAY_BUFFER``."""
    glBindBuffer(GL_ARRAY_BUFFER, 0)


def delete_vbo(vbo_id: int) -> None:
    """Delete a VBO by id."""
    glDeleteBuffers(1, [vbo_id])


def delete_vao(vao_id: int) -> None:
    """Delete a VAO by id."""
    glDeleteVertexArrays(1, [vao_id])
