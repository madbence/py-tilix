from fractions import Fraction
from itertools import pairwise

import pytest

from tilix import Face, Shape, block, cube, ramp, stairs, wall, wall_joint


@pytest.mark.parametrize("factory", [cube, block, ramp, stairs, wall])
def test_default_dimensions(factory):
    points = [p for face in factory().faces for p in face.vertices]
    assert tuple(min(p[i] for p in points) for i in range(3)) == (0, 0, 0)
    assert tuple(max(p[i] for p in points) for i in range(3)) == (4, 4, 4)


def test_block_exposes_only_the_three_visible_surfaces():
    shape = block(width=2, depth=3, height=4)
    right, left, top = shape.faces
    assert {p[0] for p in right.vertices} == {2}
    assert {p[1] for p in left.vertices} == {3}
    assert {p[2] for p in top.vertices} == {4}
    assert [f.shade for f in shape.faces] == ["right", "left", "top"]


def test_ramp_top_descends_toward_positive_y():
    side, slope = ramp(width=2, depth=3, height=4).faces
    assert len(side.vertices) == 3
    assert {(y, z) for _, y, z in slope.vertices} == {(0, 4), (3, 0)}


def test_stairs_have_one_continuous_side_and_equal_treads():
    shape = stairs(width=2, depth=4, height=2, steps=3)
    assert len(shape.faces) == 7
    assert shape.faces[0].shade == "right"
    treads = [face for face in shape.faces if face.shade == "top"]
    assert [face.vertices[0][2] for face in treads] == [
        Fraction(2, 3),
        Fraction(4, 3),
        2,
    ]
    for tread in treads:
        ys = [p[1] for p in tread.vertices]
        assert max(ys) - min(ys) == Fraction(4, 3)


def test_translation_preserves_the_original_shape():
    original = cube(1)
    moved = original.translated(-2, 3, Fraction(1, 2))
    assert original.faces[-1].vertices[0] == (0, 0, 1)
    assert moved.faces[-1].vertices[0] == (-2, 3, Fraction(3, 2))


def test_wall_has_a_centered_top_and_three_consecutive_tiers():
    end, base, slope, upper, top = wall(
        length=4,
        base_width=4,
        base_height=4,
        slope_height=4,
        top_width=2,
        top_height=8,
    ).faces
    assert end.vertices == (
        (4, 0, 0),
        (4, 4, 0),
        (4, 4, 4),
        (4, 3, 8),
        (4, 3, 16),
        (4, 1, 16),
        (4, 1, 8),
        (4, 0, 4),
    )
    assert {p[2] for p in base.vertices} == {0, 4}
    assert {(p[1], p[2]) for p in slope.vertices} == {(4, 4), (3, 8)}
    assert {p[2] for p in upper.vertices} == {8, 16}
    assert {p[1] for p in top.vertices} == {1, 3}
    assert {p[2] for p in top.vertices} == {16}


def test_wall_preserves_exact_fractional_dimensions():
    shape = wall(base_width=1, top_width=Fraction(1, 3))
    assert {p[1] for p in shape.faces[-1].vertices} == {
        Fraction(1, 3),
        Fraction(2, 3),
    }


def test_shallow_wall_shoulder_is_clipped_behind_the_upper_wall():
    shoulder = wall(slope_height=Fraction(1, 2)).faces[0]
    assert shoulder.shade == "top"
    assert set(shoulder.vertices) == {(4, 0, 1), (4, 1, Fraction(3, 2)), (3, 0, 1)}


@pytest.mark.parametrize(
    "dimension",
    ["length", "base_width", "base_height", "slope_height", "top_width", "top_height"],
)
@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True, "4", None])
def test_wall_validates_every_dimension(dimension, value):
    error = TypeError if value is None or isinstance(value, (bool, str)) else ValueError
    with pytest.raises(error, match=dimension):
        wall(**{dimension: value})


def test_wall_rejects_an_overhanging_top():
    with pytest.raises(ValueError, match="top_width"):
        wall(base_width=2, top_width=3)


def test_perpendicular_wall_exchanges_the_ground_axes_and_side_shades():
    settings = dict(length=6, base_width=3, top_width=1, slope_height=Fraction(1, 2))
    original = wall(**settings)
    rotated = wall(axis="y", **settings)
    mirrored_shades = {"top": "top", "right": "left", "left": "right"}
    assert rotated.faces == tuple(
        Face(tuple((y, x, z) for x, y, z in face.vertices), mirrored_shades[face.shade])
        for face in original.faces
    )


@pytest.mark.parametrize(
    "arms",
    [
        ("+x", "+y"),
        ("+y", "-x"),
        ("-x", "-y"),
        ("-y", "+x"),
        ("+x", "+y", "-y"),
        ("+y", "+x", "-x"),
        ("-x", "+y", "-y"),
        ("-y", "+x", "-x"),
        ("+x", "+y", "-x", "-y"),
    ],
)
def test_joint_roof_is_one_polygon_with_the_requested_arms(arms):
    shape = wall_joint(*arms, length=3)
    roof = shape.faces[-1].vertices
    assert {z for _, _, z in roof} == {4}
    assert min(x for x, _, _ in roof) == (-5 if "-x" in arms else -1)
    assert max(x for x, _, _ in roof) == (5 if "+x" in arms else 1)
    assert min(y for _, y, _ in roof) == (-5 if "-y" in arms else -1)
    assert max(y for _, y, _ in roof) == (5 if "+y" in arms else 1)
    twice_area = sum(
        x * by - bx * y for (x, y, _), (bx, by, _) in pairwise((*roof, roof[0]))
    )
    assert twice_area == 2 * (2 * 2 + len(arms) * 4 * 2)
    assert wall_joint(*reversed(arms), length=3) == shape


@pytest.mark.parametrize("arms", [(), ("+x",), ("+y", "-y"), ("+x", "+x"), ("+x", "z")])
def test_joint_requires_distinct_arms_that_form_a_corner_t_or_cross(arms):
    with pytest.raises(ValueError, match="arm"):
        wall_joint(*arms)


@pytest.mark.parametrize("factory", [cube, block, ramp, stairs])
@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_dimensions_must_be_positive_and_finite(factory, value):
    with pytest.raises(ValueError):
        factory(value)


@pytest.mark.parametrize("value", [True, "4", None])
def test_dimensions_reject_non_numeric_values(value):
    with pytest.raises(TypeError):
        cube(value)


@pytest.mark.parametrize("steps", [0, -2])
def test_stairs_need_at_least_one_step(steps):
    with pytest.raises(ValueError, match="steps"):
        stairs(steps=steps)


@pytest.mark.parametrize("steps", [True, 2.5, "3"])
def test_step_count_must_be_an_integer(steps):
    with pytest.raises(TypeError, match="steps"):
        stairs(steps=steps)


def test_custom_geometry_rejects_empty_or_malformed_faces():
    with pytest.raises(ValueError, match="at least three"):
        Face(((0, 0, 0), (1, 0, 0)))
    with pytest.raises(ValueError, match="three coordinates"):
        Face(((0, 0), (1, 0, 0), (0, 1, 0)))
    with pytest.raises(ValueError, match="shade"):
        Face(((0, 0, 0), (1, 0, 0), (0, 1, 0)), "unknown")
    with pytest.raises(ValueError, match="at least one"):
        Shape(())
    with pytest.raises(TypeError, match="Face"):
        Shape(("face",))
