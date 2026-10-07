# wyattsnotes.wyattau.com

- URL: https://wyattsnotes.wyattau.com
- Stack: Astro / Starlight, behind Cloudflare
- Pages: 59 in sitemap
- Owner: WyattAu

## What it is good at exposing

- SERP truncation: titles and descriptions run long
- Client-side injection: the glossary pages render part of their content and
  their theme switcher with JavaScript, so raw-versus-rendered comparison has
  something to find
- A real canonical bug was found here: every page canonicalised to the site
  root, which is fixed by WyattAu/starlight-sites#23

## Notes

Response headers are set correctly (Cloudflare), so it is a good contrast case
against the GitHub Pages targets, where header findings are unactionable.
