"""Ray-sphere intersection for 3D mouse picking.

Ported from Taco.Classes.MouseRay (MouseRay.cs).
Uses numpy for all matrix / vector math.  The viewport is given as
``(width, height)``.
"""

from __future__ import annotations

import math
from typing import Tuple

import numpy as np
from numpy.linalg import inv


class MouseRay:
    """A ray cast from screen-space mouse coordinates into the 3D scene.

    Parameters
    ----------
    x:
        Mouse X in window (pixel) coordinates.
    y:
        Mouse Y in window (pixel) coordinates.
    model_view:
        4x4 model-view matrix (numpy ``(4, 4)`` float64/float32).
    projection:
        4x4 projection matrix (numpy ``(4, 4)`` float64/float32).
    viewport_size:
        ``(width, height)`` of the viewport in pixels.
    """

    def __init__(
        self,
        x: float,
        y: float,
        model_view: np.ndarray,
        projection: np.ndarray,
        viewport_size: Tuple[int, int],
    ) -> None:
        width, height = viewport_size

        self._start: np.ndarray = self.unproject(x, y, 0.0, projection, model_view, viewport_size)
        self._end: np.ndarray = self.unproject(x, y, 1.0, projection, model_view, viewport_size)

        direction = self._end - self._start
        length = np.linalg.norm(direction)
        if length > 0.0:
            direction = direction / length
        self._direction: np.ndarray = direction

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def start(self) -> np.ndarray:
        """Near-plane world-space origin of the ray (3-component vector)."""
        return self._start

    @property
    def end(self) -> np.ndarray:
        """Far-plane world-space end of the ray (3-component vector)."""
        return self._end

    @property
    def direction(self) -> np.ndarray:
        """Normalised direction vector of the ray (3-component vector)."""
        return self._direction

    # ------------------------------------------------------------------
    # Unproject
    # ------------------------------------------------------------------

    @staticmethod
    def unproject(
        mouse_x: float,
        mouse_y: float,
        depth: float,
        projection: np.ndarray,
        model_view: np.ndarray,
        viewport: Tuple[int, int],
    ) -> np.ndarray:
        """Unproject a screen-space point to world-space.

        Reproduces the logic from the C# ``UnProject`` extension method:

        1. Map mouse coordinates into normalised device coordinates.
        2. Transform by the inverse projection, then inverse model-view.
        3. Perspective-divide by *w*.

        Parameters
        ----------
        mouse_x, mouse_y:
            Screen coordinates (pixels).
        depth:
            Depth value -- ``0.0`` for the near plane, ``1.0`` for the far plane.
        projection:
            4x4 projection matrix.
        model_view:
            4x4 model-view matrix.
        viewport:
            ``(width, height)`` in pixels.

        Returns
        -------
        np.ndarray
            3-component world-space position.
        """
        width, height = viewport

        # Normalised device coordinates (Y is flipped to match OpenGL convention)
        vec = np.array([
            2.0 * mouse_x / width - 1.0,
            -(2.0 * mouse_y / height - 1.0),
            depth,
            1.0,
        ], dtype=np.float64)

        proj_inv = inv(np.asarray(projection, dtype=np.float64))
        view_inv = inv(np.asarray(model_view, dtype=np.float64))

        # Transform: first by inverse projection, then by inverse model-view.
        # The C# code multiplies vec * matrix (row-vector convention).
        vec = proj_inv @ vec
        vec = view_inv @ vec

        # Perspective divide
        w = vec[3]
        if abs(w) > 1e-6:
            vec[0] /= w
            vec[1] /= w
            vec[2] /= w

        return vec[:3]

    # ------------------------------------------------------------------
    # Intersection tests
    # ------------------------------------------------------------------

    def intersection(self, point: np.ndarray, radius: float) -> float:
        """Return the signed distance along the ray to the closest intersection
        with a bounding sphere centred at *point* with the given *radius*.

        Returns ``0.0`` when the ray origin is inside the sphere or when there
        is no intersection.  A positive value means the intersection is in
        front of the ray origin.

        Ported from ``MouseRay.Intersection`` in the C# codebase.
        """
        center = np.asarray(point, dtype=np.float64)
        difference = center - self._start
        difference_length_sq: float = float(np.dot(difference, difference))
        radius_sq: float = radius * radius

        # Ray origin is inside the sphere.
        if difference_length_sq < radius_sq:
            return 0.0

        distance_along_ray: float = float(np.dot(self._direction, difference))

        # Sphere is entirely behind the ray.
        if distance_along_ray < 0.0:
            return 0.0

        # Discriminant of the ray-sphere quadratic.
        dist: float = radius_sq + distance_along_ray * distance_along_ray - difference_length_sq

        if dist < 0.0:
            return 0.0

        return distance_along_ray - math.sqrt(dist)

    def intersects(self, point: np.ndarray, radius: float) -> bool:
        """Return ``True`` if the ray intersects the bounding sphere.

        A positive ``intersection`` value means a hit.
        """
        t = self.intersection(point, radius)
        return t > 0.0
