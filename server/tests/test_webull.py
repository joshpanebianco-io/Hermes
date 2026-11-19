"""
Webull's OpenAPI as the live-price feed beside Yahoo's (owner, 2026-11-18: "what about if i
have a webull account?", then "make sure our current implementation is kept as a fallback
so it's easy to revert and switch between"). The signing follows Webull's own Python SDK
(3.0.4); the first live session that day answered every signed call, and the feed carried
about 65 trades a second for AAPL, NVDA and SPY, each about 0.4 s after the trade.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import time
import urllib.parse
from datetime import UTC, datetime
from typing import Any

from newsterminal.sources import stream
from newsterminal.sources import webull as wb

NOW = datetime(2026, 11, 18, 15, 40, 0, tzinfo=UTC)


def test_the_signed_string_and_signature_follow_the_sdk() -> None:
    h = wb.sign("/market-data/stocks/snapshots/list",
                {"symbols": "AAPL,NVDA", "category": "US_STOCK"}, None,
                key="K", secret="S", host="api.webull.com.au", now=NOW, nonce="n1")
    assert h["x-timestamp"] == "2026-11-18T15:40:00Z" and h["x-version"] == "v3"
    assert h["x-signature-algorithm"] == "HMAC-SHA256" and h["x-signature-version"] == "1.0"
    # By hand: the path, then every signed header and query parameter sorted by name.
    plain = ("/market-data/stocks/snapshots/list&category=US_STOCK&host=api.webull.com.au"
             "&symbols=AAPL,NVDA&x-app-key=K&x-signature-algorithm=HMAC-SHA256"
             "&x-signature-nonce=n1&x-signature-version=1.0&x-timestamp=2026-11-18T15:40:00Z")
    text = urllib.parse.quote(plain, safe="")
    want = base64.b64encode(hmac.new(b"S&", text.encode(), hashlib.sha256).digest()).decode()
    assert h["x-signature"] == want


def test_a_body_is_signed_by_its_upper_case_sha256() -> None:
    body = wb.body_text({"symbols": ["AAPL"], "count": "5"})
    assert body == '{"symbols":["AAPL"],"count":"5"}'
    s = wb.string_to_sign("/x", {"host": "h"}, None, body)
    tail = hashlib.sha256(body.encode()).hexdigest().upper()
    assert urllib.parse.unquote(s) == f"/x&host=h&{tail}"
    # A query parameter with a signed header's name joins it, as the SDK does.
    assert urllib.parse.unquote(wb.string_to_sign("/x", {"host": "h"}, {"host": "q"}, None)) \
        == "/x&host=h&q"


def _field(n: int, s: bytes) -> bytes:
    return bytes([(n << 3) | 2, len(s)]) + s


def _tick(sym: str, price: str, at_ms: int, session: str = "RTH") -> bytes:
    basic = _field(1, sym.encode()) + _field(2, b"913257561") + _field(4, session.encode())
    return (_field(1, basic) + _field(2, str(at_ms).encode()) + _field(3, price.encode())
            + _field(4, b"100") + _field(5, b"B"))


def test_a_tick_message_decodes_to_a_trade() -> None:
    at = int(NOW.timestamp() * 1000) + 41
    t = wb.parse_tick(_tick("NVDA", "151.76", at))
    assert t is not None
    assert (t["sym"], t["price"], t["volume"], t["side"], t["session"]) == \
        ("NVDA", 151.76, 100.0, "B", "RTH")
    assert abs(t["at"] - NOW.timestamp() - 0.041) < 1e-6
    assert wb.parse_tick(_field(3, b"1.0")) is None   # no symbol, no trade
    assert wb.token_status(wb.Reply(200, {"status": "PENDING"})) == "PENDING"
    assert wb.token_status(wb.Reply(200, {"status": 1})) == "NORMAL"


def test_mqtt_packets_are_framed_whole_or_left_for_the_next_read() -> None:
    c = wb.mqtt_connect("sess", "key", "pw", 30)
    assert c[0] == 0x10 and b"MQTT" in c and c.endswith(b"\x00\x02pw")
    pub = bytes([0x32]) + wb._mqtt_len(2 + 4 + 2 + 3) + b"\x00\x04tick" + b"\x00\x07" + b"abc"
    buf = bytearray(b"\x20\x02\x00\x00" + pub[:5])
    got = wb.mqtt_packets(buf)
    assert [(k, b) for k, _f, b in got] == [(2, b"\x00\x00")] and bytes(buf) == pub[:5]
    buf.extend(pub[5:])
    (kind, flags, body), = wb.mqtt_packets(buf)
    assert kind == 3 and not buf
    assert wb.mqtt_publish(flags, body) == ("tick", b"abc", 7)
    assert wb.mqtt_puback(7) == b"\x40\x02\x00\x07"


def test_the_feed_switch_reads_the_app_then_the_env_then_the_keys(tmp_path: Any,
                                                                  monkeypatch: Any) -> None:
    path = str(tmp_path / "feed.json")
    monkeypatch.delenv("NT_PRICE_FEED", raising=False)
    monkeypatch.setenv("WEBULL_APP_KEY", "k")
    monkeypatch.setenv("WEBULL_APP_SECRET", "s")
    assert wb.feed_mode(path) == ("webull", "the default with Webull keys set")
    monkeypatch.setenv("NT_PRICE_FEED", "yahoo")
    assert wb.feed_mode(path)[0] == "yahoo"
    wb.set_feed_mode("webull", path)
    assert wb.feed_mode(path) == ("webull", "chosen in Settings")
    wb.set_feed_mode(None, path)
    assert wb.feed_mode(path)[0] == "yahoo"
    monkeypatch.delenv("NT_PRICE_FEED")
    monkeypatch.delenv("WEBULL_APP_KEY")
    assert wb.feed_mode(path) == ("yahoo", "the default without Webull keys")


def test_both_feeds_fill_one_book_and_the_newest_trade_wins() -> None:
    ps = stream.PriceStream()
    at = datetime(2026, 11, 18, 15, 40, tzinfo=UTC).timestamp()   # 10:40 ET, a session
    ps.put("NVDA", 151.76, at, src="webull")
    # Yahoo's copy of an older trade, arriving late, does not replace it.
    ps.put("NVDA", 150.00, at - 120, src="yahoo")
    assert ps.last_trade("NVDA") == (151.76, at)
    q = ps.quote("NVDA")
    assert q is not None and q["feed"] == "webull" and q["session"] == "rth"
    ps.put("NVDA", 151.90, at + 1, src="yahoo")
    assert ps.last_trade("NVDA") == (151.90, at + 1)
    ps.put("NVDA", 0.0, at + 2, src="webull")        # not a trade
    assert ps.last_trade("NVDA") == (151.90, at + 1)


def test_the_feed_puts_each_tick_into_the_books() -> None:
    got: list[tuple[Any, ...]] = []
    feed = wb.WebullFeed(lambda *a, **k: got.append((*a, k["src"])), lambda: ["NVDA"])
    at_ms = int(time.time() * 1000)
    assert feed.take(_tick("NVDA", "151.76", at_ms)) == "NVDA"
    assert got == [("NVDA", 151.76, at_ms / 1000.0, "webull")]
    assert feed.ticks == 1 and feed.take(b"\xff") is None


def test_a_refused_batch_is_split_so_one_bad_name_cannot_keep_the_rest_out(
        monkeypatch: Any) -> None:
    asked: list[list[str]] = []

    def fake(session_id: str, symbols: list[str], sub_types: list[str], **_: Any) -> wb.Reply:
        asked.append(list(symbols))
        return wb.Reply(400, None, "HTTP 400") if "BAD" in symbols else wb.Reply(200, None)

    monkeypatch.setattr(wb, "subscribe", fake)
    feed = wb.WebullFeed(lambda *a, **k: None, lambda: ["AAPL", "BAD", "NVDA", "SPY"])
    have, ok = asyncio.run(feed._sync("s", set(), None, ("k", "s")))
    assert have == {"AAPL", "NVDA", "SPY"} and not ok
    assert "BAD" in feed._refused and asked[0] == ["AAPL", "BAD", "NVDA", "SPY"]
    # Refused alone, it is not asked for again: the next sync is clean.
    have, ok = asyncio.run(feed._sync("s", have, None, ("k", "s")))
    assert ok and have == {"AAPL", "NVDA", "SPY"} and feed.subscribed == 3


def test_names_webull_says_it_does_not_know_are_set_aside_at_once(monkeypatch: Any) -> None:
    # As Webull answered on 18 Nov: the whole batch refused, the unknown names in brackets.
    asked: list[list[str]] = []

    def fake(session_id: str, symbols: list[str], sub_types: list[str], **_: Any) -> wb.Reply:
        asked.append(list(symbols))
        bad = [s for s in symbols if s in ("BRK.B", "BK")]
        if bad:
            return wb.Reply(417, {"error_code": "INVALID_SYMBOL", "status": 417,
                                  "message": f"The symbols does not exist in the category. "
                                             f"[{', '.join(bad)}]."}, "HTTP 417")
        return wb.Reply(200, None)

    monkeypatch.setattr(wb, "subscribe", fake)
    feed = wb.WebullFeed(lambda *a, **k: None, lambda: ["AAPL", "BRK.B", "BK", "NVDA"])
    have, ok = asyncio.run(feed._sync("s", set(), None, ("k", "s")))
    assert ok and have == {"AAPL", "NVDA"} and len(asked) == 2
    assert set(feed._refused) == {"BRK.B", "BK"}
    assert "not known to Webull" in " ".join(feed.status().notes or []) or not feed.connected


def test_another_session_taking_the_data_ends_the_connection() -> None:
    # As Webull said on 18 Nov, when a second session on the key subscribed: the first
    # hears this and no more trades, so it stops and takes the data back a minute later.
    feed = wb.WebullFeed(lambda *a, **k: None, lambda: [])
    assert wb.CONNECTIONS == 1
    feed._notice(0, b'{"drop":0,"rtt":112,"sent":792,"type":"1001"}')
    assert feed.slots()[0]["notice"]["sent"] == 792
    try:
        feed._notice(0, b'{"content":"Permission grabbed by other session, category : '
                        b'us-stock","type":"1002"}')
        raise AssertionError("a grab must end the session")
    except wb.Grabbed as e:
        assert "Permission grabbed" in str(e)


def test_each_connection_holds_its_own_hundred() -> None:
    names = [f"S{i}" for i in range(250)]
    feed = wb.WebullFeed(lambda *a, **k: None, lambda: names, connections=3)
    assert feed._slice(0) == names[:100] and feed._slice(1) == names[100:200]
    assert feed._slice(2) == names[200:250] and feed._slice(3) == []
    feed._refused["S0"] = time.time()
    assert feed._slice(0)[0] == "S1" and feed._slice(1)[0] == "S101"


# ---- the snapshots: the names past the live hundred (2026-11-19) -------------------------

def _et(*a: int) -> float:
    return datetime(*a, tzinfo=wb.ET).timestamp()  # type: ignore[misc]


#: AAPL's row as Webull answered at 18:55 ET on 18 Nov (after hours), the fields read.
AAPL_AH = {"symbol": "AAPL", "price": "353.7387", "close": "352.4500",
           "last_trade_time": 1795035601365, "extend_hour_last_price": "353.7387",
           "extend_hour_last_trade_time": 1795046101589}


def test_a_snapshot_row_gives_its_newest_trade_of_the_day() -> None:
    # After hours `price` is already the after-hours price, but `last_trade_time` is the
    # regular session's last (16:00:01); the after-hours trade's own time is the other.
    assert wb.snapshot_trade(AAPL_AH, _et(2026, 11, 18, 18, 55)) == \
        ("AAPL", 353.7387, 1795046101.589)
    # At 08:00 the next morning, before AAPL's first pre-market print, both pairs are
    # yesterday's: no trade of today's, so nothing for the books.
    assert wb.snapshot_trade(AAPL_AH, _et(2026, 11, 19, 8, 0)) is None
    # In the session the regular pair is the newer.
    rth = {"symbol": "NVDA", "price": "151.20",
           "last_trade_time": int(_et(2026, 11, 19, 10, 40) * 1000),
           "extend_hour_last_price": "150.10",
           "extend_hour_last_trade_time": int(_et(2026, 11, 19, 9, 29, 59) * 1000)}
    assert wb.snapshot_trade(rth, _et(2026, 11, 19, 10, 40, 5)) == \
        ("NVDA", 151.20, _et(2026, 11, 19, 10, 40))
    assert wb.snapshot_trade({"price": "1", "last_trade_time": 1}, 0.0) is None   # no symbol
    assert wb.snapshot_trade({**rth, "price": "0", "extend_hour_last_price": None},
                             _et(2026, 11, 19, 10, 40, 5)) is None


def _row(sym: str, at: float, price: float = 10.0) -> dict[str, Any]:
    return {"symbol": sym, "price": f"{price:.4f}", "last_trade_time": int(at * 1000)}


def _snap_feed(monkeypatch: Any, names: list[str], asked: list[list[str]],
               bad: tuple[str, ...] = ()) -> tuple[wb.WebullFeed, list[tuple[Any, ...]]]:
    monkeypatch.setenv("WEBULL_APP_KEY", "k")
    monkeypatch.setenv("WEBULL_APP_SECRET", "s")
    put: list[tuple[Any, ...]] = []

    def fake(symbols: list[str], **_: Any) -> wb.Reply:
        asked.append(list(symbols))
        unknown = [s for s in symbols if s in bad]
        if unknown:
            return wb.Reply(417, {"error_code": "INVALID_SYMBOL", "status": 417,
                                  "message": f"The symbols does not exist in the category. "
                                             f"[{', '.join(unknown)}]."}, "HTTP 417")
        return wb.Reply(200, [_row(s, _et(2026, 11, 18, 10, 39, 50)) for s in symbols])

    monkeypatch.setattr(wb, "snapshots", fake)
    feed = wb.WebullFeed(lambda *a, **k: put.append((*a, k["src"], k["recv"])), lambda: names)
    feed._token = lambda: ("tok", 0.0)  # type: ignore[method-assign]
    return feed, put


def test_snapshots_read_every_wanted_name_the_connection_does_not_hold(monkeypatch: Any) -> None:
    names = [f"S{i}" for i in range(250)]
    asked: list[list[str]] = []
    feed, put = _snap_feed(monkeypatch, names, asked)
    feed._held[0] = set(names[:100])
    now = _et(2026, 11, 18, 10, 40)
    # The first pass of the day reads the connection's hundred once as well, so a name
    # that has not traded since the connection began still has its last price.
    assert feed._snap_pass(now) == wb.SNAP_SEC
    assert asked == [names[:100], names[100:200], names[200:250]]
    assert len(put) == 250 and put[100] == ("S100", 10.0, _et(2026, 11, 18, 10, 39, 50),
                                            wb.SNAP_SRC, now)
    # After it, a hundred a call, the connection's hundred left out.
    asked.clear()
    assert feed._snap_pass(now + 10) == wb.SNAP_SEC
    assert asked == [names[100:200], names[200:250]]
    st = feed.snap_status(now + 10)
    assert (st["names"], st["booked"], st["calls"], st["error"]) == (150, 150, 2, None)
    assert feed.snap_of("S100") == (_et(2026, 11, 18, 10, 39, 50), 10.0, now + 10)
    # The next day the connection's names are read once again.
    assert feed.snap_names(_et(2026, 11, 19, 9, 0))[:100] == names[:100]
    # The connection down, the snapshots cover its hundred too.
    feed._held.clear()
    assert feed.snap_names(now + 10) == names


def test_a_name_webull_does_not_know_is_set_aside_and_the_rest_read_again(
        monkeypatch: Any) -> None:
    asked: list[list[str]] = []
    feed, put = _snap_feed(monkeypatch, ["AAPL", "BK", "NVDA"], asked, bad=("BK",))
    now = _et(2026, 11, 18, 10, 40)
    feed._snap_pass(now)
    assert asked == [["AAPL", "BK", "NVDA"], ["AAPL", "NVDA"]]
    assert [p[0] for p in put] == ["AAPL", "NVDA"] and "BK" in feed._refused
    assert feed.snap_names(now) == ["AAPL", "NVDA"]
    # Set aside for REFUSED_SEC, then asked about again.
    assert "BK" in feed.snap_names(now + wb.REFUSED_SEC + 1)


def test_snapshots_rest_while_the_market_is_shut(monkeypatch: Any) -> None:
    asked: list[list[str]] = []
    feed, put = _snap_feed(monkeypatch, ["AAPL"], asked)
    assert feed._snap_pass(_et(2026, 11, 21, 12, 0)) == wb.SNAP_IDLE_SEC   # a Saturday
    assert feed._snap_pass(_et(2026, 11, 19, 2, 0)) == wb.SNAP_IDLE_SEC    # overnight
    assert not asked and not put and feed.snap_status()["idle"]


def test_a_long_list_waits_its_share_of_the_budget(monkeypatch: Any) -> None:
    names = [f"S{i}" for i in range(700)]
    asked: list[list[str]] = []
    feed, _put = _snap_feed(monkeypatch, names, asked)
    # Seven calls at 30 a minute: 14 s, not 10, in the session...
    assert feed._snap_pass(_et(2026, 11, 18, 10, 40)) == 14.0 and len(asked) == 7
    # ...and the extended hours' own 20 s when that is longer.
    assert feed._snap_pass(_et(2026, 11, 18, 8, 0)) == wb.SNAP_EXT_SEC


def test_a_lapsed_token_is_asked_for_once_for_every_thread(monkeypatch: Any) -> None:
    # The connection and the snapshots both need it; each new ask prompts the owner's phone.
    asks: list[int] = []
    monkeypatch.setattr(wb, "token_needed", lambda: True)
    monkeypatch.setattr(wb, "load_token", lambda: None)
    monkeypatch.setattr(wb, "token_step", lambda: (asks.append(1), (None, "token INVALID"))[1])
    feed = wb.WebullFeed(lambda *a, **k: None, lambda: [])
    tok, wait = feed._token()
    assert tok is None and wait == wb.TOKEN_RETRY_SEC and len(asks) == 1
    tok, wait = feed._token()
    assert tok is None and 0 < wait < wb.TOKEN_RETRY_SEC + 1 and len(asks) == 1


def test_the_connection_names_it_holds_for_the_snapshots(monkeypatch: Any) -> None:
    monkeypatch.setattr(wb, "subscribe", lambda *a, **k: wb.Reply(200, None))
    feed = wb.WebullFeed(lambda *a, **k: None, lambda: ["AAPL", "NVDA", "SPY"])
    have, ok = asyncio.run(feed._sync("s", set(), None, ("k", "s")))
    assert ok and feed.held() == have == {"AAPL", "NVDA", "SPY"}
    # Held but not yet read today: one snapshot each first, then none.
    assert feed.snap_names() == ["AAPL", "NVDA", "SPY"]
    feed._snap_read.update(dict.fromkeys(have, datetime.fromtimestamp(time.time(), wb.ET).date()))
    assert feed.snap_names() == []
