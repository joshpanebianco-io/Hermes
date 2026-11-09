/**
 * Laying a live trade on a chart's last candle. Pure, so it can be tested without
 * a chart: which bucket a trade falls in, what it does to that bucket, and the
 * next value of an EMA that has moved with it.
 */

export interface LiveBar {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface LiveTick {
  price: number;
  /** Epoch seconds of the trade. */
  at: number;
  /** This minute's candle from the stream, for the high and low between polls. */
  minute?: { t: number; o: number; h: number; l: number; c: number } | null;
}

/**
 * The bar this trade belongs to, and whether it is a new one. Null when the trade
 * is older than the newest bar (it is already in the bars). The grid is the
 * collector's: epoch seconds floored to the step, so :00 / :10 / :20 in ET.
 *
 * The minute's candle only counts when it falls inside the bucket: a poll that
 * lands just after the minute turned must not stretch the new bar with the old
 * minute's range.
 */
export function mergeTick(last: LiveBar | null, tick: LiveTick, step: number): { bar: LiveBar; isNew: boolean } | null {
  const at = Math.floor(tick.at);
  const k = at - (at % step);
  if (last && k < last.t) return null;
  const m = tick.minute && tick.minute.t >= k && tick.minute.t < k + step ? tick.minute : null;
  if (last && k === last.t) {
    return {
      bar: {
        ...last,
        h: Math.max(last.h, tick.price, m?.h ?? -Infinity),
        l: Math.min(last.l, tick.price, m?.l ?? Infinity),
        c: tick.price,
      },
      isNew: false,
    };
  }
  return {
    bar: {
      t: k,
      o: m?.o ?? tick.price,
      h: Math.max(tick.price, m?.h ?? -Infinity),
      l: Math.min(tick.price, m?.l ?? Infinity),
      c: tick.price,
      v: 0,
    },
    isNew: true,
  };
}

/** The next value of an EMA of length `len`, given the value before this bar. */
export function nextEma(prev: number, close: number, len: number): number {
  const k = 2 / (len + 1);
  return close * k + prev * (1 - k);
}
