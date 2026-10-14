/**
 * One knob for the size of every word on screen (owner, 2026-10-14: "increase
 * the font in the entire app, very very slightly").
 *
 * THE SIZES ARE PIXELS, SEVEN HUNDRED TIMES OVER. Every pane sets its own
 * `text-[11px]`, and the stylesheet's own rules (the eyebrow, Quiet's type
 * table) do the same, so a root font size scales nothing. Rewriting them by
 * hand would be seven hundred edits and a step that drifts the moment a new
 * pane is written. So this runs AFTER Tailwind, on the CSS it emits: every
 * `font-size: <n>px`, wherever it came from, becomes
 * `calc(<n>px * var(--type-scale, 1))`. The scale is set once, on :root in
 * globals.css. Relative sizes (em, %, a var) are already relative to one of
 * these, so they follow without being touched.
 *
 * What it cannot reach is what never passes through CSS: SVG `fontSize`
 * attributes, which the scanner chart sizes against its own geometry, and the
 * letter tile's inline size, which tracks the logo box rather than the type.
 */
const PX = /^(\d*\.?\d+)px$/;

const typeScale = () => ({
  postcssPlugin: "type-scale",
  Declaration: {
    "font-size"(decl) {
      const m = PX.exec(decl.value.trim());
      if (m) decl.value = `calc(${m[1]}px * var(--type-scale, 1))`;
    },
  },
});
typeScale.postcss = true;

module.exports = typeScale;
