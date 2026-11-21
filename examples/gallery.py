"""Generate individual sprites and a gallery: uv run python examples/gallery.py."""

from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw

from tilix import (
    Face,
    Palette,
    Shape,
    block,
    cube,
    ramp,
    render,
    stairs,
    wall,
    wall_joint,
)

BLOCK_CELLS = 4
RAMP_COUNT = 8


def ramp_group() -> Shape:
    """Eight touching strips sharing one block's base and a common ground plane."""
    strip_width = Fraction(BLOCK_CELLS, RAMP_COUNT)
    faces = []
    for i in range(RAMP_COUNT):
        x = i * strip_width
        height = (RAMP_COUNT - i) * strip_width
        strip = ramp(width=strip_width, depth=BLOCK_CELLS, height=height).translated(
            x=x
        )
        right_x = x + strip_width
        neighbor_height = height - strip_width
        # Only the side above the next, shorter ramp is exposed. Drawing each
        # full side would leave hidden outlines running through its neighbor.
        exposed_side = Face(
            (
                (right_x, 0, neighbor_height),
                (right_x, BLOCK_CELLS, 0),
                (right_x, 0, height),
            ),
            "right",
        )
        faces.extend((exposed_side, strip.faces[1]))
    return Shape(tuple(faces))


def main() -> None:
    output = Path("output")
    output.mkdir(exist_ok=True)
    standard_wall = dict(base_height=2, slope_height=2, top_height=4)
    corners = {
        "wall_corner_positive_x_positive_y": ("+x", "+y"),
        "wall_corner_positive_y_negative_x": ("+y", "-x"),
        "wall_corner_negative_x_negative_y": ("-x", "-y"),
        "wall_corner_negative_y_positive_x": ("-y", "+x"),
    }
    tees = {
        "wall_t_positive_x": ("+x", "+y", "-y"),
        "wall_t_positive_y": ("+y", "+x", "-x"),
        "wall_t_negative_x": ("-x", "+y", "-y"),
        "wall_t_negative_y": ("-y", "+x", "-x"),
    }
    # Block-sized bases are 4×4 cells; cell_cube shows a single cell for comparison.
    shapes = {
        "cube": cube(size=BLOCK_CELLS),
        "cell_cube": cube(size=1),
        "block": block(width=BLOCK_CELLS, depth=BLOCK_CELLS, height=2),
        "ramps": ramp_group(),
        "stairs": stairs(width=BLOCK_CELLS, depth=BLOCK_CELLS, height=4),
        "wall": wall(**standard_wall),
        "wall_y": wall(axis="y", **standard_wall),
        "wall_narrow": wall(
            base_width=3,
            top_width=1,
            **standard_wall,
        ),
        "wall_thin": wall(
            length=BLOCK_CELLS,
            base_width=2,
            base_height=2,
            slope_height=1,
            top_width=1,
            top_height=5,
        ),
        "wall_cross": wall_joint("+x", "+y", "-x", "-y", **standard_wall),
        **{
            name: wall_joint(*arms, **standard_wall)
            for variants in (corners, tees)
            for name, arms in variants.items()
        },
    }
    wall_palette = Palette(
        top="#d4d9e2", left="#9aa6ba", right="#697b96", outline="#354255"
    )
    palettes = {
        "cube": Palette(),
        "cell_cube": Palette(),
        "block": Palette(
            top="#ffc980", left="#e69958", right="#b76843", outline="#493a44"
        ),
        "ramps": Palette(
            top="#b8c5ff", left="#8798de", right="#616ca8", outline="#343d60"
        ),
        "stairs": Palette(
            top="#f4a4b4", left="#d77799", right="#a9537f", outline="#513c58"
        ),
    }
    labels = {
        "cell_cube": "cube (1 cell)",
        "ramps": "8 ramps",
        "wall": "wall (x axis)",
        "wall_y": "wall (y axis)",
        "wall_narrow": "wall (3 / 1 cells)",
        "wall_thin": "wall (2 / 1 cells)",
        "wall_cross": "4-way join",
        **{name: f"corner {' '.join(arms)}" for name, arms in corners.items()},
        **{name: f"T stem {arms[0]}" for name, arms in tees.items()},
    }
    sprites = {
        name: render(shape, palette=palettes.get(name, wall_palette))
        for name, shape in shapes.items()
    }
    rows = (
        ("cube", "cell_cube", "block", "ramps", "stairs"),
        ("wall", "wall_y", "wall_narrow", "wall_thin", "wall_cross"),
        tuple(corners),
        tuple(tees),
    )
    column_width = max(sprite.width for sprite in sprites.values()) + 16
    width = max(map(len, rows)) * column_width
    row_heights = [max(sprites[name].height for name in row) + 48 for row in rows]
    gallery = Image.new("RGBA", (width, sum(row_heights)), "#202830")
    draw = ImageDraw.Draw(gallery)
    row_top = 0
    for row, row_height in zip(rows, row_heights, strict=True):
        baseline = row_top + row_height - 36
        left = (width - len(row) * column_width) // 2
        for i, name in enumerate(row):
            sprite = sprites[name]
            sprite.save(output / f"{name}.png")
            center_x = left + i * column_width + column_width // 2
            gallery.alpha_composite(
                sprite, (center_x - sprite.width // 2, baseline - sprite.height)
            )
            draw.text(
                (center_x, baseline + 14),
                labels.get(name, name),
                fill="#dbe4ec",
                anchor="mm",
            )
        row_top += row_height
    gallery = gallery.resize(
        (gallery.width * 2, gallery.height * 2), Image.Resampling.NEAREST
    )
    gallery.save(output / "gallery.png")
    print(
        f"Saved {len(shapes)} transparent sprites and gallery.png to {output.resolve()}"
    )


if __name__ == "__main__":
    main()
