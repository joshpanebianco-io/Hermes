import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The collector's address must never reach the browser. Every fetch of it
  // happens in a server component or a route handler, exactly as GEXYGEN keeps
  // its compute service off the client — here the reason is not a licence but
  // the same principle: the browser has no business knowing the shape of the
  // machine's private network.
  env: {},
  eslint: { ignoreDuringBuilds: false },
  // The "N" badge sat over the status rail's first source and the corner of
  // every pane — and daily use runs `next dev`, so it was on screen all day.
  devIndicators: false,
  // `next dev` binds 127.0.0.1 only (package.json -H): on every interface it
  // let any machine on the network press Generate or delete history. The page
  // still opens as either name for the loopback, and both must load the dev
  // bundle.
  allowedDevOrigins: ["localhost", "127.0.0.1"],
  // A production build gets its own directory (`npm run prod`, `dev.ps1
  // -Prod`): `next build` into `.next` would rewrite the files a running
  // `next dev` is serving from and break it mid-session.
  distDir: process.env.NT_DIST || ".next",
};

export default nextConfig;
