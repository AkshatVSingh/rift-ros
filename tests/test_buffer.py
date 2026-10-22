from rift_ros.buffer import RollingEventBuffer
from rift_ros.models import Event

def test_buffer_expires_old_events():
    b = RollingEventBuffer(10)
    b.append(Event(0, "x", "a", "old")); b.append(Event(11, "x", "b", "new"))
    assert [e.source for e in b.snapshot()] == ["b"]

def test_buffer_keeps_boundary():
    b = RollingEventBuffer(10); b.append(Event(1, "x", "a", "x")); b.append(Event(11, "x", "b", "y"))
    assert len(b) == 2

def test_bad_window():
    import pytest
    with pytest.raises(ValueError): RollingEventBuffer(0)
