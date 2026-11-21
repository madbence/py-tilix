from fractions import Fraction
from pathlib import Path
from runpy import run_path

import pytest
from PIL import Image

from tilix import (
    Face,
    Grid,
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


def test_projection_axes_and_negative_coordinates():
    grid = Grid()
    assert grid.project((0, 0, 0)) == (0, 0)
    assert grid.project((1, 0, 0)) == (12, 6)
    assert grid.project((0, 1, 0)) == (-12, 6)
    assert grid.project((0, 0, 1)) == (0, -12)
    assert grid.project((-1, -2, -3)) == (12, 18)


@pytest.mark.parametrize("fraction", [Fraction(1, 2), Fraction(1, 3), Fraction(1, 6)])
def test_subdivisions_stay_on_right_pixel_anchors(fraction):
    for point in [(fraction, 0, 0), (0, fraction, 0), (0, 0, fraction)]:
        x, y = Grid().project(point)
        assert (x - 2 * y) % 4 == 0


def test_float_subdivisions_tolerate_representation_error():
    assert Grid().project((1 / 3, 0, 0)) == (4, 2)


@pytest.mark.parametrize("point", [(0.25, 0, 0), (0, 0, Fraction(1, 12))])
def test_projection_rejects_subpixel_or_left_pixel_vertices(point):
    with pytest.raises(ValueError, match="right pixel"):
        Grid().project(point)


def test_a_larger_grid_supports_quarter_cells():
    assert Grid(cell_size=24).project((Fraction(1, 4), 0, 0)) == (6, 3)


@pytest.mark.parametrize("cell_size", [0, -2, 3])
def test_grid_needs_a_positive_even_cell_size(cell_size):
    with pytest.raises(ValueError, match="cell_size"):
        Grid(cell_size=cell_size)


@pytest.mark.parametrize("cell_size", [True, 12.0])
def test_grid_needs_an_integer_cell_size(cell_size):
    with pytest.raises(TypeError, match="cell_size"):
        Grid(cell_size=cell_size)


def test_cube_dimensions_include_dual_pixels_and_padding():
    assert render(cube()).size == (105, 105)
    assert render(cube(1), padding=0).size == (25, 25)


def test_cube_face_colors_and_single_pixel_vertical_edges():
    palette = Palette(top="red", left="green", right="blue", outline="black")
    image = render(cube(1), palette=palette, padding=0)
    assert image.getpixel((12, 6)) == (255, 0, 0, 255)
    assert image.getpixel((6, 15)) == (0, 128, 0, 255)
    assert image.getpixel((18, 15)) == (0, 0, 255, 255)
    assert image.getpixel((12, 18)) == (0, 0, 0, 255)
    assert image.getpixel((0, 8)) == (0, 0, 0, 255)
    assert image.getpixel((1, 8)) == (0, 128, 0, 255)
    padded = render(cube(1), palette=palette, padding=1)
    assert padded.getpixel((0, 9)) == (0, 0, 0, 0)


def test_isometric_diagonals_use_the_reference_dual_pixel_pattern():
    image = render(cube(1), padding=0)
    alpha = image.getchannel("A")
    assert [x for x in range(image.width) if alpha.getpixel((x, 0))] == [11, 12]
    outline = Palette().outline
    assert [x for x in range(image.width) if image.getpixel((x, 1)) == outline] == [
        9,
        10,
        13,
        14,
    ]


@pytest.mark.parametrize("outline", ["black", None])
@pytest.mark.parametrize("size", [1, 4])
def test_cube_left_corners_join_the_vertical_without_overhanging(outline, size):
    image = render(cube(size), palette=Palette(outline=outline), padding=0)
    assert image.width == image.height == 24 * size + 1
    alpha = image.getchannel("A")
    assert [y for y in range(image.height) if alpha.getpixel((0, y))] == list(
        range(6 * size, 18 * size + 1)
    )


@pytest.mark.parametrize("outline", ["black", None])
@pytest.mark.parametrize("shape", [block(4, 4, 2), ramp(), stairs()])
def test_left_silhouette_corners_have_no_extra_pixel(shape, outline):
    grid, padding = Grid(), 2
    image = render(shape, grid=grid, palette=Palette(outline=outline), padding=padding)
    assert image.width == 97 + 2 * padding
    # Known left silhouette corners, including each stair tread and the ramp tip.
    if shape == stairs():
        corners = [(0, 4 - i, i + 1) for i in range(4)] + [(0, 4, 0)]
    elif shape == ramp():
        corners = [(0, 4, 0)]
    else:
        corners = [(0, 4, 0), (0, 4, 2)]
    min_y = min(grid.project(p)[1] for face in shape.faces for p in face.vertices)
    for corner in corners:
        x, y = grid.project(corner)
        px, py = x + 48 + padding, y - min_y + padding
        assert image.getpixel((px, py))[3] == 255
        assert image.getpixel((px - 1, py))[3] == 0


def test_clipped_corners_preserve_an_opaque_background_at_integer_scale():
    image = render(cube(1), padding=1, scale=3, background="white")
    assert image.getpixel((0, 7 * 3)) == (255, 255, 255, 255)
    assert image.getpixel((3, 7 * 3)) == Palette().outline


@pytest.mark.parametrize(
    "shape",
    [
        cube(),
        block(2, 3, 1),
        ramp(),
        stairs(),
        wall(),
        wall(base_height=4, slope_height=4, top_height=8),
        wall(slope_height=Fraction(1, 2)),
        wall(length=1, base_width=6, slope_height=1),
        wall(slope_height=Fraction(1, 2), top_height=Fraction(1, 3)),
    ],
)
def test_shapes_have_no_transparent_holes_in_their_scanlines(shape):
    image = render(shape, padding=0)
    alpha = image.getchannel("A")
    for y in range(image.height):
        filled = [x for x in range(image.width) if alpha.getpixel((x, y))]
        if filled:
            assert filled == list(range(min(filled), max(filled) + 1))


@pytest.mark.parametrize("outline", ["black", None])
def test_eight_touching_ramps_have_no_stray_face_pixels(outline):
    gallery = run_path(str(Path(__file__).resolve().parents[1] / "examples/gallery.py"))
    palette = Palette(outline=outline)
    image = render(gallery["ramp_group"](), palette=palette, padding=1)

    for y in range(1, image.height - 1):
        for x in range(1, image.width - 1):
            color = image.getpixel((x, y))
            if color in (palette.top, palette.right):
                assert any(
                    image.getpixel((x + dx, y + dy)) == color
                    for dx in (-1, 0, 1)
                    for dy in (-1, 0, 1)
                    if dx or dy
                ), (x, y)

    # The final ramp's bottom tip is exactly one dual pixel wide.
    tip_row = image.getchannel("A").crop(
        (0, image.height - 2, image.width, image.height - 1)
    )
    assert tip_row.getbbox() == (48, 0, 50, 1)


def test_one_step_stairs_render_as_a_block():
    assert (
        render(stairs(2, 3, 4, steps=1)).tobytes() == render(block(2, 3, 4)).tobytes()
    )


def test_equal_width_wall_renders_as_a_block_without_tier_seams():
    actual = render(wall(length=3, base_width=2, top_width=2))
    expected = render(block(3, 2, 4))
    assert actual.size == expected.size
    assert actual.tobytes() == expected.tobytes()


def test_wall_example_renders_at_full_height():
    image = render(wall(base_height=2, slope_height=2, top_height=4), padding=0)
    assert image.mode == "RGBA"
    assert image.size == (97, 139)
    assert image.getchannel("A").getbbox() == (0, 0, 97, 139)


def test_cross_roof_and_front_cap_hide_edges_of_the_rear_arms():
    palette = Palette(top="red", left="green", right="blue", outline="black")
    joint = wall_joint(
        "+x", "+y", "-x", "-y", base_height=2, slope_height=1, top_height=5
    )
    image = render(joint, palette=palette, padding=0)
    assert image.size == (73, 130)
    assert image.getpixel((36, 15)) == palette.top
    assert image.getpixel((24, 21)) == palette.top
    assert image.getpixel((48, 21)) == palette.top
    assert image.getpixel((60, 63)) == palette.right
    assert image.getpixel((36, 57)) == palette.outline
    assert (
        render(joint.translated(2, -3, 1), palette=palette, padding=0).tobytes()
        == image.tobytes()
    )


def test_fractional_cells_render_at_the_equivalent_native_resolution():
    small = render(cube(Fraction(1, 3)))
    coarse = render(cube(1), grid=Grid(cell_size=4))
    assert small.size == coarse.size
    assert small.tobytes() == coarse.tobytes()


def test_translation_does_not_change_an_auto_cropped_sprite():
    assert render(cube().translated(-3, 2, 1)).tobytes() == render(cube()).tobytes()


def test_nearest_neighbor_scaling_introduces_no_new_colors():
    native = render(stairs())
    scaled = render(stairs(), scale=3)
    assert scaled.size == (native.width * 3, native.height * 3)
    assert set(scaled.get_flattened_data()) == set(native.get_flattened_data())
    assert (
        scaled.resize(native.size, Image.Resampling.NEAREST).tobytes()
        == native.tobytes()
    )


def test_padding_adds_exactly_the_requested_transparent_border():
    bare = render(cube(1), padding=0)
    padded = render(cube(1), padding=3)
    assert padded.size == (bare.width + 6, bare.height + 6)
    assert (
        padded.crop((3, 3, padded.width - 3, padded.height - 3)).tobytes()
        == bare.tobytes()
    )
    assert padded.getchannel("A").getbbox() == (
        3,
        3,
        padded.width - 3,
        padded.height - 3,
    )


def test_outline_can_be_disabled_and_background_can_be_opaque():
    palette = Palette(outline=None)
    image = render(cube(), palette=palette, background="white")
    assert image.getpixel((0, 0)) == (255, 255, 255, 255)
    assert set(image.get_flattened_data()) == {
        palette.top,
        palette.left,
        palette.right,
        (255, 255, 255, 255),
    }


def test_rgba_colors_preserve_alpha():
    palette = Palette(top=(255, 0, 0, 128), outline=None)
    assert render(cube(1), palette=palette, padding=0).getpixel((12, 6)) == (
        255,
        0,
        0,
        128,
    )


def test_png_roundtrip_preserves_rgba_pixels(tmp_path):
    expected = render(ramp(), scale=2)
    path = tmp_path / "ramp.png"
    expected.save(path)
    with Image.open(path) as actual:
        assert actual.format == "PNG"
        assert actual.mode == "RGBA"
        assert actual.size == expected.size
        assert actual.tobytes() == expected.tobytes()


def test_custom_visible_face_uses_the_same_grid_and_renderer():
    tile = Shape((Face(((0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0))),))
    image = render(tile, padding=0)
    assert image.size == (50, 25)
    # A flat diamond has no vertical or sloping side at its left corner;
    # keep the full dual pixel of the grid itself.
    assert image.getpixel((0, 12)) == Palette().outline
    assert image.getpixel((1, 12)) == Palette().outline


@pytest.mark.parametrize("kwargs", [{"scale": 0}, {"scale": -1}, {"padding": -1}])
def test_invalid_render_sizes_fail_clearly(kwargs):
    with pytest.raises(ValueError):
        render(cube(), **kwargs)


@pytest.mark.parametrize("kwargs", [{"scale": 1.5}, {"padding": True}])
def test_render_sizes_must_be_integers(kwargs):
    with pytest.raises(TypeError):
        render(cube(), **kwargs)


@pytest.mark.parametrize("color", [(300, 0, 0), (-1, 0, 0), "not a color"])
def test_invalid_colors_fail_at_palette_creation(color):
    with pytest.raises(ValueError):
        Palette(top=color)


@pytest.mark.parametrize("color", [(0.5, 0, 0), (True, 0, 0), (1, 2), [1, 2, 3]])
def test_malformed_colors_fail_at_palette_creation(color):
    with pytest.raises(TypeError):
        Palette(top=color)


def test_incompatible_step_count_reports_grid_alignment():
    with pytest.raises(ValueError, match="right pixel"):
        render(stairs(steps=5))
