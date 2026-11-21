"""Integer rasterization with 2:1 dual-pixel edges and right-pixel anchors."""

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from math import isclose, lcm

from PIL import Image, ImageColor, ImageDraw

from tilix.geometry import Face, Point3, Shape, _point

type Color = str | tuple[int, int, int] | tuple[int, int, int, int]
type Pixel = tuple[int, int]
type RGBA = tuple[int, int, int, int]
type Edge = tuple[Pixel, Pixel]
type Span = tuple[int, int]


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


def _clipped_corners(edges: set[Edge]) -> set[Pixel]:
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


def _edge_rows(edge: Edge, clipped_corners: set[Pixel]) -> dict[int, Span]:
    """Rasterize a left-to-right edge into inclusive horizontal spans."""
    a, b = edge
    x, y = a
    dx, dy = b[0] - x, b[1] - y
    rise = abs(dy)
    direction = 1 if dy > 0 else -1
    if _is_isometric(a, b):
        anchors = ((x + 2 * row, y + direction * row) for row in range(rise + 1))
        return {
            py: (px if (px, py) in clipped_corners else px - 1, px)
            for px, py in anchors
        }
    if dy == 0:
        return {y: (x, b[0])}

    # Use one direction for rounding ties on edges shared by multiple faces.
    if rise >= dx:
        rows = {}
        for row in range(rise + 1):
            px = x + (row * dx + rise // 2) // rise
            rows[y + direction * row] = (px, px)
        return rows

    rows = {}
    for col in range(dx + 1):
        px = x + col
        py = y + direction * ((col * rise + dx // 2) // dx)
        first, _ = rows.get(py, (px, px))
        rows[py] = (first, px)
    return rows


def _face_crossings(
    face_edges: tuple[Edge, ...], edge_rows: dict[Edge, dict[int, Span]]
) -> dict[int, list[Edge]]:
    crossings = defaultdict(list)
    for edge in face_edges:
        # Count each crossing over a half-open interval at shared vertices.
        end_y = max(edge[0][1], edge[1][1])
        for y in edge_rows[edge]:
            if y < end_y:
                crossings[y].append(edge)
    for y, edges in crossings.items():
        edges.sort(key=lambda edge: edge_rows[edge][y])
    return crossings


def _close_triangle_tips(
    crossings: dict[int, list[Edge]],
    edge_rows: dict[Edge, dict[int, Span]],
) -> None:
    if not crossings:
        return
    gaps = {
        y: (edge_rows[left][y][1] + 1, edge_rows[right][y][0] - 1)
        for y, (left, right) in crossings.items()
    }
    widest = max(gaps, key=lambda y: gaps[y][1] - gaps[y][0])
    first_left, first_right = gaps[widest]
    if first_left > first_right:
        return

    # Once two borders pinch off a triangular face, join them through the
    # remaining taper so rounding does not reopen disconnected color pockets.
    for end, direction in ((min(gaps) - 1, -1), (max(gaps) + 1, 1)):
        previous_left, previous_right = first_left, first_right
        connected = True
        for y in range(widest + direction, end, direction):
            left, right = gaps[y]
            connected = (
                connected
                and left <= right
                and left <= previous_right + 1
                and right >= previous_left - 1
            )
            if connected:
                previous_left, previous_right = left, right
            else:
                # Neighboring faces use the merged coverage too, even when
                # their shared borders are drawn in face colors.
                left_edge, right_edge = crossings[y]
                a, b = edge_rows[left_edge][y], edge_rows[right_edge][y]
                merged = (min(a[0], b[0]), max(a[1], b[1]))
                edge_rows[left_edge][y] = edge_rows[right_edge][y] = merged


def _face_spans(
    perimeter: tuple[Edge, ...], edge_rows: dict[Edge, dict[int, Span]]
) -> Iterator[tuple[int, int, int]]:
    for edge in perimeter:
        for y, (left, right) in edge_rows[edge].items():
            yield y, left, right
    for y, crossings in _face_crossings(perimeter, edge_rows).items():
        pairs = zip(crossings[::2], crossings[1::2], strict=True)
        for left_edge, right_edge in pairs:
            left, right = edge_rows[left_edge][y][1], edge_rows[right_edge][y][0]
            if right > left + 1:
                yield y, left + 1, right - 1


def _depth_plane(
    face: Face, polygon: tuple[Pixel, ...]
) -> tuple[Fraction, Fraction, Fraction] | None:
    """Express world z as an affine function of projected pixel coordinates."""
    (x, y), *rest = polygon
    z, *heights = (Fraction(vertex[2]) for vertex in face.vertices)
    points = zip(rest, heights, strict=True)
    for ((bx, by), bz), ((cx, cy), cz) in pairwise(points):
        dx, dy, dz = bx - x, by - y, bz - z
        ex, ey, ez = cx - x, cy - y, cz - z
        det = dx * ey - dy * ex
        if det:
            ax = (dz * ey - dy * ez) / det
            ay = (dx * ez - dz * ex) / det
            return ax, ay, z - ax * x - ay * y
    # Grid tolerance can make an almost edge-on face exactly edge-on.
    return None


def _draw_visible_faces(
    image: Image.Image,
    shape: Shape,
    polygons: list[tuple[Pixel, ...]],
    face_edges: list[tuple[Edge, ...]],
    edge_rows: dict[Edge, dict[int, Span]],
    palette: Palette,
    offset_x: int,
    offset_y: int,
) -> None:
    # A viewing ray increases x, y, and z together. Compare z exactly in
    # integer units so a shared edge can win depth ties against a face fill.
    planes = [
        _depth_plane(face, polygon)
        for face, polygon in zip(shape.faces, polygons, strict=True)
    ]
    units = 2 * lcm(
        *(value.denominator for plane in planes if plane is not None for value in plane)
    )
    pixels = image.load()
    width = image.width
    depths: list[int | None] = [None] * (width * image.height)

    def paint(
        y: int,
        left: int,
        right: int,
        color: RGBA,
        plane: tuple[int, int, int],
        *,
        ink: bool = False,
    ) -> None:
        dx, dy, origin = plane
        py = y + offset_y
        row = py * width + offset_x
        depth = origin + dy * y + dx * left + ink
        for x in range(left, right + 1):
            index = row + x
            previous = depths[index]
            if previous is None or depth >= previous:
                depths[index] = depth
                pixels[x + offset_x, py] = color
            depth += dx

    for face, perimeter, plane in zip(shape.faces, face_edges, planes, strict=True):
        if plane is None:
            continue
        ax, ay, bias = plane
        pixel_plane = int(ax * units), int(ay * units), int(bias * units)
        color = getattr(palette, face.shade)
        for y, left, right in _face_spans(perimeter, edge_rows):
            paint(y, left, right, color, pixel_plane)
        if palette.outline is not None:
            for edge in perimeter:
                for y, (left, right) in edge_rows[edge].items():
                    paint(y, left, right, palette.outline, pixel_plane, ink=True)


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
    polygons = [tuple(grid.project(p) for p in face.vertices) for face in shape.faces]
    face_edges = [
        tuple((a, b) if a <= b else (b, a) for a, b in pairwise((*poly, poly[0])))
        for poly in polygons
    ]
    edges = {edge for perimeter in face_edges for edge in perimeter}
    clipped_corners = _clipped_corners(edges)
    edge_rows = {edge: _edge_rows(edge, clipped_corners) for edge in edges}
    for perimeter in face_edges:
        if len(perimeter) == 3:
            _close_triangle_tips(_face_crossings(perimeter, edge_rows), edge_rows)

    min_x = min(left for rows in edge_rows.values() for left, _ in rows.values())
    max_x = max(x for poly in polygons for x, _ in poly)
    min_y = min(y for poly in polygons for _, y in poly)
    max_y = max(y for poly in polygons for _, y in poly)
    image = Image.new(
        "RGBA",
        (max_x - min_x + 1 + padding * 2, max_y - min_y + 1 + padding * 2),
        _color(background),
    )
    offset_x, offset_y = padding - min_x, padding - min_y
    if shape._occlude:
        _draw_visible_faces(
            image, shape, polygons, face_edges, edge_rows, palette, offset_x, offset_y
        )
    else:
        draw = ImageDraw.Draw(image)

        def draw_span(y: int, left: int, right: int, color: RGBA) -> None:
            draw.line(
                (left + offset_x, y + offset_y, right + offset_x, y + offset_y), color
            )

        for face, perimeter in zip(shape.faces, face_edges, strict=True):
            color = getattr(palette, face.shade)
            for y, left, right in _face_spans(perimeter, edge_rows):
                draw_span(y, left, right, color)
        if palette.outline is not None:
            for rows in edge_rows.values():
                for y, (left, right) in rows.items():
                    draw_span(y, left, right, palette.outline)
    if scale != 1:
        image = image.resize(
            (image.width * scale, image.height * scale), Image.Resampling.NEAREST
        )
    return image
