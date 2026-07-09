"""Tests for TagTracker new/lost detection."""

from fi50x import TagTracker


def test_new_and_lost_with_zero_tolerance():
    t = TagTracker(miss_tolerance=0)

    d = t.update(["A", "B"])
    assert d.new == ["A", "B"]
    assert d.lost == []
    assert d.present == ["A", "B"]

    d = t.update(["B", "C"])
    assert d.new == ["C"]
    assert d.lost == ["A"]
    assert d.present == ["B", "C"]


def test_miss_tolerance_debounces_lost():
    t = TagTracker(miss_tolerance=1)
    t.update(["A"])

    d = t.update([])          # missed once; tolerance 1 -> still present
    assert d.lost == []
    assert d.present == ["A"]

    d = t.update([])          # missed twice -> lost
    assert d.lost == ["A"]
    assert d.present == []


def test_reappear_within_tolerance_is_not_new():
    t = TagTracker(miss_tolerance=2)
    t.update(["A"])
    t.update([])              # miss 1 (within tolerance)

    d = t.update(["A"])       # reappears before being declared lost
    assert d.new == []
    assert d.present == ["A"]


def test_has_changes_flag():
    t = TagTracker(miss_tolerance=0)
    assert t.update(["A"]).has_changes() is True
    assert t.update(["A"]).has_changes() is False


def test_reset():
    t = TagTracker(miss_tolerance=0)
    t.update(["A", "B"])
    t.reset()
    d = t.update(["A"])       # after reset, A looks new again
    assert d.new == ["A"]


def test_negative_tolerance_rejected():
    import pytest

    with pytest.raises(ValueError):
        TagTracker(miss_tolerance=-1)
