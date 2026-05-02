// @ts-check
import { defineConfig } from 'astro/config';

import cloudflare from "@astrojs/cloudflare";

// https://astro.build/config
export default defineConfig({
  // Used by Astro.site for absolute URLs (Open Graph, sitemap, etc.).
  // Update this when a custom domain is added.
  site: "https://trail.dustandstars.space",

  adapter: cloudflare(),
});