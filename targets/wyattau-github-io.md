# wyattau.github.io (crawlkit, CivitForge, clawdius, EvergreenImageRegistry)

- URLs: https://wyattau.github.io/{crawlkit,CivitForge,clawdius,EvergreenImageRegistry}/
- Stack: static sites on GitHub Pages
- Owner: WyattAu

## What they are good at exposing

Unactionable findings. GitHub Pages does not allow custom response headers, so
14-19% of the defects an audit reports here cannot be fixed by following the
advice. Measured 220 of 1,319 across the four sites.

This is the case that produced `analyzers::hosting_advice`: the finding stays,
because it is true, and the recommendation names the constraint instead of
repeating a header the operator cannot set.
