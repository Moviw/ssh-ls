# ssh-ls visual and interaction design

## Direction

Use a calm, modern Tokyo Night-inspired terminal surface: deep blue-black background, cool blue/purple focus accents, teal for network/path data, and restrained semantic colors. Prioritize scan speed and host identity over decoration. The color names here are a product choice; do not present them as official Tokyo Night token assignments.

The design references are the curated [awesome-tui-design](https://github.com/cola-runner/awesome-tui-design) collection, especially its [Tokyo Night](https://github.com/cola-runner/awesome-tui-design/blob/master/designs/tokyo-night/DESIGN.md), [Catppuccin](https://github.com/cola-runner/awesome-tui-design/blob/master/designs/catppuccin/DESIGN.md), and [Nord](https://github.com/cola-runner/awesome-tui-design/blob/master/designs/nord/DESIGN.md) guides, plus interaction patterns from [Truffle Glyph](https://truffleagent.com/glyph/) and its [source repository](https://github.com/truffle-dev/glyph). These references describe visual/interaction patterns; this project is an independent implementation and does not reuse their source code. Glyph ships Go/Bubble Tea source today, not a Python/Textual dependency, so ssh-ls implements comparable behavior with native Textual widgets.

The Catppuccin guide uses upstream named palette colors but its semantic mapping (such as Mauve as primary or Teal for paths) is that guide's curated interpretation, not a rule imposed by [Catppuccin's official palette](https://catppuccin.com/palette/). Tokyo Night and Nord characterizations likewise follow the catalog's guidance, not an official semantic-token standard.

## Main screen

- Persistent two-column layout: searchable host rows on the left, selected-host details on the right.
- Keep alias/name as the strongest row text; use smaller, quieter text for user, destination, port, recent use, and source status.
- Keep host navigation and details visible together at wide widths. At a 100-column breakpoint, stack/collapse the detail area rather than squeezing aliases and connection metadata into unreadable columns.
- Show three compact tabs: All, Recent, Favorites. Open on Recent unless the user chooses another start page in Settings. Use one obvious active underline/accent and preserve selection while changing tabs where possible.
- Avoid group/tag hierarchy. Sorting, search, favorite, recency, and history provenance provide enough organization for the intended lightweight picker.

## Focus and density

- Selected list row uses a stable cursor mark and bold/high-contrast text; focused panel border and tab style reinforce keyboard focus.
- Use thin single-line borders and moderate padding; keep dividers quieter than content.
- Give the shortcut strip two spaced regions: common actions on the left and Help/Quit on the right. Render keycaps separately from labels. Hide lower-priority actions at narrow widths; never wrap a binding.
- Reserve fixed columns for cursor and favorite markers. Selection changes color and cursor only, never text alignment.
- Prefer immediate state changes. Animate only meaningful asynchronous operations, such as a connectivity check.

## Palette roles

Keep colors behind semantic tokens so a palette can be swapped without rewriting widgets:

| Token | Role |
| --- | --- |
| `background` | Main canvas |
| `surface` | Raised panels and modal backgrounds |
| `foreground` | Primary labels and host aliases |
| `muted` | Secondary metadata, borders, disabled controls |
| `accent` | Selection, active tab, focused border |
| `data` | Hostnames, addresses, key/config paths |
| `success`, `warning`, `error` | Results and validation states |

Do not encode state by color alone: pair status colors with labels/icons. Verify contrast in both truecolor and limited-color terminals; gracefully fall back to basic ANSI styling.

## Interaction conventions

- `j`/`k` and arrows move the list; `Tab` and left/right change tabs.
- `Space` toggles favorite; `/` starts search; `s` opens the sort menu.
- `Enter` connects; `a`/`e`/`c`/`Delete` manage records. `m` enters reorder mode; move with `j`/`k` or arrows and finish with `Esc`.
- `r` prompts for a remote command; `i` reloads config; `o` opens the Settings page; `v` opens a confirmed `ssh -G` inspection; `g` runs local diagnostics; `?` opens help; `q` quits. `U` resets a host’s saved overrides and `H` restores hidden hosts.
- Keep the footer discoverable and contextual. A help view should list the same bindings as the footer and dialogs.
- Destructive actions require explicit confirmation; show a short, specific action label with confirm/cancel keys.
- Use brief, non-blocking toasts for success/error feedback, with semantic icon + text and expiry. Do not use a toast as the sole report of a consequential failure.

## Accessibility and safety

- Honor terminal width/height; avoid requiring emoji, Nerd Fonts, or truecolor.
- History suggestions are untrusted input and remain inert until accepted. Never execute history content.
- Demo data must be synthetic and must not trigger SSH, config writes, or history scans.
