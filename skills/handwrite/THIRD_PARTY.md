# Third-party code, data and fonts

## saurabhdaware/text-to-handwriting (MIT)

https://github.com/saurabhdaware/text-to-handwriting, commit `0f07785` (2021-07-11).
What came from it on 2026-09-28, rewritten in Python for this engine:

- `scripts/hw_effects.py`: the Shadows and Scanner page effects. The gradient colour (`#0008`
  to clear), the Scanner angle range (50 to 120 degrees) and the contrast formula and amount
  (`contrastImage()`, 0.55) are theirs, from `js/utils/generate-utils.mjs` and
  `js/generate-images.mjs`.
- `--paper-image` and the site's paper upload: their "Upload Paper Image as Background"
  (`js/utils/helpers.mjs` `addPaperFromFile`).
- The site's font upload (`.ttf`, `.otf`), its per-page download and its letter and word
  spacing and top margin controls, after their customisation panel (`index.html`).
- `liujian` in the font catalog: one of their three hands (the other two, Homemade Apple and
  Caveat, were already here).
- `evals/parity/upstream-t2h/*.jpg`: their app's output for our letter text, captured by
  running that commit locally (`capture.py`). No code, CSS or image from the repository is
  shipped here.

```
MIT License

Copyright (c) 2020 Saurabh Daware

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Not taken: their Kruti Dev Hindi font (`fonts/Hindi_Type.ttf`), which has no licence in the
repository; this engine writes Hindi with the Unicode Devanagari hands below.

## Fonts

No font file is in this repository. `hw_fonts.py` downloads each face from
[google/fonts](https://github.com/google/fonts) on first use into `assets/fonts/`, which is
git-ignored. Each face keeps its own licence, which allows redistribution; the folder a face
comes from in google/fonts names it (`ofl/` for the SIL Open Font License 1.1, `apache/` for the
Apache License 2.0).

| Name | Face | Licence | google/fonts path |
|---|---|---|---|
| `caveat` | Caveat | SIL OFL 1.1 | `ofl/caveat` |
| `kalam` | Kalam | SIL OFL 1.1 | `ofl/kalam` |
| `patrick` | PatrickHand | SIL OFL 1.1 | `ofl/patrickhand` |
| `indie` | IndieFlower | SIL OFL 1.1 | `ofl/indieflower` |
| `shadows` | ShadowsIntoLight | SIL OFL 1.1 | `ofl/shadowsintolight` |
| `gloria` | GloriaHallelujah | SIL OFL 1.1 | `ofl/gloriahallelujah` |
| `architect` | ArchitectsDaughter | SIL OFL 1.1 | `ofl/architectsdaughter` |
| `homemade` | HomemadeApple | Apache 2.0 | `apache/homemadeapple` |
| `reenie` | ReenieBeanie | SIL OFL 1.1 | `ofl/reeniebeanie` |
| `nothing` | NothingYouCouldDo | SIL OFL 1.1 | `ofl/nothingyoucoulddo` |
| `justanother` | JustAnotherHand | Apache 2.0 | `apache/justanotherhand` |
| `dawning` | DawningofaNewDay | SIL OFL 1.1 | `ofl/dawningofanewday` |
| `aurore` | LaBelleAurore | SIL OFL 1.1 | `ofl/labelleaurore` |
| `cedarville` | Cedarville | SIL OFL 1.1 | `ofl/cedarvillecursive` |
| `dancing` | DancingScript | SIL OFL 1.1 | `ofl/dancingscript` |
| `schoolbell` | Schoolbell | Apache 2.0 | `apache/schoolbell` |
| `comingsoon` | ComingSoon | Apache 2.0 | `apache/comingsoon` |
| `sueellen` | SueEllenFrancisco | SIL OFL 1.1 | `ofl/sueellenfrancisco` |
| `sunrise` | WaitingfortheSunrise | SIL OFL 1.1 | `ofl/waitingforthesunrise` |
| `rocksalt` | RockSalt | Apache 2.0 | `apache/rocksalt` |
| `zeyada` | Zeyada | SIL OFL 1.1 | `ofl/zeyada` |
| `gochi` | GochiHand | SIL OFL 1.1 | `ofl/gochihand` |
| `handlee` | Handlee | SIL OFL 1.1 | `ofl/handlee` |
| `kristi` | Kristi | SIL OFL 1.1 | `ofl/kristi` |
| `annie` | AnnieUseYourTelescope | SIL OFL 1.1 | `ofl/annieuseyourtelescope` |
| `delius` | Delius | SIL OFL 1.1 | `ofl/delius` |
| `caveatbrush` | CaveatBrush | SIL OFL 1.1 | `ofl/caveatbrush` |
| `neucha` | Neucha | SIL OFL 1.1 | `ofl/neucha` |
| `marck` | MarckScript | SIL OFL 1.1 | `ofl/marckscript` |
| `pangolin` | Pangolin | SIL OFL 1.1 | `ofl/pangolin` |
| `playpen` | PlaypenSans | SIL OFL 1.1 | `ofl/playpensans` |
| `playpen-ar` | PlaypenSansArabic | SIL OFL 1.1 | `ofl/playpensansarabic` |
| `playpen-he` | PlaypenSansHebrew | SIL OFL 1.1 | `ofl/playpensanshebrew` |
| `playpen-dev` | PlaypenSansDeva | SIL OFL 1.1 | `ofl/playpensansdeva` |
| `playpen-th` | PlaypenSansThai | SIL OFL 1.1 | `ofl/playpensansthai` |
| `ruqaa` | ArefRuqaa | SIL OFL 1.1 | `ofl/arefruqaa` |
| `mali` | Mali | SIL OFL 1.1 | `ofl/mali` |
| `sriracha` | Sriracha | SIL OFL 1.1 | `ofl/sriracha` |
| `nanumpen` | NanumPenScript | SIL OFL 1.1 | `ofl/nanumpenscript` |
| `gaegu` | Gaegu | SIL OFL 1.1 | `ofl/gaegu` |
| `klee` | KleeOne | SIL OFL 1.1 | `ofl/kleeone` |
| `yomogi` | Yomogi | SIL OFL 1.1 | `ofl/yomogi` |
| `kurenaido` | ZenKurenaido | SIL OFL 1.1 | `ofl/zenkurenaido` |
| `mashanzheng` | MaShanZheng | SIL OFL 1.1 | `ofl/mashanzheng` |
| `longcang` | LongCang | SIL OFL 1.1 | `ofl/longcang` |
| `zhimang` | ZhiMangXing | SIL OFL 1.1 | `ofl/zhimangxing` |
| `liujian` | LiuJianMaoCao | SIL OFL 1.1 | `ofl/liujianmaocao` |
