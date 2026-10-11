"""The live recognizer must never turn a torso lean into a control input."""

import pytest
from test_motion_recognizer import Player


@pytest.mark.parametrize("lean", [-0.05, 0.05])
@pytest.mark.parametrize("scale", [0.5, 1.0, 1.8])
def test_lean_is_disabled_for_every_body_scale(lean, scale):
    player = Player(scale=scale)
    player.motion(0.3, {"lean": 0.0}, {"lean": lean})
    player.hold(0.5, lean=lean)
    player.motion(0.3, {"lean": lean}, {"lean": 0.0})
    assert player.events == []
