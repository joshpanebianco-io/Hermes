"""
Webull's OpenAPI, from the owner's own Webull account (Australia).

WHY (owner, 2026-11-18: "to get proper real time stock data feeds, will i have to pay for
a provider?", then "what about if i have a webull account?"). Every price here was
Yahoo's, unofficial and unpaid: its stream ran 80 to 440 seconds late for half an hour on
12 Nov (stream.py), and its screener is fifteen minutes behind until 09:45. Webull's API
is official, comes with the account, and lists Nasdaq Basic Level 1 as free for OpenAPI
use: last sale and quote from Nasdaq's exchanges and its trade reporting facility, from
04:00 ET, which is not every venue's volume but is the market's price.

WHAT IS HERE, AS WEBULL'S OWN PYTHON SDK DOES IT (webull-openapi-python-sdk 3.0.4, read
2026-11-18; not a dependency: it pins cryptography<42, protobuf<5 and grpcio<1.60, and
this service needs none of them for a few calls):

  - Signing. Every request carries x-app-key, x-timestamp (UTC, seconds), x-signature-
    algorithm HMAC-SHA256, x-signature-version 1.0 and a random x-signature-nonce, plus
    x-version v3. The signed string is the path, then "&" and every signed header (lower
    case, with `host`) and query parameter as name=value sorted by name and joined by "&",
    then "&" and the upper-case hex SHA-256 of the body when there is one; the whole
    URL-encoded with nothing safe. The signature is base64 HMAC-SHA256 of it under the
    secret plus "&" (`string_to_sign`, `sign`).
  - The token. GET /openapi/config says whether the account needs one. If it does, POST
    /auth/tokens/create answers PENDING and Webull asks the owner to approve in the
    Webull app (an SMS code the first time); /auth/tokens/check reads NORMAL once they
    have, and the token rides every call as x-access-token. Unused for 15 days it lapses
    (INVALID); unapproved for 5 minutes it is EXPIRED. Kept in cache/ (git-ignored).
  - Snapshots: GET /market-data/stocks/snapshots/list, 1 to 100 symbols a call (measured
    2026-11-19; one unknown name refuses the call, as with a subscribe). Funds answer under
    US_STOCK too (SPY, XLK, SMH). Every number is a string; the two times are epoch ms.
  - Bars: POST /market-data/stocks/bars/list, a batch of symbols, M1/M5..., up to 1200.
  - The stream: MQTT 3.1.1 over TLS (wss://data-api.webull.com.au:8883/mqtt here, the
    `websockets` package the Yahoo stream already uses). Client id = a session id,
    username = the app key, password anything. Nothing is subscribed over MQTT itself:
    after CONNACK, POST /market-data/streaming/subscribe names the session id, the
    symbols, the category and the sub types (SNAPSHOT, TICK, QUOTE), and the server
    pushes to topics "snapshot", "tick", "quote" (protobuf), "notice" (JSON) and "echo".
    At most 5 connections a key; subscriptions do not survive a reconnect.

Every protobuf field these messages carry is a string (message.proto in the SDK, decoded
as data): Basic {1 symbol, 2 instrument_id, 3 timestamp, 4 trading_session}; Tick {1 basic,
2 time, 3 price, 4 volume, 5 side}; Snapshot {1 basic, 2 trade_time, 3 price, ... 12
ext_price ...}. So `decode` here reads strings and nested messages and nothing else.

NOTHING DEPENDS ON IT. No key, no token, a refusal: the app reads Yahoo as it did.
The key and secret come from the environment (.env.local) and are never logged.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import CACHE_DIR
from ..http import SourceStatus

try:
    import websockets
    from websockets.typing import Subprotocol
except ImportError:  # pragma: no cover — requirements.txt has it
    websockets = None  # type: ignore[assignment]

REGION = "au"
API_HOST = "api.webull.com.au"
MQTT_URL = "wss://data-api.webull.com.au:8883/mqtt"
API_VERSION = "v3"
SIGN_ALGORITHM = "HMAC-SHA256"
SIGN_VERSION = "1.0"
CATEGORY_STOCK = "US_STOCK"
CATEGORY_ETF = "US_ETF"
TOKEN_FILE = os.path.join(CACHE_DIR, "webull_token.json")
#: The client tag Webull's logs see: no name, no address, nothing of the owner's.
USER_AGENT = "hermes-terminal/1.0"


def credentials() -> tuple[str, str] | None:
    """(app key, app secret) from the environment, or None when either is missing."""
    key = (os.environ.get("WEBULL_APP_KEY") or "").strip()
    secret = (os.environ.get("WEBULL_APP_SECRET") or "").strip()
    return (key, secret) if key and secret else None


# ---- signing -----------------------------------------------------------------------------


def body_text(body: Any) -> str | None:
    """The body as sent and as signed: compact JSON, or None for no body. Pure."""
    if body is None:
        return None
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def string_to_sign(path: str, signed: dict[str, str], query: dict[str, Any] | None,
                   body: str | None) -> str:
    """The string Webull signs (the SDK's `_build_sign_string`). Pure.

    `signed` is the signed headers by lower-case name, `host` among them; a query
    parameter with a header's name joins it with "&", as the SDK does."""
    params = {k.lower(): str(v) for k, v in signed.items()}
    for k, v in (query or {}).items():
        params[k] = f"{params[k]}&{v}" if k in params else str(v)
    text = path + "&" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    if body is not None:
        text += "&" + hashlib.sha256(body.encode("utf-8")).hexdigest().upper()
    return urllib.parse.quote(text, safe="")


def signature(text: str, secret: str) -> str:
    """base64 HMAC-SHA256 of the signed string under the secret plus "&". Pure."""
    mac = hmac.new((secret + "&").encode("utf-8"), text.encode("utf-8"), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode("ascii").strip()


def sign(path: str, query: dict[str, Any] | None, body: str | None, *, key: str, secret: str,
         host: str = API_HOST, now: datetime | None = None,
         nonce: str | None = None) -> dict[str, str]:
    """Every header a request needs but the token and the content type. Pure given
    `now` and `nonce`."""
    signed = {
        "x-app-key": key,
        "x-timestamp": (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "x-signature-version": SIGN_VERSION,
        "x-signature-algorithm": SIGN_ALGORITHM,
        "x-signature-nonce": nonce or uuid.uuid4().hex,
    }
    text = string_to_sign(path, {**signed, "host": host}, query, body)
    return {**signed, "x-signature": signature(text, secret), "x-version": API_VERSION}


# ---- requests ------------------------------------------------------------------------------


class Reply:
    """One answer: the HTTP status (0 for no answer), the JSON (or None) and a short why."""

    def __init__(self, status: int, data: Any = None, error: str | None = None) -> None:
        self.status, self.data, self.error = status, data, error

    @property
    def ok(self) -> bool:
        return self.status == 200 and self.error is None

    def __repr__(self) -> str:
        return f"Reply({self.status}, error={self.error!r})"


def call(method: str, path: str, *, query: dict[str, Any] | None = None, body: Any = None,
         token: str | None = None, creds: tuple[str, str] | None = None,
         timeout: float = 12.0) -> Reply:
    """One signed request. Never raises; never logs the key, the secret or the token."""
    creds = creds or credentials()
    if creds is None:
        return Reply(0, error="no WEBULL_APP_KEY / WEBULL_APP_SECRET in .env.local")
    text = body_text(body)
    headers = sign(path, query, text, key=creds[0], secret=creds[1])
    headers["User-Agent"] = USER_AGENT
    headers["Accept"] = "application/json"
    if text is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["x-access-token"] = token
    url = f"https://{API_HOST}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, data=text.encode("utf-8") if text is not None else None,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return Reply(0, error=f"unreachable: {type(e).__name__}")
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        data = raw[:300].decode("utf-8", "replace")
    if status != 200:
        why = data.get("message") or data.get("msg") or data.get("error_code") \
            if isinstance(data, dict) else None
        return Reply(status, data, f"HTTP {status}" + (f": {why}" if why else ""))
    return Reply(status, data)


# ---- the token -----------------------------------------------------------------------------


def token_status(reply: Reply) -> str | None:
    """NORMAL / PENDING / INVALID / EXPIRED off a create or check answer, or None. Pure."""
    d = reply.data if isinstance(reply.data, dict) else {}
    s = d.get("status")
    if s is None:
        return None
    return {0: "PENDING", 1: "NORMAL"}.get(s, str(s)) if isinstance(s, int) else str(s)


def load_token(path: str = TOKEN_FILE) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
        return got if isinstance(got, dict) and got.get("token") else None
    except (OSError, ValueError):
        return None


def save_token(d: dict[str, Any], path: str = TOKEN_FILE) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: d.get(k) for k in ("token", "expires", "status")}, f)
    os.replace(tmp, path)


def token_needed(creds: tuple[str, str] | None = None) -> bool | None:
    """Whether this account must hold a token (GET /openapi/config), None unknown."""
    r = call("GET", "/openapi/config", creds=creds)
    if not r.ok or not isinstance(r.data, dict):
        return None
    return bool(r.data.get("token_check_enabled", False))


def token_step(creds: tuple[str, str] | None = None,
               path: str = TOKEN_FILE) -> tuple[str | None, str]:
    """One step toward a NORMAL token: (the token when NORMAL, else None; what to tell the
    owner). Create once (handing back the saved one, which the server keeps if it is still
    good), then check while it is PENDING. Never blocks."""
    held = load_token(path)
    if held and held.get("status") == "PENDING":
        r = call("POST", "/auth/tokens/check", body={"token": held["token"]}, creds=creds)
    else:
        body = {"token": held["token"]} if held else {}
        r = call("POST", "/auth/tokens/create", body=body, creds=creds)
    if not r.ok:
        return None, f"token request refused ({r.error})"
    status = token_status(r)
    d = r.data if isinstance(r.data, dict) else {}
    if d.get("token"):
        save_token({**d, "status": status}, path)
    if status == "NORMAL":
        return str(d.get("token")), "token approved"
    if status == "PENDING":
        return None, "approve the API sign-in in your Webull app (within 5 minutes)"
    return None, f"token {status or 'unknown'}: a new one will be asked for"


# ---- market data over HTTP -----------------------------------------------------------------


def snapshots(symbols: list[str], *, category: str = CATEGORY_STOCK, extended: bool = True,
              token: str | None = None, creds: tuple[str, str] | None = None) -> Reply:
    """GET /market-data/stocks/snapshots/list for many names at once."""
    q: dict[str, Any] = {"symbols": ",".join(symbols), "category": category}
    if extended:
        q["extend_hour_required"] = "true"
    return call("GET", "/market-data/stocks/snapshots/list", query=q, token=token, creds=creds)


def bars(symbols: list[str], *, timespan: str = "M5", count: int = 200,
         category: str = CATEGORY_STOCK, sessions: str | None = None,
         token: str | None = None, creds: tuple[str, str] | None = None) -> Reply:
    """POST /market-data/stocks/bars/list: the last `count` bars of each name."""
    body: dict[str, Any] = {"symbols": symbols, "category": category, "timespan": timespan,
                            "count": str(count)}
    if sessions:
        body["trading_sessions"] = sessions
    return call("POST", "/market-data/stocks/bars/list", body=body, token=token, creds=creds)


def subscribe(session_id: str, symbols: list[str], sub_types: list[str], *,
              category: str = CATEGORY_STOCK, token: str | None = None,
              creds: tuple[str, str] | None = None) -> Reply:
    body = {"session_id": session_id, "symbols": symbols, "category": category,
            "sub_types": sub_types}
    return call("POST", "/market-data/streaming/subscribe", body=body, token=token, creds=creds)


def unsubscribe(session_id: str, symbols: list[str], sub_types: list[str], *,
                category: str = CATEGORY_STOCK, token: str | None = None,
                creds: tuple[str, str] | None = None) -> Reply:
    body = {"session_id": session_id, "symbols": symbols, "category": category,
            "sub_types": sub_types}
    return call("POST", "/market-data/streaming/unsubscribe", body=body, token=token,
                creds=creds)


def invalid_symbols(reply: Reply) -> list[str]:
    """The names a refused subscribe says Webull does not know. Pure. Seen 2026-11-18:
    417 {"error_code": "INVALID_SYMBOL", "message": "The symbols does not exist in the
    category. [BRK.B, BK]."}: one unknown name refuses the whole batch."""
    d = reply.data if isinstance(reply.data, dict) else {}
    if d.get("error_code") != "INVALID_SYMBOL":
        return []
    m = re.search(r"\[([^\]]*)\]", str(d.get("message") or ""))
    return [s.strip() for s in m.group(1).split(",") if s.strip()] if m else []


ET = ZoneInfo("America/New_York")


def snapshot_trade(row: Any, now: float) -> tuple[str, float, float] | None:
    """One snapshot row → (symbol, price, trade time) of the newest trade it reports, or
    None when it reports none from `now`'s day (ET). Pure.

    TWO TRADES A ROW, PAIRED BY TIME (read 2026-11-19, 18:55 ET, after hours): `price` is the
    newest price, the extended hours' included, but `last_trade_time` is the regular
    session's last (16:00:00.801 on NVDA); the after-hours trade's own time is
    `extend_hour_last_trade_time`, beside `extend_hour_last_price`. So the two pairs are
    (extend_hour_last_price, extend_hour_last_trade_time) and (price, last_trade_time), and
    the newer wins: the extended pair after the bell and before the open, the regular pair
    in the session. A pair from another day is no trade of today's: before a name's first
    pre-market print both still hold yesterday's, and the books must not take those for
    this morning's."""
    if not isinstance(row, dict) or not row.get("symbol"):
        return None
    best: tuple[float, float] | None = None
    for px_key, at_key in (("extend_hour_last_price", "extend_hour_last_trade_time"),
                           ("price", "last_trade_time")):
        px, at = _num(row.get(px_key)), _epoch(row.get(at_key))
        if px is None or not px > 0 or at is None or at > now + 60.0:
            continue
        if best is None or at > best[1]:
            best = (px, at)
    if best is None:
        return None
    if datetime.fromtimestamp(best[1], ET).date() != datetime.fromtimestamp(now, ET).date():
        return None
    return str(row["symbol"]), best[0], best[1]


# ---- which feed --------------------------------------------------------------------------

FEED_FILE = os.path.join(CACHE_DIR, "price_feed.json")
FEEDS = ("webull", "yahoo")


def feed_mode(path: str = FEED_FILE) -> tuple[str, str]:
    """(the live-price feed, why): "webull" runs Webull's trades beside Yahoo's stream
    (newest wins), "yahoo" is the app as it was before Webull, Yahoo alone.

    THE SWITCH (owner, 2026-11-18: "make sure our current implementation is kept as a
    fallback so it's easy to revert and switch between"). In order: the choice made in
    the app (POST /api/feed, kept in cache/price_feed.json), then NT_PRICE_FEED in
    .env.local, then Webull when its keys are set and Yahoo when they are not."""
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f).get("feed")
        if got in FEEDS:
            return str(got), "chosen in Settings"
    except (OSError, ValueError, AttributeError):
        pass
    env = (os.environ.get("NT_PRICE_FEED") or "").strip().lower()
    if env in FEEDS:
        return env, "set by NT_PRICE_FEED in .env.local"
    if credentials():
        return "webull", "the default with Webull keys set"
    return "yahoo", "the default without Webull keys"


