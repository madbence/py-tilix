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


def wall(
    length: Scalar = 4,
    *,
    base_width: Scalar = 4,
    base_height: Scalar = 1,
    slope_height: Scalar = 1,
    top_width: Scalar = 2,
    top_height: Scalar = 2,
) -> Shape:
    """A wall along +x with a centered, narrower top and sloping shoulders.

    All dimensions are in cells. The base spans y=0 to base_width; the top
    is centered across that width. Heights describe three consecutive tiers:
    vertical base, sloping transition, and vertical top. Total height is
    base_height + slope_height + top_height. All dimensions must be positive,
    and top_width must not exceed base_width. Equal widths form a plain block.
    """
    length = _positive(length, "length")
    base_width = _positive(base_width, "base_width")
    base_height = _positive(base_height, "base_height")
    slope_height = _positive(slope_height, "slope_height")
    top_width = _positive(top_width, "top_width")
    top_height = _positive(top_height, "top_height")
    if top_width > base_width:
        raise ValueError("top_width must not exceed base_width")

    shoulder = base_height + slope_height
    height = shoulder + top_height
    if top_width == base_width:
        return block(length, base_width, height)
    far_y = (base_width - top_width) / 2
    near_y = (base_width + top_width) / 2
    faces = []
    if slope_height < far_y:
        # A shallow far shoulder peeks out around the upper wall. Clip its
        # hidden part against the upper wall's far top edge and end corner.
        cutoff = far_y - top_height / (1 - slope_height / far_y)
        end_y = max(Fraction(0), cutoff, far_y - length)
        end_x = length - far_y + end_y
        shoulder_points = [(length, 0), (length, far_y), (end_x, end_y)]
        if cutoff > 0 and end_x > 0:
            shoulder_points.append((0, cutoff))
        if end_y > 0:
            shoulder_points.append((0, 0))
        faces.append(
            Face(
                tuple(
                    (x, y, base_height + slope_height * y / far_y)
                    for x, y in shoulder_points
                ),
                "top",
            )
        )
    return Shape(
        (
            *faces,
            # One end profile avoids internal seams between the three tiers.
            Face(
                (
                    (length, 0, 0),
                    (length, base_width, 0),
                    (length, base_width, base_height),
                    (length, near_y, shoulder),
                    (length, near_y, height),
                    (length, far_y, height),
                    (length, far_y, shoulder),
                    (length, 0, base_height),
                ),
                "right",
            ),
            Face(
                (
                    (0, base_width, 0),
                    (length, base_width, 0),
                    (length, base_width, base_height),
                    (0, base_width, base_height),
                ),
                "left",
            ),
            Face(
                (
                    (0, base_width, base_height),
                    (length, base_width, base_height),
                    (length, near_y, shoulder),
                    (0, near_y, shoulder),
                ),
                "top",
            ),
            Face(
                (
                    (0, near_y, shoulder),
                    (length, near_y, shoulder),
                    (length, near_y, height),
                    (0, near_y, height),
                ),
                "left",
            ),
            Face(
                (
                    (0, far_y, height),
                    (length, far_y, height),
                    (length, near_y, height),
                    (0, near_y, height),
                ),
                "top",
            ),
        )
    )


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
