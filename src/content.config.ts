import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const days = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/days" }),
  schema: z.object({
    day: z.number(),
    date: z.string(), // YYYY-MM-DD (must be quoted in frontmatter)
    title: z.string(),
    goal: z.string().optional(),
    miles_today: z.string().optional(),
    total_pct: z.string().optional(),
    total_all: z.string().optional(),
    miles_to_go: z.string().optional(),
    stop_type: z.string().optional(),
    lat: z.number().optional(),
    lon: z.number().optional(),
  }),
});

export const collections = { days };