def set_feed_mode(feed: str | None, path: str = FEED_FILE) -> None:
    """Keep the app's choice, or clear it (None) to fall back to .env.local's."""
    if feed is None:
        with contextlib.suppress(OSError):
            os.remove(path)
        return
    if feed not in FEEDS:
        raise ValueError(f"feed must be one of {FEEDS}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"feed": feed}, f)


# ---- the stream's wire ---------------------------------------------------------------------


def _varint(b: bytes, i: int) -> tuple[int, int]:
    shift = v = 0
    while True:
        c = b[i]
        i += 1
        v |= (c & 0x7F) << shift
        if not c & 0x80:
            return v, i
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def decode(b: bytes, nested: frozenset[int] = frozenset({1})) -> dict[int, Any]:
    """A protobuf message whose fields are strings, with `nested` fields read as messages
    of the same kind → {field: value}. Repeated fields keep their first. Pure; raises on
    bad bytes."""
    out: dict[int, Any] = {}
    i = 0
    while i < len(b):
        key, i = _varint(b, i)
        field, wire = key >> 3, key & 7
        if wire == 2:
            n, i = _varint(b, i)
            chunk = b[i:i + n]
            i += n
            if field in out:
                continue
            out[field] = decode(chunk, frozenset()) if field in nested else \
                chunk.decode("utf-8", "replace")
        elif wire == 0:
            v, i = _varint(b, i)
            out.setdefault(field, v)
        elif wire == 1:
            i += 8
        elif wire == 5:
            i += 4
        else:
            raise ValueError(f"wire type {wire}")
    return out


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _epoch(v: Any) -> float | None:
    """A Webull time (epoch milliseconds, as a string) → epoch seconds."""
    x = _num(v)
    if x is None or x <= 0:
        return None
    return x / 1000.0 if x > 1e11 else x


def _basic(m: dict[int, Any]) -> dict[int, Any]:
    got = m.get(1)
    return got if isinstance(got, dict) else {}


def parse_tick(payload: bytes) -> dict[str, Any] | None:
    """A "tick" message → {sym, price, at, volume, side, session}, or None. Pure."""
    m = decode(payload)
    basic = _basic(m)
    sym, price = basic.get(1), _num(m.get(3))
    at = _epoch(m.get(2)) or _epoch(basic.get(3))
    if not sym or price is None or at is None:
        return None
    return {"sym": str(sym), "price": price, "at": at, "volume": _num(m.get(4)),
            "side": m.get(5), "session": basic.get(4)}


def parse_snapshot(payload: bytes) -> dict[str, Any] | None:
    """A "snapshot" message → {sym, price, at, ext_price, ext_at, session}, or None. Pure."""
    m = decode(payload)
    basic = _basic(m)
    sym = basic.get(1)
    if not sym:
        return None
    return {"sym": str(sym), "price": _num(m.get(3)), "at": _epoch(m.get(2)),
            "ext_price": _num(m.get(12)), "ext_at": _epoch(m.get(11)),
            "volume": _num(m.get(8)), "session": basic.get(4)}


# MQTT 3.1.1, the four packets a subscriber needs. A broker's PUBLISH can come at QoS 1,
# which is answered with a PUBACK.

def _mqtt_str(s: str) -> bytes:
    b = s.encode("utf-8")
    return len(b).to_bytes(2, "big") + b


def _mqtt_len(n: int) -> bytes:
    out = bytearray()
    while True:
        byte, n = n % 128, n // 128
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def mqtt_connect(client_id: str, username: str, password: str, keepalive: int = 30) -> bytes:
    """A CONNECT packet: clean session, a user name and a password. Pure."""
    var = _mqtt_str("MQTT") + bytes([4, 0xC2]) + keepalive.to_bytes(2, "big")
    payload = _mqtt_str(client_id) + _mqtt_str(username) + _mqtt_str(password)
    return bytes([0x10]) + _mqtt_len(len(var) + len(payload)) + var + payload


PINGREQ = bytes([0xC0, 0x00])


def mqtt_packets(buf: bytearray) -> list[tuple[int, int, bytes]]:
    """Every whole packet at the front of `buf` → [(type, flags, body)], taken out of it;
    a part packet is left for the next read. Pure but for `buf`."""
    out: list[tuple[int, int, bytes]] = []
    while len(buf) >= 2:
        n = shift = 0
        i = 1
        while True:
            if i >= len(buf):
                return out
            c = buf[i]
            n |= (c & 0x7F) << shift
            i += 1
            if not c & 0x80:
                break
            shift += 7
            if shift > 21:
                raise ValueError("bad remaining length")
        if len(buf) < i + n:
            return out
        out.append((buf[0] >> 4, buf[0] & 0x0F, bytes(buf[i:i + n])))
        del buf[:i + n]
    return out


def mqtt_publish(flags: int, body: bytes) -> tuple[str, bytes, int | None]:
    """A PUBLISH body → (topic, payload, the packet id to acknowledge or None). Pure."""
    n = int.from_bytes(body[:2], "big")
    topic = body[2:2 + n].decode("utf-8", "replace")
    i = 2 + n
    pid = None
    if (flags >> 1) & 3:
        pid = int.from_bytes(body[i:i + 2], "big")
        i += 2
    return topic, body[i:], pid


def mqtt_puback(pid: int) -> bytes:
    return bytes([0x40, 0x02]) + pid.to_bytes(2, "big")


class Grabbed(Exception):
    """Another session on the key took the US-stock data (notice 1002)."""


#: CONNACK's refusals, as Webull's docs number them.
CONNACK_WHY = {1: "bad protocol version", 2: "invalid client id", 3: "empty app key",
               100: "unknown", 101: "internal error", 102: "already authenticated",
               103: "authentication failed", 104: "invalid app key",
               105: "five connections already open on this key"}


# ---- the feed ------------------------------------------------------------------------------

#: Names a subscribe call carries.
SUB_CHUNK = 50
#: THE MOST ONE CONNECTION HOLDS IS 100 (measured 2026-11-18: the third batch of fifty on
#: one connection came back 417 "Maximum number of subscribe tickers:100").
#:
#: AND ONLY ONE CONNECTION A KEY GETS THE DATA (the same day). A key may open five, but
#: the US-stock permission belongs to one session at a time: the newest to subscribe takes
#: it, and the others get a notice, {"type": "1002", "content": "Permission grabbed by
#: other session, category : us-stock"}, and no more trades. Three connections took it
#: from each other in turn, each going quiet and reconnecting, so the first names on the
#: list (SPY, QQQ, the Magnificent 7) sat on Yahoo's trades most of the time; a test
#: script on the same key took it from the app the same way. So: one connection, its 100
#: names the ones that matter most (collector._webull_wanted); the rest stay Yahoo's.
PER_CONNECTION = 100
CONNECTIONS = 1
#: Grabbed by another session (a second copy of the app, a test run): wait this long
#: before taking it back, so two sessions on one key do not trade it every few seconds.
GRABBED_WAIT_SEC = 60.0
#: How often the subscription is brought into line with what is wanted; after a refused
#: call, the wait before the next try (subscribe calls are 60 a minute a key).
SYNC_SEC = 5.0
SYNC_AFTER_REFUSAL_SEC = 60.0
#: A name Webull refused on its own is not asked for again for this long.
REFUSED_SEC = 3600.0
KEEPALIVE_SEC = 30
BACKOFF = (2.0, 5.0, 15.0, 30.0, 60.0, 120.0)
HEALTHY_SEC = 120.0
#: While a token waits for the owner's approval it is checked this often (a check sends
#: nothing to their phone); a token that lapsed is asked for again no sooner than this,
#: because every new ask does.
PENDING_CHECK_SEC = 10.0
TOKEN_RETRY_SEC = 300.0
#: A connection silent this long is dead, whatever it says: in the regular session (a
#: hundred names, the busiest first, never all quiet for this long), and in the extended
#: hours, when thin names can be.
QUIET_SEC = 45.0
QUIET_EXT_SEC = 180.0
LATE_SEC = 20.0

#: THE NAMES PAST THE LIVE HUNDRED, BY SNAPSHOT (owner, 2026-11-19: "do what you recommend").
#: One connection carries 100 names; the app watches about 330, and Yahoo's stream, which
#: has them, heard from 126 to 149 of ~335 in its best minute of recent sessions and ran 80
#: to 440 s late on a bad one. A snapshot is a plain request, not a session, so it takes
#: nothing from the connection (checked the same evening: the connection ran on through
#: it). Read for every wanted name the connection does not hold this moment, so a
#: connection that is down has the snapshots covering its hundred too.
SNAP_SRC = "webull_snap"
#: Names a snapshot call takes (2026-11-19: 101 came back 417 "symbols size must be between
#: 1 and 100").
SNAP_CHUNK = 100
#: A pass every this many seconds: in the regular session, and in the extended hours.
SNAP_SEC = 10.0
SNAP_EXT_SEC = 20.0
#: Of the key's 60 requests a minute (HTTP, the Australian portal), what the snapshots may
#: spend; the rest is the connection's subscribes and room for a retry. A pass of more calls
#: than this allows at SNAP_SEC waits longer.
SNAP_BUDGET_MIN = 30
#: Calls in one pass at most, the retries after an unknown name included.
SNAP_MAX_CALLS = 8
#: Closed (overnight, a weekend, a holiday): looked at again this often.
SNAP_IDLE_SEC = 60.0
#: After a 429, a refused token or no answer.
SNAP_BACKOFF_SEC = 60.0


class WebullFeed:
    """Webull's trades, pushed, into the app's live-price books (`put`, stream.PriceStream's)
    for the names the books want (`wanted`, the same list Yahoo's socket is given).

    Up to CONNECTIONS threads, each its own event loop and one MQTT connection over a
    websocket, each holding its slice of the wanted list (100 names). A dropped connection
    backs off and comes back and subscribes again from nothing (Webull keeps no
    subscription across one). Beside them one more thread reads snapshots of every wanted
    name no connection holds (`_snap_pass`), into the same books as SNAP_SRC. Started and
    stopped by the collector as the feed switch says (`feed_mode`); stopped, the app is
    Yahoo's alone, exactly as before."""

    def __init__(self, put: Callable[..., None], wanted: Callable[[], list[str]],
                 connections: int = CONNECTIONS, snapshots_on: bool = True) -> None:
        self.put = put
        self.wanted = wanted
        self.connections = connections
        self.snapshots_on = snapshots_on
        self._lock = threading.Lock()
        self._token_lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._connected: dict[int, float] = {}
        self._subs: dict[int, int] = {}
        self.error: str | None = None
        self.note: str | None = None
        self.last_tick = 0.0
        self.ticks = 0
        self._recent: deque[tuple[float, float]] = deque(maxlen=6000)
        self._refused: dict[str, float] = {}
        self._token_held: tuple[str | None, float] = (None, 0.0)
        self._by_sym: dict[str, tuple[float, float, float]] = {}
        #: Per connection: when it last heard a trade, how many, and Webull's last notice.
        self._slot_last: dict[int, float] = {}
        self._slot_ticks: dict[int, int] = {}
        self._slot_notice: dict[int, dict[str, Any]] = {}
        #: Per connection, the names it holds now (`held`): the snapshots read the rest.
        self._held: dict[int, set[str]] = {}
        #: A failed token ask, and when the next may be made, for every thread at once.
        self._token_retry_at = 0.0
        #: The snapshot pass: its last result, its calls in the last minute, each name's last.
        self._snap: dict[str, Any] = {"names": 0, "rows": 0, "booked": 0, "calls": 0,
                                      "every_sec": None, "at": 0.0, "error": None,
                                      "idle": False}
        self._snap_calls: deque[float] = deque(maxlen=200)
        self._snap_by_sym: dict[str, tuple[float, float, float]] = {}
        #: The ET day each name was last read by a snapshot (`snap_names`).
        self._snap_read: dict[str, Any] = {}

    def slots(self) -> list[dict[str, Any]]:
        """Each connection's health: names held, trades heard, seconds since the last, and
        Webull's own sent / drop counts."""
        now = time.time()
        with self._lock:
            return [{"slot": s + 1, "connected": s in self._connected,
                     "names": self._subs.get(s, 0), "trades": self._slot_ticks.get(s, 0),
                     "quiet_sec": round(now - self._slot_last[s], 1)
                     if s in self._slot_last else None,
                     "notice": self._slot_notice.get(s)} for s in range(self.connections)]

    @property
    def connected(self) -> bool:
        return bool(self._connected)

    @property
    def subscribed(self) -> int:
        return sum(self._subs.values())

    # ---- the threads ---------------------------------------------------------------------

    def running(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    def start(self) -> None:
        if websockets is None or self.running():
            return
        self._stop.clear()
        self._threads = [threading.Thread(target=self._run, args=(slot,), name=f"webull-{slot}",
                                          daemon=True) for slot in range(self.connections)]
        if self.snapshots_on:
            self._threads.append(threading.Thread(target=self._snap_run, name="webull-snap",
                                                  daemon=True))
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)
        with self._lock:
            self._connected.clear()
            self._subs.clear()
            self._held.clear()

    def _token(self) -> tuple[str | None, float]:
        """(a NORMAL token, or None and how long to wait before asking again). One ask at a
        time for every thread, a NORMAL answer kept ten minutes, and a failed ask holding
        every thread off until its wait is out: the connection and the snapshots both need
        the token, and each new ask after a lapse sends the owner's phone a prompt."""
        with self._token_lock:
            tok, at = self._token_held
            now = time.monotonic()
            if tok is not None and now - at < 600.0:
                return tok, 0.0
            if now < self._token_retry_at:
                return None, self._token_retry_at - now
            need = token_needed()
            if need is False:
                self._token_held = ("", time.monotonic())
                return "", 0.0
            got, msg = token_step()
            with self._lock:
                self.note = None if got else msg
            if got:
                self._token_held = (got, time.monotonic())
                return got, 0.0
            self._token_held = (None, 0.0)
            held = load_token()
            wait = PENDING_CHECK_SEC if held and held.get("status") == "PENDING" \
                else TOKEN_RETRY_SEC
            self._token_retry_at = time.monotonic() + wait
            return None, wait

    def _run(self, slot: int = 0) -> None:
        fails = 0
        while not self._stop.is_set():
            creds = credentials()
            if creds is None:
                with self._lock:
                    self.error = "no WEBULL_APP_KEY / WEBULL_APP_SECRET in .env.local"
                self._stop.wait(60.0)
                continue
            token, wait = self._token()
            if token is None:
                self._stop.wait(wait)
                continue
            started = time.monotonic()
            try:
                asyncio.run(self._session(creds, token or None, slot))
            except Grabbed as e:
                with self._lock:
                    self.error = (f"another Webull API session on this key took the data "
                                  f"({e}); taking it back in {GRABBED_WAIT_SEC:.0f}s")
                    self._connected.pop(slot, None)
                    self._subs.pop(slot, None)
                    self._held.pop(slot, None)
                self._stop.wait(GRABBED_WAIT_SEC)
                continue
            except Exception as e:  # noqa: BLE001 — a feed that fails must not take the thread
                with self._lock:
                    self.error = f"connection {slot + 1}: {e.__class__.__name__}: {e}"[:200]
                    # A refused token is asked about again, not reused for ten minutes.
                    if "401" in str(e) or "403" in str(e):
                        self._token_held = (None, 0.0)
            with self._lock:
                self._connected.pop(slot, None)
                self._subs.pop(slot, None)
                self._held.pop(slot, None)
            if self._stop.is_set():
                return
            fails = 0 if time.monotonic() - started >= HEALTHY_SEC else fails + 1
            self._stop.wait(BACKOFF[min(fails, len(BACKOFF) - 1)])

    # ---- the connection ------------------------------------------------------------------

    async def _session(self, creds: tuple[str, str], token: str | None, slot: int = 0) -> None:
        session_id = uuid.uuid4().hex
        async with websockets.connect(MQTT_URL, subprotocols=[Subprotocol("mqtt")],
                                      open_timeout=15, ping_interval=None,
                                      max_size=2 ** 22) as ws:
            await ws.send(mqtt_connect(session_id, creds[0], uuid.uuid4().hex, KEEPALIVE_SEC))
            buf = bytearray()
            await self._connack(ws, buf)
            now = time.time()
            with self._lock:
                self._connected[slot] = now
                self._slot_last[slot] = now
                if self.error and self.error.startswith(f"connection {slot + 1}:"):
                    self.error = None
            # THE READ LOOP DOES NOTHING BUT READ (2026-11-18, the first live session): it
            # waited on each message through asyncio.wait_for, a new task and timer per
            # message, with the subscription and the keep-alive in the same loop. The busiest
            # connection (SPY, QQQ, the Magnificent 7) fell behind and Webull stopped sending
            # to it inside ten seconds, while the two quieter ones ran on. The subscription,
            # the ping and the silence check now run beside it, in `_keep`.
            keeper = asyncio.create_task(self._keep(ws, session_id, token, creds, slot))
            try:
                async for raw in ws:
                    buf.extend(raw if isinstance(raw, bytes) else raw.encode())
                    for kind, flags, body in mqtt_packets(buf):
                        if kind != 3:
                            continue
                        topic, payload, pid = mqtt_publish(flags, body)
                        if pid is not None:
                            await ws.send(mqtt_puback(pid))
                        if topic == "tick":
                            self.take(payload, slot=slot)
                        elif topic == "notice":
                            self._notice(slot, payload)
                    if self._stop.is_set() or keeper.done():
                        break
            finally:
                keeper.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await keeper
            if keeper.done() and not keeper.cancelled() and keeper.exception() is not None:
                raise keeper.exception()  # type: ignore[misc]

    async def _keep(self, ws: Any, session_id: str, token: str | None,
                    creds: tuple[str, str], slot: int) -> None:
        """Beside the read loop: the subscription brought into line every SYNC_SEC, the MQTT
        ping, and the silence check. On any failure it closes the socket, which ends the
        read loop, and the failure is raised from the session."""
        have: set[str] = set()
        sync_at = 0.0
        pinged = time.monotonic()
        try:
            while not self._stop.is_set():
                t = time.monotonic()
                if t >= sync_at:
                    have, ok = await self._sync(session_id, have, token, creds, slot)
                    sync_at = t + (SYNC_SEC if ok else SYNC_AFTER_REFUSAL_SEC)
                if t - pinged >= KEEPALIVE_SEC / 2:
                    await ws.send(PINGREQ)
                    pinged = t
                self._quiet(have, slot)
                await asyncio.sleep(1.0)
        finally:
            with contextlib.suppress(Exception):
                await ws.close()

    async def _connack(self, ws: Any, buf: bytearray) -> None:
        end = time.monotonic() + 15.0
        while time.monotonic() < end:
            raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
            buf.extend(raw if isinstance(raw, bytes) else raw.encode())
            for kind, _flags, body in mqtt_packets(buf):
                if kind == 2:
                    rc = body[1] if len(body) > 1 else -1
                    if rc != 0:
                        raise ConnectionError(f"refused: {CONNACK_WHY.get(rc, rc)}")
                    return
        raise TimeoutError("no CONNACK")

    def _quiet(self, have: set[str], slot: int = 0) -> None:
        """THIS CONNECTION'S silence, not the feed's: it was read off the last trade of any
        connection, so one that stopped while the others ran was never found out."""
        from .stream import session_of_ts
        session = session_of_ts(time.time())
        if not have or session is None:
            return
        limit = QUIET_SEC if session == "rth" else QUIET_EXT_SEC
        with self._lock:
            heard = self._slot_last.get(slot, 0.0)
        if time.time() - heard > limit:
            raise TimeoutError(f"no trade for {limit:.0f}s on {len(have)} names "
                               "with a session on")

    def _notice(self, slot: int, payload: bytes) -> None:
        """Webull's own word on a connection: {"type": "1001", "sent": n, "drop": n, "rtt":
        ms}, "drop" being what its server threw away for this client being slow; or "1002",
        the data taken by another session on the key, which ends this one (`Grabbed`)."""
        try:
            d = json.loads(payload.decode("utf-8", "replace"))
        except ValueError:
            return
        if not isinstance(d, dict):
            return
        with self._lock:
            self._slot_notice[slot] = d
        if str(d.get("type")) == "1002":
            raise Grabbed(str(d.get("content") or "permission grabbed by another session"))

    def _slice(self, slot: int) -> list[str]:
        """This connection's names: its hundred of the wanted list, refused names left out."""
        now = time.time()
        with self._lock:
            self._refused = {s: t for s, t in self._refused.items() if now - t < REFUSED_SEC}
            refused = set(self._refused)
        want = [s for s in dict.fromkeys(self.wanted()) if s and s not in refused]
        return want[slot * PER_CONNECTION:(slot + 1) * PER_CONNECTION]

    async def _sync(self, session_id: str, have: set[str], token: str | None,
                    creds: tuple[str, str], slot: int = 0) -> tuple[set[str], bool]:
        """Bring this connection's subscription into line with its slice: (held now, no
        refusal). Names Webull says it does not know (417 INVALID_SYMBOL, named in the
        answer) are set aside for REFUSED_SEC and the rest asked for again at once; any
        other refusal splits the batch, so one bad name cannot keep fifty out."""
        now = time.time()
        want = self._slice(slot)
        add = [s for s in want if s not in have]
        drop = sorted(have - set(want))
        ok = True
        for i in range(0, len(drop), SUB_CHUNK):
            part = drop[i:i + SUB_CHUNK]
            r = await asyncio.to_thread(unsubscribe, session_id, part, ["TICK"], token=token,
                                        creds=creds)
            if r.ok:
                have = have - set(part)
        queue = [add[i:i + SUB_CHUNK] for i in range(0, len(add), SUB_CHUNK)]
        calls = 0
        while queue and calls < 12:
            part = queue.pop(0)
            calls += 1
            r = await asyncio.to_thread(subscribe, session_id, part, ["TICK"], token=token,
                                        creds=creds)
            if r.ok:
                have = have | set(part)
                continue
            bad = [s for s in invalid_symbols(r) if s in part]
            if bad:
                with self._lock:
                    for s in bad:
                        self._refused[s] = now
                rest = [s for s in part if s not in bad]
                if rest:
                    queue.insert(0, rest)
                continue
            ok = False
            with self._lock:
                self.error = f"subscribe refused: {r.error}"
            if r.status in (401, 403, 429) or r.status == 0 or "Maximum number" in (r.error or ""):
                break
            if len(part) == 1:
                with self._lock:
                    self._refused[part[0]] = now
            else:
                half = len(part) // 2
                queue[:0] = [part[:half], part[half:]]
        with self._lock:
            self._subs[slot] = len(have)
            self._held[slot] = set(have)
            if ok and self.error and self.error.startswith("subscribe refused"):
                self.error = None
        return have, ok

    # ---- what it hears -------------------------------------------------------------------

    def take(self, payload: bytes, recv: float | None = None, slot: int = 0) -> str | None:
        """One "tick" message into the books. Returns the symbol, or None."""
        try:
            t = parse_tick(payload)
        except (ValueError, IndexError):
            return None
        if t is None:
            return None
        got = time.time() if recv is None else recv
        self.put(t["sym"], t["price"], t["at"], src="webull", recv=got)
        with self._lock:
            self.ticks += 1
            self.last_tick = got
            self._slot_last[slot] = got
            self._slot_ticks[slot] = self._slot_ticks.get(slot, 0) + 1
            # Unclamped: a PC clock behind the exchange's makes this negative, and a backlog
            # in this process shows as the figure rising, whatever the clock.
            self._recent.append((got, got - t["at"]))
            self._by_sym[str(t["sym"])] = (float(t["at"]), float(t["price"]), got)
        return str(t["sym"])

    def last_of(self, sym: str) -> tuple[float, float, float] | None:
        """(trade time, price, received) of the name's latest Webull trade, or None."""
        with self._lock:
            return self._by_sym.get(sym)

    def pace(self, now: float | None = None) -> tuple[int, float | None]:
        """(trades heard in the last minute, the median of received less trade time)."""
        now = time.time() if now is None else now
        with self._lock:
            last = [a for r, a in self._recent if now - r <= 60.0]
        return len(last), (sorted(last)[len(last) // 2] if last else None)

    # ---- the snapshots -------------------------------------------------------------------

    def held(self) -> set[str]:
        """Every name a connection holds this moment."""
        with self._lock:
            return set().union(*self._held.values()) if self._held else set()

    def snap_names(self, now: float | None = None) -> list[str]:
        """The snapshots' names, in the wanted list's order: every wanted name no connection
        holds, and once a day each one it does, refused names left out.

        ONCE A DAY THE CONNECTION'S NAMES TOO (2026-11-19, the first read after hours): the
        connection books a trade only when one happens, so 56 of its names that had not
        traded since the restart had no price at all. One snapshot gives each its last."""
        now = time.time() if now is None else now
        day = datetime.fromtimestamp(now, ET).date()
        held = self.held()
        with self._lock:
            refused = {s for s, t in self._refused.items() if now - t < REFUSED_SEC}
            read = {s for s, d in self._snap_read.items() if d == day}
        return [s for s in dict.fromkeys(self.wanted())
                if s and s not in refused and (s not in held or s not in read)]

    def snap_of(self, sym: str) -> tuple[float, float, float] | None:
        """(trade time, price, read at) of the name's last snapshot trade, or None."""
        with self._lock:
            return self._snap_by_sym.get(sym)

    def _snap_run(self) -> None:
        while not self._stop.is_set():
            try:
                wait = self._snap_pass()
            except Exception as e:  # noqa: BLE001 — a failed pass must not take the thread
                with self._lock:
                    self._snap["error"] = f"{e.__class__.__name__}: {e}"[:200]
                wait = SNAP_BACKOFF_SEC
            self._stop.wait(wait)

    def _snap_pass(self, now: float | None = None) -> float:
        """One read of every snapshot name, a hundred a call, each row's newest trade of the
        day into the books. Returns the seconds to the next pass.

        Outside every session (overnight, a closed day) it reads nothing. A name Webull says
        it does not know is set aside for REFUSED_SEC, as the subscribe sets it aside, and
        the rest of its call asked for again at once; any other refusal ends the pass."""
        from .stream import session_of_ts
        t = time.time() if now is None else now
        session = session_of_ts(t)
        if session is None or credentials() is None:
            with self._lock:
                self._snap.update(idle=True, every_sec=None)
            return SNAP_IDLE_SEC
        every = SNAP_SEC if session == "rth" else SNAP_EXT_SEC
        token, wait = self._token()
        if token is None:
            with self._lock:
                self._snap.update(idle=False, error="waiting for the token")
            return max(wait, every)
        names = self.snap_names(t)
        queue = [names[i:i + SNAP_CHUNK] for i in range(0, len(names), SNAP_CHUNK)]
        calls = rows = booked = 0
        err: Reply | None = None
        while queue and calls < SNAP_MAX_CALLS:
            part = queue.pop(0)
            calls += 1
            r = snapshots(part, token=token or None)
            got_at = time.time() if now is None else now
            with self._lock:
                self._snap_calls.append(got_at)
            if r.ok:
                got = r.data if isinstance(r.data, list) else []
                rows += len(got)
                day = datetime.fromtimestamp(t, ET).date()
                with self._lock:
                    for s in part:
                        self._snap_read[s] = day
                for row in got:
                    tr = snapshot_trade(row, t)
                    if tr is None:
                        continue
                    sym, px, at = tr
                    self.put(sym, px, at, src=SNAP_SRC, recv=got_at)
                    booked += 1
                    with self._lock:
                        self._snap_by_sym[sym] = (at, px, got_at)
                continue
            bad = [s for s in invalid_symbols(r) if s in part]
            if bad:
                with self._lock:
                    for s in bad:
                        self._refused[s] = t
                rest = [s for s in part if s not in bad]
                if rest:
                    queue.insert(0, rest)
                continue
            err = r
            if r.status in (401, 403):
                with self._token_lock:
                    self._token_held = (None, 0.0)
            break
        # Inside the budget: a pass of more calls than SNAP_SEC allows waits its share.
        wait = max(every, calls * 60.0 / SNAP_BUDGET_MIN)
        if err is not None and (err.status in (0, 401, 403, 429)):
            wait = max(wait, SNAP_BACKOFF_SEC)
        with self._lock:
            self._snap.update(names=len(names), rows=rows, booked=booked, calls=calls,
                              every_sec=round(wait, 1), idle=False,
                              error=None if err is None else f"snapshot refused: {err.error}")
            if err is None:
                self._snap["at"] = t
        return wait

    def snap_status(self, now: float | None = None) -> dict[str, Any]:
        """The snapshots' last pass and their calls in the last minute, for /api/feed."""
        now = time.time() if now is None else now
        with self._lock:
            d = dict(self._snap)
            d["calls_last_min"] = sum(1 for c in self._snap_calls if now - c <= 60.0)
        d["age_sec"] = round(now - d["at"], 1) if d.get("at") else None
        d["on"] = self.snapshots_on
        return d

    def status(self) -> SourceStatus:
        from .stream import lag_of
        st = SourceStatus("Webull")
        if websockets is None:
            st.error, st.source = "the websockets package is not installed", "unavailable"
            return st
        now = time.time()
        with self._lock:
            conns, subscribed, err, note = (len(self._connected), sum(self._subs.values()),
                                            self.error, self.note)
            refused = sorted(self._refused)
            last = self.last_tick
            raw = lag_of(list(self._recent), now)
            lag = max(0.0, raw) if raw is not None else None
        st.ok = conns > 0 and subscribed > 0
        st.items = subscribed
        st.source = "live" if st.ok else "unavailable"
        st.age_min = round((now - last) / 60.0, 2) if last else None
        st.notes = [f"{subscribed} names subscribed" + (
            f" on {conns} of {self.connections} connections" if self.connections > 1 else "")]
        snap = self.snap_status(now)
        if snap["on"] and not snap["idle"] and snap["every_sec"]:
            st.notes.append(f"snapshots: {snap['names']} more names every "
                            f"{snap['every_sec']:.0f}s" + (f" ({snap['error']})"
                                                          if snap["error"] else ""))
        if refused:
            st.notes.append(f"not known to Webull, left to Yahoo: {', '.join(refused[:12])}"
                            + (f" and {len(refused) - 12} more" if len(refused) > 12 else ""))
        if err and st.ok:
            st.notes.append(err)
        if note:
            st.notes.insert(0, note)
        if st.ok and lag is not None and lag > LATE_SEC:
            st.source = "stale"
            st.notes.insert(0, f"trades arriving about {lag:.0f}s late")
        if err and not st.ok:
            st.error = err
        if st.ok:
            st.last_ok_utc = datetime.now(UTC).isoformat()
        return st
