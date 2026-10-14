/**
 * Download every ticker's logo once and save it at one size in public/logos
 * (owner, 2026-10-14: "icons for every ticker" — the company's real mark, not
 * a lookup service's guess; the runtime symbol lookup this replaces put an
 * unrelated company's logo on SPCX).
 *
 * WHAT A "LOGO" IS HERE. Each company's own site icon — the mark it publishes
 * for browsers, phone home screens and search results — found through the
 * company's website in scripts/logo-domains.json. Three quick places are
 * tried and the largest image wins: Google's favicon service (which picks the
 * site's best icon up to the size asked), the site's own
 * /apple-touch-icon.png, and DuckDuckGo's icon cache. When those give nothing
 * or less than 48px, Playwright opens the company's homepage as a browser
 * would and reads the icons the page itself declares — including SVG ones,
 * which draw sharp at any size. An ETF wears its issuer's mark (SPY State
 * Street, QQQ Invesco, IWM iShares). No account and no key, and nothing is
 * fetched at runtime: the files are committed and the app serves them itself.
 *
 * A ticker with no file gets a letter tile in the page — Berkshire's site has
 * no icon at all, and a name added to the watchlist has none until this runs.
 *
 * WHEN THE SITE ICON IS NOT THE LOGO. Some companies give their site a
 * different picture from their logo: every icon ibm.com declares is Paul
 * Rand's grey outline bee, not the striped IBM, so the largest-icon rule can
 * only ever land on the bee. For those, logo-domains.json names an image URL
 * on the company's own site instead of a domain. That image is used as it is,
 * with its transparent margin cut away first: a brand file is drawn with
 * generous clear space, and fitting the clear space into 64px leaves the mark
 * itself a few pixels tall.
 *
 * THE CONVERSION IS THE BROWSER'S. Playwright decodes whatever came back —
 * PNG, JPEG, ICO, SVG — and draws it into a 64×64 canvas, contained and
 * centred; 64px covers a 16px slot on a 4× screen. A dark mark on a
 * transparent ground gets a light tile behind it, or it would vanish on the
 * terminal's dark surfaces — judged on the pixels that show, so a dark mark
 * with a little transparency round it is tiled too.
 *
 *   node scripts/fetch-logos.mjs              # tickers without a logo yet
 *   node scripts/fetch-logos.mjs --force      # every ticker again
 *   node scripts/fetch-logos.mjs NVDA AAPL    # just these (again)
 *   npm run logos -- XYZ                      # a new name: its website is
 *                                             # looked up on Nasdaq and saved
 *
 * Saved as WebP through sharp (Next ships it) — about a quarter of the canvas
 * PNG's size at the same look.
 *
 * Writes public/logos/<TICKER>.webp and src/lib/logos.generated.ts, the list
 * the page checks before asking for a file. A name not in logo-domains.json
 * yet has its website read from Nasdaq's company profile (the same free
 * source the collector's calendars use) and saved there — an ETF has none and
 * needs its issuer's site added by hand.
 */

import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import sharp from "sharp";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const OUT = join(root, "public", "logos");
const LIST = join(root, "src", "lib", "logos.generated.ts");
const SIZE = 64;
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";

const domains = JSON.parse(readFileSync(join(root, "scripts", "logo-domains.json"), "utf8"));
const args = process.argv.slice(2);
const force = args.includes("--force");
const only = args.filter((a) => !a.startsWith("--")).map((a) => a.toUpperCase());
const fileOf = (t) => join(OUT, `${t}.webp`);

/** An image as a data URL, or null for anything that is not one. */
async function get(url) {
  try {
    const r = await fetch(url, {
      headers: { "user-agent": UA, accept: "image/*,*/*;q=0.8" },
      redirect: "follow",
      signal: AbortSignal.timeout(15_000),
    });
    if (!r.ok) return null;
    const type = (r.headers.get("content-type") || "").split(";")[0].trim();
    if (!type.startsWith("image/")) return null;
    const buf = Buffer.from(await r.arrayBuffer());
    return buf.length < 64 ? null : `data:${type};base64,${buf.toString("base64")}`;
  } catch {
    return null;
  }
}

