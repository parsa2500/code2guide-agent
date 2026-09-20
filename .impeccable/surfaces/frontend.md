# frontend/ — Code2Guide FIDS shell
# mode: operate
# audience: dual (technical + end_user) with index + ask
# approved-comp: .impeccable/mocks/comp-b-split-console.png
# direction: airport FIDS split console (seed bc539dcb, assigned grounded #6)

## Scope
React+Vite operator shell for Code2Guide: audience switch, workspace index, ask, markdown guide.

## Composition commitments (approved B)
- Left rail (~38%): brand + index status LEDs + audience destination columns + workspace + index action
- Center gate: ask textarea + submit as board row
- Right pane (~62%): guide reading surface with meta chips
- Palette: navy #0b1220, cream #f4f1e8, amber #f5c518, teal #3dd6c6
- Materials: matte LED panels, 1px split-flap hairlines, amber armed/warning, teal live
- Type: Vazirmatn (Persian UI/guide), Barlow Condensed (board codes)
- Motion: selected-row teal flood 180ms; index LED pulse when running

## Inventory
| Region | Medium |
| Brand wordmark | CSS type |
| Status LEDs | CSS |
| Audience columns | semantic buttons |
| Workspace + index | form controls |
| Ask gate | form |
| Guide pane | marked + CSS |
| Icons | authored SVG stroke set |
