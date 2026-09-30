# Colored Hong Kong tile faces

The 34 standard faces and eight flower faces are derived from **I.Mahjong-HK** by 內木一郎 (SyaoranHinata).

- Source: https://github.com/SyaoranHinata/I.Mahjong
- Source commit: `73c507836e6ab30579305257ae3e2a7e1142d066`
- Font: `I.MahjongHK.otf`
- License: M+ font license; complete original text in `LICENSE.hk.txt` (commercial use, modification and redistribution allowed).
- Changes: exported glyph outlines to SVG, removed the font's outer tile-body border, and colored the original paths with vector clipping/masks. The white dragon's double-line face frame is retained.
- Flower lettering: 春夏秋冬 in red; 梅蘭菊竹 in ink black, distinguishing seasons from plants.
- Palette: ink `#191919`, red `#b2292f`, green `#126138`, blue `#244c9c`.
- All face graphics are paths; no runtime font or raster image is required.

## Filename mapping

- `1m.svg`–`9m.svg`: man; `1p.svg`–`9p.svg`: pin; `1s.svg`–`9s.svg`: sou.
- `1z.svg`–`7z.svg`: 東、南、西、北、白、發、中. The existing game's honor values are preserved.
- Flowers: `chun.svg` 春, `xia.svg` 夏, `qiu.svg` 秋, `dong.svg` 冬, `mei.svg` 梅, `lan.svg` 蘭, `ju.svg` 菊, `zhu.svg` 竹. The game uses 菊=7 and 竹=8.
- Legacy `0m.svg`, `0p.svg`, `0s.svg` are all-red derivatives of the corresponding Hong Kong five faces, preserving the old red-five filenames. Fenghua's normal palette uses values 1–9.

`Front.svg`, `back.svg`, and `Blank.svg` are the existing tile-body assets and are outside the above font attribution.

## Cache version

The Go server caches these stable filenames for 30 days. All frontend face requests use `getTileSvgUrl()` in `src/utils/tileDisplay.ts`, which adds `?v=hk-color-v3`. Bump that version whenever face artwork changes. The standalone `ledger-preview.html` uses the same version.
