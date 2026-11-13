"""Integer rasterization with 2:1 dual-pixel edges and right-pixel anchors."""

from dataclasses import dataclass
from itertools import pairwise
from math import isclose

from PIL import Image, ImageColor, ImageDraw

from tilix.geometry import Point3, Shape, _point

type Color = str | tuple[int, int, int] | tuple[int, int, int, int]
type Pixel = tuple[int, int]
type RGBA = tuple[int, int, int, int]


def _integer(value: int, name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _color(value: Color) -> RGBA:
    if isinstance(value, str):
        return ImageColor.getcolor(value, "RGBA")
    if not isinstance(value, tuple) or len(value) not in (3, 4):
        raise TypeError(
            "a color must be a Pillow color string, RGB tuple, or RGBA tuple"
        )
    if any(isinstance(c, bool) or not isinstance(c, int) for c in value):
        raise TypeError("color channels must be integers")
    if any(not 0 <= c <= 255 for c in value):
        raise ValueError("color channels must be between 0 and 255")
    if len(value) == 3:
        return value[0], value[1], value[2], 255
    return value[0], value[1], value[2], value[3]


@dataclass(frozen=True)
class Grid:
    """Pixels per cell along each horizontal axis and along the vertical axis.

    x projects down-right, y down-left, and z straight up. A default cell spans
    12 pixels horizontally and 6 vertically along either ground axis. Its edge
    contains seven dual pixels including both endpoints, as in the TiliX grid.
    """

    cell_size: int = 12

    def __post_init__(self) -> None:
        _integer(self.cell_size, "cell_size", 2)
        if self.cell_size % 2:
            raise ValueError("cell_size must be even for a 2:1 pixel grid")

    def project(self, point: Point3) -> Pixel:
        """Project cells to an integer right-pixel anchor, without silent snapping."""
        x, y, z = _point(point)
        sx = (x - y) * self.cell_size
        sy = (x + y) * (self.cell_size // 2) - z * self.cell_size
        ix, iy = round(sx), round(sy)
        if (
            not isclose(sx, ix, rel_tol=0, abs_tol=1e-9)
            or not isclose(sy, iy, rel_tol=0, abs_tol=1e-9)
            or (ix - 2 * iy) % 4
        ):
            raise ValueError(
                f"point {point} does not land on a right pixel at "
                f"cell_size={self.cell_size}; use a larger compatible cell_size"
            )
        return ix, iy


@dataclass(frozen=True)
class Palette:
    """Explicit face colors and an optional one-pixel outline."""

    top: Color = "#a9e8ba"
    left: Color = "#5dbb8a"
    right: Color = "#338b75"
    outline: Color | None = "#233e46"

    def __post_init__(self) -> None:
        for name in ("top", "left", "right", "outline"):
            value = getattr(self, name)
            if name != "outline" or value is not None:
                object.__setattr__(self, name, _color(value))


def _is_isometric(a: Pixel, b: Pixel) -> bool:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return dy != 0 and abs(dx) == 2 * abs(dy)


def _clipped_corners(edges: set[tuple[Pixel, Pixel]]) -> set[Pixel]:
    """Find left silhouette joins where a full dual pixel would protrude."""
    neighbors: dict[Pixel, set[Pixel]] = {}
    for a, b in edges:
        if a != b:
            neighbors.setdefault(a, set()).add(b)
            neighbors.setdefault(b, set()).add(a)
    return {
        point
        for point, adjacent in neighbors.items()
        if all(other[0] >= point[0] for other in adjacent)
        and any(not _is_isometric(point, other) for other in adjacent)
    }


def _edge(
    draw: ImageDraw.ImageDraw,
    a: Pixel,
    b: Pixel,
    color: RGBA,
    clipped_corners: set[Pixel],
) -> None:
    if _is_isometric(a, b):
        # Full dual pixels along diagonals; a left silhouette join with a
        # vertical or other slope uses only its right-pixel anchor.
        if a[1] > b[1]:
            a, b = b, a
        step = 2 if b[0] > a[0] else -2
        for row in range(b[1] - a[1] + 1):
            x, y = a[0] + row * step, a[1] + row
            left = x if (x, y) in clipped_corners else x - 1
            draw.line(((left, y), (x, y)), fill=color)
    else:
        # Ramps may have slopes other than the ground-plane 2:1 directions.
        draw.line((a, b), fill=color, width=1)


def render(
    shape: Shape,
    *,
    grid: Grid = Grid(),
    palette: Palette = Palette(),
    padding: int = 4,
    scale: int = 1,
    background: Color = (0, 0, 0, 0),
) -> Image.Image:
    """Return an auto-sized RGBA Pillow image, transparent by default.

    Geometry must land on grid anchors. Rasterize once at native resolution;
    scale is a positive integer applied afterward using nearest-neighbor.
    Padding is measured in native pixels. This renders one shape, not a scene:
    custom faces must be visible, nonintersecting, and ordered back to front.
    """
    _integer(padding, "padding", 0)
    _integer(scale, "scale", 1)
    projected = [tuple(grid.project(p) for p in face.vertices) for face in shape.faces]
    edges = {
        (a, b) if a <= b else (b, a)
        for polygon in projected
        for a, b in pairwise((*polygon, polygon[0]))
    }
    clipped_corners = _clipped_corners(edges)
    points = [p for face in projected for p in face]
    min_x = min(x for x, _ in points)
    left_endpoints = {min(a, b) for a, b in edges if _is_isometric(a, b)}
    if any(p[0] == min_x and p not in clipped_corners for p in left_endpoints):
        min_x -= 1  # room for an unclipped dual pixel, e.g. on a flat tile
    max_x = max(x for x, _ in points)
    min_y, max_y = min(y for _, y in points), max(y for _, y in points)
    image = Image.new(
        "RGBA",
        (max_x - min_x + 1 + padding * 2, max_y - min_y + 1 + padding * 2),
        _color(background),
    )
    draw = ImageDraw.Draw(image)
    clipped_corners = {
        (x - min_x + padding, y - min_y + padding) for x, y in clipped_corners
    }
    screen_edges: set[tuple[Pixel, Pixel]] = set()
    for face, polygon in zip(shape.faces, projected, strict=True):
        polygon = tuple((x - min_x + padding, y - min_y + padding) for x, y in polygon)
        color = getattr(palette, face.shade)
        draw.polygon(polygon, fill=color)
        for a, b in pairwise((*polygon, polygon[0])):
            _edge(draw, a, b, color, clipped_corners)
            screen_edges.add((a, b) if a <= b else (b, a))
    if palette.outline is not None:
        for a, b in sorted(screen_edges):
            _edge(draw, a, b, palette.outline, clipped_corners)
    if scale != 1:
        image = image.resize(
            (image.width * scale, image.height * scale), Image.Resampling.NEAREST
        )
    return image
