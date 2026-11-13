"""Immutable visible surfaces, measured in grid cells."""

from dataclasses import dataclass
from fractions import Fraction
from math import isfinite
from typing import Literal

type Scalar = int | float | Fraction
type Point3 = tuple[Scalar, Scalar, Scalar]
type Shade = Literal["top", "left", "right"]


def _number(value: Scalar, name: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float, Fraction)):
        raise TypeError(f"{name} must be an int, float, or Fraction")
    if isinstance(value, float) and not isfinite(value):
        raise ValueError(f"{name} must be finite")
    return Fraction(str(value)) if isinstance(value, float) else Fraction(value)


def _positive(value: Scalar, name: str) -> Fraction:
    result = _number(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _point(point: Point3) -> tuple[Fraction, Fraction, Fraction]:
    if len(point) != 3:
        raise ValueError("a point must have three coordinates")
    x, y, z = point
    return _number(x, "coordinate"), _number(y, "coordinate"), _number(z, "coordinate")


@dataclass(frozen=True)
class Face:
    """A visible polygon with a palette shade; vertices follow its perimeter.

    Only provide camera-facing surfaces. The renderer draws faces in the order
    supplied by a Shape; it does not remove hidden surfaces from arbitrary meshes.
    """

    vertices: tuple[Point3, ...]
    shade: Shade = "top"

    def __post_init__(self) -> None:
        if len(self.vertices) < 3:
            raise ValueError("a face must have at least three vertices")
        if self.shade not in ("top", "left", "right"):
            raise ValueError("shade must be 'top', 'left', or 'right'")
        object.__setattr__(self, "vertices", tuple(map(_point, self.vertices)))


@dataclass(frozen=True)
class Shape:
    """Visible faces, ordered from back to front, independent of resolution."""

    faces: tuple[Face, ...]

    def __post_init__(self) -> None:
        faces = tuple(self.faces)
        if not faces:
            raise ValueError("a shape must have at least one face")
        if not all(isinstance(face, Face) for face in faces):
            raise TypeError("faces must contain Face objects")
        object.__setattr__(self, "faces", faces)

    def translated(self, x: Scalar = 0, y: Scalar = 0, z: Scalar = 0) -> "Shape":
        """Return a copy moved by the given number of cells."""
        dx, dy, dz = _point((x, y, z))
        return Shape(
            tuple(
                Face(tuple((a + dx, b + dy, c + dz) for a, b, c in f.vertices), f.shade)
                for f in self.faces
            )
        )


def block(width: Scalar = 4, depth: Scalar = 4, height: Scalar = 4) -> Shape:
    """A rectangular block extending from the origin along +x, +y, and +z."""
    w, d, h = (
        _positive(width, "width"),
        _positive(depth, "depth"),
        _positive(height, "height"),
    )
    return Shape(
        (
            Face(((w, 0, 0), (w, d, 0), (w, d, h), (w, 0, h)), "right"),
            Face(((0, d, 0), (w, d, 0), (w, d, h), (0, d, h)), "left"),
            Face(((0, 0, h), (w, 0, h), (w, d, h), (0, d, h)), "top"),
        )
    )


def cube(size: Scalar = 4) -> Shape:
    """A cube; the default size is four TiliX-inspired cells per axis."""
    return block(size, size, size)


def ramp(width: Scalar = 4, depth: Scalar = 4, height: Scalar = 4) -> Shape:
    """A solid wedge, highest at y=0 and descending toward y=depth."""
    w, d, h = (
        _positive(width, "width"),
        _positive(depth, "depth"),
        _positive(height, "height"),
    )
    return Shape(
        (
            Face(((w, 0, 0), (w, d, 0), (w, 0, h)), "right"),
            Face(((0, 0, h), (w, 0, h), (w, d, 0), (0, d, 0)), "top"),
        )
    )


def stairs(
    width: Scalar = 4,
    depth: Scalar = 4,
    height: Scalar = 4,
    *,
    steps: int = 4,
) -> Shape:
    """Solid stairs, highest at y=0, with equally sized treads and risers.

    The total depth and height are divided by steps. Choose a render grid on
    which each resulting vertex lands on a right pixel.
    """
    if isinstance(steps, bool) or not isinstance(steps, int):
        raise TypeError("steps must be an integer")
    if steps < 1:
        raise ValueError("steps must be positive")
    w, d, h = (
        _positive(width, "width"),
        _positive(depth, "depth"),
        _positive(height, "height"),
    )
    tread, rise = d / steps, h / steps
    # One continuous side avoids seams between stacked or overlapping blocks.
    profile: list[Point3] = [(w, 0, 0), (w, d, 0)]
    for i in range(steps):
        y, z = d - i * tread, (i + 1) * rise
        profile.extend(((w, y, z), (w, y - tread, z)))
    faces = [Face(tuple(profile), "right")]
    for i in range(steps):
        near_y, far_y = d - i * tread, d - (i + 1) * tread
        low_z, high_z = i * rise, (i + 1) * rise
        faces.extend(
            (
                Face(
                    (
                        (0, near_y, low_z),
                        (w, near_y, low_z),
                        (w, near_y, high_z),
                        (0, near_y, high_z),
                    ),
                    "left",
                ),
                Face(
                    (
                        (0, far_y, high_z),
                        (w, far_y, high_z),
                        (w, near_y, high_z),
                        (0, near_y, high_z),
                    ),
                    "top",
                ),
            )
        )
    return Shape(tuple(faces))
