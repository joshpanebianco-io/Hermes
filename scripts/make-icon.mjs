/**
 * Render the HERMESX mark to a Windows icon: public/hermesx.ico.
 *
 * WHY THIS EXISTS. There is no logo file in this repo: the header's Mark draws
 * the trace in HERMES_MARK_D straight from CSS tokens. A desktop shortcut needs
 * an .ico on disk — and the browser tab points at the same file
 * (src/app/layout.tsx) — so this rasterises the mark at the default
 * hues (green #00ffb2 -> white sheen -> pink #ff4fa3, see DEFAULT_THEME in
 * src/lib/theme.ts) and packs it. sharp does the rendering — Next already ships
 * it, so no new dependency.
 *
 *   node scripts/make-icon.mjs        # or: npm run icon
 *
 * The .ico is committed; run this only when the mark or its hues change. If the
 * desktop still shows the old picture afterwards that is Explorer's icon cache,
 * not the file — `ie4uinit.exe -show` or a sign-out refreshes it.
 *
 * ONE PICTURE FOR THE DESKTOP AND THE TAB. The tab icon was a plain black glyph
 * on a transparent tile until the owner asked for this one there too
 * (2026-09-22). A desktop sits on a wallpaper that supplies nothing, so this
 * carries its own chassis-black tile and the lockup's colours — the same call
 * GEXYGEN's icon makes, which is what lets the two sit side by side and read as
 * a pair — and the tile holds up just as well on a light or dark tab strip.
 *
 * ICO LAYOUT. 16-64 px are stored as classic 32-bit DIBs (readable by every
 * Windows since XP, and what the shell reaches for at desktop sizes); 128 and
 * 256 as PNG entries, which Vista+ decodes and which keep the file small. The
 * mark is drawn fresh at each size rather than scaled from one, so the traced
 * line work stays alive at 16 px and stays fine at 256.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const out = join(root, "public", "hermesx.ico");

/**
 * The trace, read out of the TypeScript module rather than duplicated. It is a
 * 26KB string literal; a second copy here is a second chance for the desktop
 * icon to drift away from the header, which is the one thing lib/hermesMark.ts
 * exists to prevent. A regex beats an import because that file is TS and this is
 * a plain node script with no build step in front of it.
 */
const source = readFileSync(join(root, "src", "lib", "hermesMark.ts"), "utf8");
const D = source.match(/HERMES_MARK_D\s*=\s*"([^"]+)"/)?.[1];
if (!D) throw new Error("could not read HERMES_MARK_D out of src/lib/hermesMark.ts");

const A = "#00ffb2"; // iconA default: green neon
const SHEEN = "#f2f5ff"; // the near-white stop the wordmark wash routes through
const B = "#ff4fa3"; // iconB default: pink neon
const CHASSIS = "#0a0b10"; // the app's chassis black, same tile as the GEXYGEN icon

/**
 * MIRRORED AND TILTED LIKE THE HEADER, SCALED DOWN TO SIT ON A TILE. The header
 * runs `rotate(-10 256 256) translate(512 0) scale(-1 1)` — rotate leftmost so
 * it applies in screen space AFTER the mirror, which is the trap the header's
 * own gradient fell into. Same order here, but the mirror is written about the
 * centre so the 0.86 can ride along with it. Full bleed is wrong inside a
 * rounded tile, where the corners would eat the wing tips.
 */
const MARK_TRANSFORM =
  "rotate(-10 256 256) translate(256 256) scale(-0.86 0.86) translate(-256 -256)";

/**
 * The lockup's wash, frozen. The header slides this gradient one full period
 * every 5.6s; an .ico is a still, so it gets one frame of that motion — wing in
 * green, sheen through the middle, face in pink. objectBoundingBox units (the
 * default) land the stops across the MARK rather than across the tile, and the
 * gradient is declared inside the mirrored group so offset 0 is the wing either
 * way.
 */
const gradient =
  `<linearGradient id="wash" x1="0" y1="0" x2="1" y2="0">` +
  `<stop offset="0" stop-color="${A}"/>` +
  `<stop offset="0.5" stop-color="${SHEEN}"/>` +
  `<stop offset="1" stop-color="${B}"/>` +
  `</linearGradient>`;

const DIB_SIZES = [16, 24, 32, 48, 64];
const PNG_SIZES = [128, 256];

