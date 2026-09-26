from __future__ import annotations

import math

import pytest

from lector_placas.application.frame_sampler import TimeBasedFrameSampler
from lector_placas.domain.errors import ConfigurationError, InvalidEntityError


def run(sampler: TimeBasedFrameSampler, stamps: list[int]) -> list[int]:
    return [t for t in stamps if sampler.should_process(t)]


def test_constant_30fps_video_sampled_at_10fps() -> None:
    stamps = [round(i * 1000 / 30) for i in range(31)]
    assert run(TimeBasedFrameSampler(10), stamps) == [
        0,
        100,
        200,
        300,
        400,
        500,
        600,
        700,
        800,
        900,
        1000,
    ]


def test_tolerance_accepts_99ms_at_10fps() -> None:
    assert run(TimeBasedFrameSampler(10), [0, 33, 66, 99, 133, 199]) == [0, 99, 199]


def test_variable_frame_rate() -> None:
    assert run(TimeBasedFrameSampler(10), [0, 150, 151, 260, 262, 400]) == [0, 150, 260, 400]


def test_high_target_processes_everything() -> None:
    stamps = [0, 40, 80, 120]
    assert run(TimeBasedFrameSampler(60), stamps) == stamps


def test_backwards_jump_is_processed() -> None:
    assert run(TimeBasedFrameSampler(10), [0, 500, 100, 150, 250]) == [0, 500, 100, 250]


def test_reset() -> None:
    sampler = TimeBasedFrameSampler(1)
    assert sampler.should_process(0)
    assert not sampler.should_process(10)
    sampler.reset()
    assert sampler.should_process(10)


@pytest.mark.parametrize("fps", [0, -5, math.inf, math.nan])
def test_invalid_fps(fps: float) -> None:
    with pytest.raises(ConfigurationError):
        TimeBasedFrameSampler(fps)


def test_negative_timestamp() -> None:
    with pytest.raises(InvalidEntityError):
        TimeBasedFrameSampler(10).should_process(-1)