/** Every decodable candidate's size, measured by the browser on a blank page. */
async function measure(work, src) {
  return work.evaluate(async (s) => {
    const img = new Image();
    img.src = s;
    try {
      await img.decode();
    } catch {
      return null;
    }
    // A blank image is no image: Phillips 66's site served a fully
    // transparent icon, and the first run saved it as an invisible logo.
    const probe = document.createElement("canvas");
    probe.width = probe.height = 32;
    const pg = probe.getContext("2d");
    pg.drawImage(img, 0, 0, 32, 32);
    const px = pg.getImageData(0, 0, 32, 32).data;
    let ink = 0;
    for (let i = 3; i < px.length; i += 4) if (px[i] > 26) ink++;
    if (ink < 8) return null;
    // An SVG without its own size is a vector: as large as anyone asks.
    if (!img.naturalWidth && s.startsWith("data:image/svg")) return { w: 512, h: 512 };
    return { w: img.naturalWidth, h: img.naturalHeight };
  }, src);
}

/** The icons a company's homepage declares, fetched as the browser that loaded it. */
async function declared(nav, domain) {
  const bases = domain.split(".").length > 2 ? [`https://${domain}`] : [`https://www.${domain}`, `https://${domain}`];
  for (const base of bases) {
    try {
      await nav.goto(base, { waitUntil: "domcontentloaded", timeout: 25_000 });
      const links = await nav.evaluate(() =>
        [...document.querySelectorAll('link[rel~="icon"], link[rel="apple-touch-icon"], link[rel="apple-touch-icon-precomposed"]')]
          .map((l) => l.href)
          .filter(Boolean),
      );
      const out = [];
      for (const href of [...new Set(links)]) {
        try {
          const r = await nav.request.get(href, { timeout: 15_000 });
          if (!r.ok()) continue;
          const type = (r.headers()["content-type"] || "").split(";")[0].trim() || (href.endsWith(".svg") ? "image/svg+xml" : "");
          if (!type.startsWith("image/")) continue;
          out.push(`data:${type};base64,${(await r.body()).toString("base64")}`);
        } catch {
          /* the next one */
        }
      }
      if (out.length) return out;
    } catch {
      /* the next base */
    }
  }
  return [];
}

/** A logo named by URL in logo-domains.json, its transparent margin trimmed. */
async function named(url) {
  const src = await get(url);
  if (!src) return null;
  try {
    const png = await sharp(Buffer.from(src.split(",")[1], "base64")).trim().png().toBuffer();
    return `data:image/png;base64,${png.toString("base64")}`;
  } catch {
    return src; // a format sharp cannot read — the browser may still draw it, margin and all
  }
}

const sources = (d) => [
  ["google", `https://www.google.com/s2/favicons?domain=${d}&sz=128`],
  ["site", `https://${d}/apple-touch-icon.png`],
  ["duckduckgo", `https://icons.duckduckgo.com/ip3/${d}.ico`],
];

