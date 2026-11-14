"""Generate individual sprites and a gallery: uv run python examples/gallery.py."""

from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw

from tilix import Face, Palette, Shape, block, cube, ramp, render, stairs, wall

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
    # Block-sized bases are 4×4 cells; cell_cube shows a single cell for comparison.
    shapes = {
        "cube": cube(size=BLOCK_CELLS),
        "cell_cube": cube(size=1),
        "block": block(width=BLOCK_CELLS, depth=BLOCK_CELLS, height=2),
        "ramps": ramp_group(),
        "stairs": stairs(width=BLOCK_CELLS, depth=BLOCK_CELLS, height=4),
        "wall": wall(
            length=BLOCK_CELLS,
            base_width=BLOCK_CELLS,
            base_height=2,
            slope_height=2,
            top_width=BLOCK_CELLS / 2,
            top_height=4,
        ),
        "wall_narrow": wall(
            length=BLOCK_CELLS,
            base_width=3,
            base_height=2,
            slope_height=2,
            top_width=1,
            top_height=4,
        ),
        "wall_thin": wall(
            length=BLOCK_CELLS,
            base_width=2,
            base_height=2,
            slope_height=1,
            top_width=1,
            top_height=5,
        ),
    }
    ramp_palette = Palette(
        top="#b8c5ff", left="#8798de", right="#616ca8", outline="#343d60"
    )
    palettes = [
        Palette(),
        Palette(),
        Palette(top="#ffc980", left="#e69958", right="#b76843", outline="#493a44"),
        ramp_palette,
        Palette(top="#f4a4b4", left="#d77799", right="#a9537f", outline="#513c58"),
        Palette(top="#d4d9e2", left="#9aa6ba", right="#697b96", outline="#354255"),
        Palette(top="#d4d9e2", left="#9aa6ba", right="#697b96", outline="#354255"),
        Palette(top="#d4d9e2", left="#9aa6ba", right="#697b96", outline="#354255"),
    ]
    labels = {
        "cell_cube": "cube (1 cell)",
        "ramps": "8 ramps",
        "wall_narrow": "wall (3 / 1 cells)",
        "wall_thin": "wall (2 / 1 cells)",
    }
    sprites = [
        render(shape, palette=palette)
        for shape, palette in zip(shapes.values(), palettes, strict=True)
    ]
    baseline = max(120, max(sprite.height for sprite in sprites) + 12)
    gallery = Image.new("RGBA", (len(shapes) * 140, baseline + 40), "#202830")
    draw = ImageDraw.Draw(gallery)
    for i, (name, sprite) in enumerate(zip(shapes, sprites, strict=True)):
        sprite.save(output / f"{name}.png")
        x, y = i * 140 + (140 - sprite.width) // 2, baseline - sprite.height
        gallery.alpha_composite(sprite, (x, y))
        label = labels.get(name, name)
        draw.text((i * 140 + 70, baseline + 18), label, fill="#dbe4ec", anchor="mm")
    gallery = gallery.resize(
        (gallery.width * 2, gallery.height * 2), Image.Resampling.NEAREST
    )
    gallery.save(output / "gallery.png")
    print(
        f"Saved {len(shapes)} transparent sprites and gallery.png to {output.resolve()}"
    )


if __name__ == "__main__":
    main()
