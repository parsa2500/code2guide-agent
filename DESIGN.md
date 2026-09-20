# Design System — Code2Guide

<!-- impeccable:design-schema 1 -->

## World

Airport FIDS split-console for an operate surface: the guide is a selected “flight,” not a chat thread. Matte LED panels, split-flap hairlines, amber armed states, teal live selection.

## Palette

| Token | Hex | Role |
|---|---|---|
| Navy | `#0b1220` | Ground |
| Navy lift | `#121b2e` | Panels / strip |
| Line | `#1c2740` | Split-flap dividers |
| Cream | `#f4f1e8` | Primary ink |
| Cream dim | `#c9c4b5` | Secondary ink |
| Amber | `#f5c518` | Armed / primary CTA |
| Teal | `#3dd6c6` | Live selection / success |
| Danger | `#ff6b5a` | Errors |
| OK | `#6dff9a` | Index healthy LED |

Strategy: Restrained dark operate — neutrals dominate; amber and teal only for action and state.

## Typography

- **UI / Persian guide:** Vazirmatn (400–700)
- **Board codes:** Barlow Condensed (500–700), tracked uppercase Latin codes (`USR`, `TEC`, `Index`)
- Scale: tight operate ratio; guide measure ~72ch; board codes larger than labels

## Layout

- Top LED status strip (brand + Index/Audience/Ask)
- Split console: left ~38% rail (destinations, workspace, index), right ~62% stage (ask gate + guide)
- Mobile: stack rail above stage; stats reflow to 2×2

## Components

- Destination columns (`aria-pressed`) for audience
- Flap-row form fields with 1px navy lines
- Primary amber CTA; teal secondary for index
- LED dots: idle / ok / warn / run / err
- Meta chips for routes/forms/breadcrumbs
- Guide markdown with teal h3, amber blockquote rule, LTR code

## Motion

- LED pulse while indexing/asking (~1.1s)
- Skeleton shimmer while guide loads
- Selection flood via teal inset underline (~160ms)
- `prefers-reduced-motion` disables pulse/shimmer

## Do / Don't

- Do keep dual audience as destination codes, not buried settings
- Do show honest empty/error/loading copy in Persian
- Don't drift into chat-bubble chrome or cream SaaS light themes
- Don't invent proof chips the API did not return

## Provenance

- Direction: grounded FIDS #6 (seed `bc539dcb`)
- Approved composition: `.impeccable/mocks/comp-b-split-console.png`
- Surface brief: `.impeccable/surfaces/frontend.md`