/** A listed company's website from Nasdaq's company profile, as a bare host. */
async function website(ticker) {
  try {
    const r = await fetch(`https://api.nasdaq.com/api/company/${ticker.replace(/\./g, "-")}/company-profile`, {
      headers: { "user-agent": UA, accept: "application/json" },
      signal: AbortSignal.timeout(15_000),
    });
    const url = (await r.json())?.data?.CompanyUrl?.value?.trim();
    return url ? new URL(url.includes("://") ? url : `https://${url}`).hostname.replace(/^www\./, "").toLowerCase() : null;
  } catch {
    return null;
  }
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  // Names asked for by hand that the list does not know yet.
  let added = 0;
  for (const t of only.filter((x) => !domains[x])) {
    const host = await website(t);
    if (host) {
      domains[t] = host;
      added++;
      console.log(`${t.padEnd(6)} ${host} (from Nasdaq's company profile)`);
    } else {
      console.log(`${t.padEnd(6)} no website on Nasdaq — add it to scripts/logo-domains.json by hand`);
    }
  }
  if (added) {
    const sorted = Object.fromEntries(Object.entries(domains).sort(([a], [b]) => a.localeCompare(b)));
    writeFileSync(join(root, "scripts", "logo-domains.json"), `${JSON.stringify(sorted, null, 2)}
`);
  }
  const todo = Object.entries(domains).filter(([t]) => (only.length ? only.includes(t) : force || !existsSync(fileOf(t))));
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const nav = await browser.newPage({ userAgent: UA });
  const report = [];

  for (const [ticker, domain] of todo) {
    let best = null;
    const isUrl = /^https?:\/\//.test(domain);
    const label = isUrl ? new URL(domain).hostname.replace(/^www\./, "") : domain;
    if (isUrl) {
      // Named outright: that image or nothing, never a site icon instead.
      const src = await named(domain);
      const dims = src && (await measure(page, src));
      if (dims && dims.w) best = { from: "named", src, size: Math.min(dims.w, dims.h) };
    } else {
      // Every source, measured by the browser; the largest decodable image wins.
      for (const [from, url] of sources(domain)) {
        const src = await get(url);
        if (!src) continue;
        const dims = await measure(page, src);
        if (!dims || !dims.w) continue;
        const size = Math.min(dims.w, dims.h);
        if (!best || size > best.size) best = { from, src, size };
        if (size >= 128) break; // big enough; skip the rest
      }
    }
    // Weak or nothing: open the homepage and read what it declares.
    if (!isUrl && (!best || best.size < 48)) {
      for (const src of await declared(nav, domain)) {
        const dims = await measure(page, src);
        if (!dims || !dims.w) continue;
        const size = Math.min(dims.w, dims.h);
        if (!best || size > best.size) best = { from: "homepage", src, size };
      }
    }
    if (!best) {
      report.push(`${ticker.padEnd(6)} ${label.padEnd(28)} NOTHING — gets a letter tile`);
      continue;
    }

    const out = await page.evaluate(
      async ({ src, size }) => {
        const img = new Image();
        img.src = src;
        await img.decode();
        const c = document.createElement("canvas");
        c.width = c.height = size;
        const g = c.getContext("2d");
        g.imageSmoothingQuality = "high";
        const nw = img.naturalWidth || size;
        const nh = img.naturalHeight || size;
        const fit = (box, off) => {
          const s = Math.min(box / nw, box / nh);
          const w = nw * s;
          const h = nh * s;
          g.drawImage(img, off + (box - w) / 2, off + (box - h) / 2, w, h);
        };
        fit(size, 0);
        // How much is see-through, and how dark is what is not.
        const px = g.getImageData(0, 0, size, size).data;
        let clear = 0;
        let lum = 0;
        let n = 0;
        for (let i = 0; i < px.length; i += 4) {
          if (px[i + 3] < 26) {
            clear++;
            continue;
          }
          lum += (0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]) / 255;
          n++;
        }
        const clearShare = clear / (size * size);
        const tone = n ? lum / n : 1;
        const tiled = clearShare > 0.12 && tone < 0.32;
        if (tiled) {
          g.clearRect(0, 0, size, size);
          g.fillStyle = "#f1f3f6";
          g.beginPath();
          g.roundRect(0, 0, size, size, size * 0.2);
          g.fill();
          fit(size * 0.72, size * 0.14);
        }
        return { png: c.toDataURL("image/png"), clearShare, tone, tiled };
      },
      { src: best.src, size: SIZE },
    );
    await sharp(Buffer.from(out.png.split(",")[1], "base64"))
      .webp({ quality: 92, alphaQuality: 100, effort: 6 })
      .toFile(fileOf(ticker));
    report.push(`${ticker.padEnd(6)} ${label.padEnd(28)} ${best.from.padEnd(10)} ${String(best.size).padStart(3)}px${out.tiled ? "  on a light tile" : ""}`);
  }
  await browser.close();

  // The list the page reads, from what is actually on disk.
  const have = readdirSync(OUT)
    .filter((f) => f.endsWith(".webp"))
    .map((f) => f.slice(0, -5))
    .sort();
  writeFileSync(
    LIST,
    `// Generated by scripts/fetch-logos.mjs — do not edit. The tickers with a logo in public/logos.\n` +
      `export const LOGO_TICKERS: ReadonlySet<string> = new Set(${JSON.stringify(have)});\n`,
  );
  console.log(report.join("\n"));
  console.log(`\n${have.length} logos in public/logos; ${todo.length} fetched this run.`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
