from fractions import Fraction

import pytest

from tilix import Face, Shape, block, cube, ramp, stairs


@pytest.mark.parametrize("factory", [cube, block, ramp, stairs])
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
