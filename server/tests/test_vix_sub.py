"""The VIX sub-lines (2026-10-23): quiet and heavy inside normal at the median,
panic inside stressed, the notes that name them, and the VIX against its own
month — words only, the four scoring bands untouched."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from newsterminal import scanscore, volterm

NOW = datetime(2026, 10, 23, 14, 30, tzinfo=UTC)


def _q(key: str, last: float, pct: float = 0.0) -> dict[str, Any]:
    return {"key": key, "last": last, "pct": pct, "chg": 0.0}


@pytest.mark.parametrize(
    ("last", "band", "sub"),
    [(15.0, "normal", "quiet"), (17.99, "normal", "quiet"), (18.0, "normal", "heavy"),
     (19.9, "normal", "heavy"), (12.0, "grind", None), (24.0, "elevated", None),
     (30.0, "stressed", None), (35.0, "stressed", "panic"), (42.0, "stressed", "panic"),
     (None, "normal", None), (18.0, None, None)],
)
def test_vix_sub(last: float | None, band: str | None, sub: str | None) -> None:
    assert scanscore.vix_sub(last, band) == sub


def _regime(vix: float, closes: list[float] | None = None) -> dict[str, Any]:
    quotes = [_q("VIX", vix), _q("VIX3M", vix + 2.0)]
    ctx = [{"key": "VIX", "closes": closes}] if closes is not None else []
    return scanscore.regime(quotes, {"SPY": None, "QQQ": None, "IWM": None}, [], "rth", NOW,
                            context=ctx)


def test_regime_carries_the_sub_and_the_band_is_unchanged() -> None:
    heavy = _regime(18.2)
    assert heavy["band"] == "normal" and heavy["sub"] == "heavy"
    assert heavy["notes"][0] == (
        "VIX 18.2 is in the normal band, over the median of 18: moves carry, breaks run to the "
        "next level and trends hold into the close, 1%-plus days are normal — the best tape for "
        "break-and-retest: full size, stops one notch wider, let winners reach target.")
    quiet = _regime(15.0)
    assert quiet["band"] == "normal" and quiet["sub"] == "quiet"
    assert "under the median of 18: moves fade inside the day" in quiet["notes"][0]
    panic = _regime(36.0)
    assert panic["band"] == "stressed" and panic["sub"] == "panic"
    assert panic["notes"][0].startswith("VIX 36.0 is in panic territory (35 and up)")
    assert _regime(30.0)["sub"] is None and "cut size hard" in _regime(30.0)["notes"][0]


def test_vix_month_percentile_from_finished_closes() -> None:
    closes = [float(x) for x in range(13, 34)] + [99.0]  # 21 finished + today's forming
    m = volterm.vix_month([{"key": "VIX", "closes": closes}], [_q("VIX", 18.0)])
    assert m is not None
    # The twenty finished closes are 14..33; 18 sits above five of them.
    assert m["days"] == 20 and m["lo"] == 14.0 and m["hi"] == 33.0
    assert m["pctile"] == 25
    assert volterm.vix_month([{"key": "VIX", "closes": [10.0, 11.0]}], [_q("VIX", 18.0)]) is None
    assert volterm.vix_month([], [_q("VIX", 18.0)]) is None


def test_regime_prints_the_month_line() -> None:
    r = _regime(18.2, closes=[float(x) for x in range(13, 34)] + [18.2])
    assert r["vix"]["month"] == {"pctile": 25, "lo": 14.0, "hi": 33.0, "days": 20}
    assert r["notes"][1] == ("Against its own month VIX 18.2 sits at the 25th percentile "
                             "(14.0–33.0).")
