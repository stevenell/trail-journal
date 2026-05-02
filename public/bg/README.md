# Background image

Drop a file named **`space.jpg`** in this folder to use it as the site's
background. The image is referenced from `src/styles/global.css`:

```css
background-image: url("/bg/space.jpg"), ...
```

If `space.jpg` is missing, the browser silently skips that layer and
falls back to a CSS-only star field on a deep-space gradient — so the
site still looks intentional.

## Recommended specs

- **Format:** `.jpg` (smaller file size than PNG; we don't need transparency)
- **Size:** 1920×1080 or 2560×1440 — covers most viewports without scaling artifacts
- **Tone:** dark, low-contrast. The middle of the image will sit *behind* day cards, so keep the center calm.
- **File size:** < 500 KB ideally; the bg loads on every page

## Suggested AI prompts

For ChatGPT / DALL·E:

> A dark, deep-space website background. Mostly black/very dark navy
> with a faint scattering of small stars. One soft, low-saturation
> nebula wash in the upper-right corner — subtle, ~15% opacity.
> No planets, no focal points, no text. Designed to sit *behind*
> content cards, so the center should be calm and uncluttered.
> 1920×1080.

After you save the file here, run `update.ps1` (or just `npm run build`)
and the new background will pick up automatically.
