// The type scale runs after Tailwind so it sees the utilities Tailwind emits
// (scripts/postcss-type-scale.cjs). Next resolves a plugin name from the repo
// root, so a relative path is how a local one is named.
const config = { plugins: { "@tailwindcss/postcss": {}, "./scripts/postcss-type-scale.cjs": {} } };
export default config;