/**
 * THE STROKE IS SIZE-DEPENDENT, AND HAS TO BE. The trace is line art whose
 * strokes run a couple of units wide in a 512 box — at a 16px raster that is a
 * third of a pixel, and the helm dissolves into grey mush. Stroking the path
 * with its own fill fattens the ink until it survives the sample grid: 300/size
 * units is about 0.6px of added ink at every size, floored at 8 so the large
 * entries keep the header's weight instead of going spidery.
 *
 * THE CEILING IS WHERE THE FEATHERS CLOSE UP. Fatter is not safer: the wing is
 * five fine strokes with narrow gaps, and past roughly 0.8px of added ink those
 * gaps fill and the wing becomes a green blob with no feathers in it. Measured
 * at 16/24/32 px across strokes 10-30, legibility peaked around 18/13/9 and
 * fell off above — which is the curve this constant is fitted to, not a guess.
 */
function svg(size) {
  const stroke = Math.max(8, Math.round(300 / size));
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 512 512">` +
    `<rect width="512" height="512" rx="112" fill="${CHASSIS}"/>` +
    `<g transform="${MARK_TRANSFORM}">` +
    `<defs>${gradient}</defs>` +
    `<path fill="url(#wash)" stroke="url(#wash)" stroke-width="${stroke}" ` +
    `stroke-linejoin="round" d="${D}"/>` +
    `</g></svg>`
  );
}

/** The SVG at an explicit pixel size, so librsvg rasterises AT that size instead of at 512 and downscaling. */
function render(size) {
  return sharp(Buffer.from(svg(size))).ensureAlpha();
}

/**
 * One 32-bit DIB icon image: BITMAPINFOHEADER, then the colour (XOR) bitmap as
 * bottom-up BGRA rows, then the 1-bit AND mask (rows padded to 4 bytes). The
 * alpha channel is what modern Windows composites with; the AND mask marks the
 * fully transparent pixels for anything that still reads it.
 */
function dib(size, rgba) {
  const rowBytes = size * 4;
  const maskRow = Math.ceil(size / 32) * 4;
  const xor = Buffer.alloc(size * rowBytes);
  const and = Buffer.alloc(size * maskRow);
  for (let y = 0; y < size; y++) {
    const src = (size - 1 - y) * rowBytes; // sharp is top-down, DIB is bottom-up
    for (let x = 0; x < size; x++) {
      const s = src + x * 4;
      const d = y * rowBytes + x * 4;
      xor[d] = rgba[s + 2];
      xor[d + 1] = rgba[s + 1];
      xor[d + 2] = rgba[s];
      xor[d + 3] = rgba[s + 3];
      if (rgba[s + 3] === 0) and[y * maskRow + (x >> 3)] |= 0x80 >> (x & 7);
    }
  }
  const hdr = Buffer.alloc(40);
  hdr.writeUInt32LE(40, 0); // biSize
  hdr.writeInt32LE(size, 4); // biWidth
  hdr.writeInt32LE(size * 2, 8); // biHeight: XOR + AND stacked
  hdr.writeUInt16LE(1, 12); // biPlanes
  hdr.writeUInt16LE(32, 14); // biBitCount
  hdr.writeUInt32LE(0, 16); // biCompression = BI_RGB
  hdr.writeUInt32LE(xor.length + and.length, 20); // biSizeImage
  return Buffer.concat([hdr, xor, and]);
}

const images = [];
for (const size of DIB_SIZES) {
  const { data, info } = await render(size).raw().toBuffer({ resolveWithObject: true });
  if (info.channels !== 4 || info.width !== size || info.height !== size) {
    throw new Error(`unexpected raster for ${size}px: ${JSON.stringify(info)}`);
  }
  images.push({ size, bytes: dib(size, data) });
}
for (const size of PNG_SIZES) {
  images.push({ size, bytes: await render(size).png().toBuffer() });
}

// ICONDIR (6 bytes) + one 16-byte ICONDIRENTRY per image, then the images.
const dir = Buffer.alloc(6 + 16 * images.length);
dir.writeUInt16LE(0, 0); // reserved
dir.writeUInt16LE(1, 2); // type 1 = icon
dir.writeUInt16LE(images.length, 4);
let offset = dir.length;
images.forEach(({ size, bytes }, i) => {
  const e = 6 + i * 16;
  dir.writeUInt8(size === 256 ? 0 : size, e); // 0 means 256
  dir.writeUInt8(size === 256 ? 0 : size, e + 1);
  dir.writeUInt8(0, e + 2); // no palette
  dir.writeUInt8(0, e + 3); // reserved
  dir.writeUInt16LE(1, e + 4); // planes
  dir.writeUInt16LE(32, e + 6); // bits per pixel
  dir.writeUInt32LE(bytes.length, e + 8);
  dir.writeUInt32LE(offset, e + 12);
  offset += bytes.length;
});

const ico = Buffer.concat([dir, ...images.map((i) => i.bytes)]);
writeFileSync(out, ico);
console.log(
  `wrote ${relative(root, out)}: ${images.map((i) => i.size).join("/")} px, ${ico.length} bytes`,
);
