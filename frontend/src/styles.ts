import { css } from "lit";

/**
 * The panel's styles, from the mockup. Colors come from the palette's
 * custom properties (see theme.ts); green, amber, orange and red are only
 * used for safety ratings.
 */
export const styles = css`
  :host {
    --sc-radius: 12px;
    --sc-font: var(--ha-font-family-body, Roboto, system-ui, -apple-system, "Segoe UI", sans-serif);
    /* The panel registers with handle_safe_area, so it keeps clear of
       notches itself. Home Assistant sets these variables; the sidebar
       already covers the left inset when it's shown. */
    --sc-inset-top: var(--safe-area-inset-top, env(safe-area-inset-top, 0px));
    --sc-inset-bottom: var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px));
    --sc-inset-left: var(
      --safe-area-content-inset-left,
      var(--safe-area-inset-left, env(safe-area-inset-left, 0px))
    );
    --sc-inset-right: var(
      --safe-area-content-inset-right,
      var(--safe-area-inset-right, env(safe-area-inset-right, 0px))
    );
    display: block;
    font-family: var(--sc-font);
    font-size: 14px;
    line-height: 1.45;
    -webkit-font-smoothing: antialiased;
  }
  *,
  *::before,
  *::after {
    box-sizing: border-box;
  }
  [hidden] {
    display: none !important;
  }
  button,
  input,
  select,
  textarea {
    font: inherit;
    color: inherit;
  }
  :focus-visible {
    outline: 2px solid var(--sc-focus);
    outline-offset: 2px;
  }
  h1,
  h2,
  h3 {
    text-wrap: balance;
  }
  .muted {
    color: var(--sc-fg2);
  }
  .small {
    font-size: 12px;
    color: var(--sc-fg2);
  }
  .eyebrow {
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--sc-fg2);
  }
  .i {
    width: 18px;
    height: 18px;
    fill: currentColor;
    flex: none;
  }
  .num {
    font-variant-numeric: tabular-nums;
  }
  .arr {
    display: inline-block;
    vertical-align: -2px;
    color: var(--sc-fg2);
    flex: none;
  }
  .wx {
    width: 18px;
    height: 18px;
    vertical-align: -4px;
    flex: none;
  }

  /* Page, toolbar and tabs */
  .page {
    min-height: 100vh;
    min-height: 100dvh;
    background: var(--sc-page);
    color: var(--sc-fg);
  }
  .toolbar {
    position: relative;
    z-index: 4;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px 18px;
    min-height: 56px;
    padding: calc(var(--sc-inset-top) + 6px) max(16px, var(--sc-inset-right)) 6px
      max(8px, var(--sc-inset-left));
    background: var(--sc-toolbar);
    border-bottom: 1px solid var(--sc-line);
    color: var(--sc-toolbar-ink);
  }
  .title {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-right: auto;
    font-size: 20px;
  }
  .title h1 {
    margin: 0;
    font-size: inherit;
    font-weight: 500;
  }
  .logo svg {
    display: block;
    width: 30px;
    height: 30px;
  }
  ha-menu-button {
    color: var(--sc-toolbar-ink);
  }
  .pickers {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 8px 12px;
  }
  .pick {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    min-width: 0;
  }
  .field {
    display: grid;
    gap: 3px;
    min-width: 0;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--sc-fg2);
  }
  .field select {
    max-width: 100%;
    padding: 7px 10px;
    border: 1px solid var(--sc-line);
    border-radius: 8px;
    background: var(--sc-card);
    color: var(--sc-fg);
    font-size: 14px;
    letter-spacing: 0;
    text-transform: none;
  }
  .mode {
    display: inline-flex;
    align-self: flex-end;
    gap: 2px;
    padding: 2px;
    border: 1px solid var(--sc-line);
    border-radius: 999px;
  }
  .mode button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 32px;
    padding: 0 12px;
    border: 0;
    border-radius: 999px;
    background: transparent;
    color: var(--sc-fg2);
    font-size: 13px;
    cursor: pointer;
  }
  .mode button .i {
    width: 17px;
    height: 17px;
  }
  .mode button[aria-pressed="true"] {
    background: var(--sc-primary-tint);
    color: var(--sc-primary-ink);
  }
  .tabs {
    display: flex;
    gap: 2px;
    padding: 0 max(12px, var(--sc-inset-right)) 0 max(12px, var(--sc-inset-left));
    border-bottom: 1px solid var(--sc-line);
    overflow-x: auto;
  }
  .tabs a {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 13px 14px 11px;
    border-bottom: 2px solid transparent;
    color: var(--sc-fg2);
    font-weight: 500;
    text-decoration: none;
    white-space: nowrap;
  }
  .tabs a[aria-selected="true"] {
    border-bottom-color: var(--sc-primary);
    color: var(--sc-primary-ink);
  }
  .content {
    min-width: 0;
    max-width: 1380px;
    margin: 0 auto;
    padding: 18px max(20px, var(--sc-inset-right)) calc(28px + var(--sc-inset-bottom))
      max(20px, var(--sc-inset-left));
    container: panel / inline-size;
  }
  .view {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  .advisory {
    margin: 4px 0 0;
    color: var(--sc-fg2);
    font-size: 12px;
  }
  /* On a phone the pickers wrap, so the toolbar scrolls away with the page. */
  @media (min-width: 601px) {
    .toolbar {
      position: sticky;
      top: 0;
    }
  }
  @media (max-width: 760px) {
    .mode button b {
      display: none;
    }
    .mode button {
      padding: 0 9px;
    }
  }
  @media (max-width: 600px) {
    .content {
      padding: 14px max(10px, var(--sc-inset-right)) calc(20px + var(--sc-inset-bottom))
        max(10px, var(--sc-inset-left));
    }
    .title {
      flex-basis: calc(100% - 140px);
    }
  }
  @media (max-width: 520px) {
    .tabs a {
      padding: 13px 10px 11px;
    }
    .tabs a .i {
      display: none;
    }
  }

  /* Shared parts */
  .card {
    min-width: 0;
    padding: 16px;
    border: 1px solid var(--sc-line);
    border-radius: var(--sc-radius);
    background: var(--sc-card);
  }
  .card h2 {
    margin: 0;
    font-size: 16px;
    font-weight: 500;
  }
  .card-head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 6px 16px;
    margin-bottom: 10px;
  }
  .card p.small {
    margin: 8px 0 0;
  }
  .key {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    font-size: 12px;
    color: var(--sc-fg2);
  }
  .key i {
    display: inline-block;
    width: 14px;
    height: 3px;
    margin-right: 5px;
    border-radius: 2px;
    vertical-align: middle;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 500;
    white-space: nowrap;
  }
  .chip::before {
    content: "";
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
  }
  .lvl-good {
    background: var(--sc-good-bg);
    color: var(--sc-good);
  }
  .lvl-caution {
    background: var(--sc-caution-bg);
    color: var(--sc-caution);
  }
  .lvl-not_recommended {
    background: var(--sc-notrec-bg);
    color: var(--sc-notrec);
  }
  .lvl-dangerous {
    background: var(--sc-danger-bg);
    color: var(--sc-danger);
  }
  .s-great {
    --band: var(--sc-s-great);
    --band-ink: var(--sc-s-great-ink);
  }
  .s-good {
    --band: var(--sc-s-good);
    --band-ink: var(--sc-s-good-ink);
  }
  .s-fair {
    --band: var(--sc-s-fair);
    --band-ink: var(--sc-s-fair-ink);
  }
  .s-poor {
    --band: var(--sc-s-poor);
    --band-ink: var(--sc-s-poor-ink);
  }
  .ring {
    display: block;
    flex: none;
    width: 36px;
    height: 36px;
  }
  .ring circle {
    fill: none;
    stroke-width: 3.4;
  }
  .ring .rt {
    stroke: var(--ring-t, var(--sc-ring-track));
  }
  .ring .rv {
    stroke: var(--ring-v, var(--band));
    stroke-linecap: round;
  }
  .ring text {
    font: 700 11px var(--sc-font);
    fill: var(--ring-fg, var(--sc-fg));
  }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    min-height: 36px;
    padding: 0 16px;
    border: 1px solid transparent;
    border-radius: 999px;
    background: transparent;
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
  }
  .btn[disabled] {
    opacity: 0.55;
    cursor: default;
  }
  .btn-primary {
    background: var(--sc-btn);
    color: var(--sc-btn-ink);
  }
  .btn-primary:hover:not([disabled]) {
    filter: brightness(1.08);
  }
  .btn-tonal {
    background: var(--sc-primary-tint);
    color: var(--sc-primary-ink);
  }
  .btn-text {
    padding: 0 10px;
    color: var(--sc-primary-ink);
  }
  .btn-text:hover,
  .btn-tonal:hover {
    background: var(--sc-primary-tint);
  }
  .btn-danger {
    padding: 0 10px;
    color: var(--sc-danger);
  }
  .btn-danger:hover {
    background: var(--sc-danger-bg);
  }
  .btn-sea {
    background: var(--sc-sea-ink);
    color: var(--sc-sea);
  }
  .btn-sea-ghost {
    border-color: var(--sc-sea-line);
    color: var(--sc-sea-ink);
  }
  .btn-sea-ghost:hover {
    background: var(--sc-sea-chip);
  }
  .icon-btn {
    display: inline-grid;
    flex: none;
    place-items: center;
    width: 36px;
    height: 36px;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: var(--sc-fg2);
    cursor: pointer;
  }
  .icon-btn:hover {
    background: var(--sc-primary-tint);
    color: var(--sc-primary-ink);
  }
  .icon-btn .i {
    width: 20px;
    height: 20px;
  }
  .switch {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 12px;
    font-size: 13px;
    cursor: pointer;
  }
  .switch input {
    position: relative;
    flex: none;
    width: 34px;
    height: 20px;
    margin: 0;
    border-radius: 999px;
    background: var(--sc-line);
    appearance: none;
    -webkit-appearance: none;
    cursor: pointer;
    transition: background 0.15s;
  }
  .switch input::after {
    content: "";
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--sc-knob);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    transition: transform 0.15s;
  }
  .switch input:checked {
    background: var(--sc-btn);
  }
  .switch input:checked::after {
    transform: translateX(14px);
  }
  .switch.big {
    margin-top: 0;
    font-size: 14px;
    font-weight: 500;
  }
  .notice {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 14px;
    border-radius: 12px;
    background: var(--sc-primary-tint);
    font-size: 13px;
  }
  .notice .i {
    margin-top: 1px;
    fill: var(--sc-primary-ink);
  }
  .notice p {
    margin: 0;
  }
  .error {
    background: var(--sc-danger-bg);
    color: var(--sc-danger);
  }
  .error .i {
    fill: var(--sc-danger);
  }
  .empty-state {
    display: grid;
    justify-items: start;
    gap: 10px;
  }
  .empty-state p {
    margin: 0;
    max-width: 70ch;
    color: var(--sc-fg2);
  }

  /* Week: best window and the two status cards */
  .top {
    display: grid;
    grid-template-columns: minmax(0, 1.85fr) minmax(0, 1fr);
    gap: 14px;
  }
  .side {
    display: grid;
    align-content: start;
    gap: 14px;
  }
  @container panel (max-width: 900px) {
    .top {
      grid-template-columns: minmax(0, 1fr);
    }
    .side {
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    }
  }
  .hero {
    position: relative;
    isolation: isolate;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    column-gap: 20px;
    min-height: 250px;
    padding: 20px 22px 28px;
    overflow: hidden;
    border-radius: 16px;
    background: var(--sc-sea);
    color: var(--sc-sea-ink);
  }
  .hero-wave {
    position: absolute;
    left: 0;
    bottom: 0;
    z-index: -1;
    width: 100%;
    height: 46%;
  }
  .hero-main {
    display: grid;
    align-content: start;
    gap: 2px;
    min-width: 0;
  }
  .hero .eyebrow {
    color: var(--sc-sea-ink2);
  }
  .hero-day {
    margin-top: 10px;
    color: var(--sc-sea-ink2);
    font-size: 16px;
  }
  .hero-time {
    font-size: clamp(28px, 4vw, 40px);
    font-weight: 500;
    line-height: 1.12;
    letter-spacing: -0.01em;
  }
  .hero-none {
    margin-top: 12px;
  }
  .hero-note {
    max-width: 52ch;
    margin: 8px 0 0;
    color: var(--sc-sea-ink2);
  }
  .hero-facts {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 12px;
  }
  .hero-facts > span {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 10px;
    border-radius: 999px;
    background: var(--sc-sea-chip);
    font-size: 12.5px;
    font-variant-numeric: tabular-nums;
  }
  .hero-facts .i,
  .hero-facts .arr,
  .hero-facts .wx {
    width: 15px;
    height: 15px;
    color: inherit;
  }
  .hero-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 16px;
  }
  .hero-next {
    margin-top: 12px;
    color: var(--sc-sea-ink2);
    font-size: 12.5px;
  }
  .hero-score {
    display: grid;
    align-content: start;
    justify-items: center;
    gap: 6px;
    padding-top: 2px;
    font-size: 13px;
    font-weight: 500;
  }
  .hero .ring {
    --ring-v: var(--sc-sea-ink);
    --ring-t: var(--sc-sea-chip);
    --ring-fg: var(--sc-sea-ink);
    width: 96px;
    height: 96px;
  }
  @container panel (max-width: 560px) {
    .hero {
      column-gap: 12px;
      padding: 16px 16px 24px;
    }
    .hero .ring {
      width: 64px;
      height: 64px;
    }
  }
  .now-main {
    display: flex;
    align-items: center;
    gap: 14px;
    margin: 12px 0 10px;
  }
  .dial {
    flex: none;
    width: 60px;
    height: 60px;
  }
  .dial-ring {
    fill: var(--sc-sunk);
    stroke: var(--sc-line);
  }
  .dial-tick {
    stroke: var(--sc-fg3);
    stroke-width: 1.5;
  }
  .dial-n {
    font: 500 8px var(--sc-font);
    fill: var(--sc-fg3);
  }
  .dial-arrow {
    fill: var(--sc-primary-ink);
  }
  .now-big {
    font-size: 30px;
    font-weight: 500;
    line-height: 1;
  }
  .now-big small {
    margin-left: 3px;
    color: var(--sc-fg2);
    font-size: 14px;
    font-weight: 400;
  }
  .now-sub {
    margin-top: 3px;
    color: var(--sc-fg2);
    font-size: 13px;
  }
  .kv {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 4px 12px;
    margin: 0;
    font-size: 13px;
  }
  .kv dt {
    color: var(--sc-fg2);
  }
  .kv dd {
    margin: 0;
  }
  .src {
    color: var(--sc-fg2);
    font-size: 12px;
    white-space: nowrap;
  }
  .warn-status {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 12px 0 2px;
    font-size: 15px;
    font-weight: 500;
  }
  .warn-status .i {
    width: 28px;
    height: 28px;
  }
  .warn-status small {
    display: block;
    color: var(--sc-fg2);
    font-size: 12px;
    font-weight: 400;
  }
  .warn-status.ok .i {
    fill: var(--sc-dot-good);
  }
  .warn-status.on .i {
    fill: var(--sc-dot-danger);
  }

  /* Week: the calendar */
  .cal-card {
    display: grid;
    gap: 14px;
    padding: 18px;
  }
  .cal-head h2 {
    font-size: 17px;
  }
  .cal-head p {
    margin: 4px 0 0;
  }
  .cal-tools {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  .auto-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    max-width: 100%;
    min-height: 34px;
    padding: 5px 12px 5px 10px;
    border: 1px dashed var(--sc-line);
    border-radius: 999px;
    background: transparent;
    color: var(--sc-fg2);
    font-size: 12.5px;
    text-align: left;
    cursor: pointer;
  }
  .auto-chip .i {
    width: 16px;
    height: 16px;
    fill: var(--sc-fg3);
  }
  .auto-chip b {
    color: var(--sc-primary-ink);
    font-weight: 500;
    white-space: nowrap;
  }
  .auto-chip.on {
    border-style: solid;
    border-color: var(--sc-primary);
    color: var(--sc-fg);
  }
  .auto-chip.on .i {
    fill: var(--sc-primary-ink);
  }
  .pl {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    max-width: 100%;
    min-height: 34px;
    padding: 5px 12px 5px 10px;
    border: 0;
    border-radius: 999px;
    background: var(--sc-primary-tint);
    color: var(--sc-fg);
    font-size: 12.5px;
    text-align: left;
    cursor: pointer;
  }
  .pl:hover {
    filter: brightness(0.97);
  }
  .pl .i {
    width: 16px;
    height: 16px;
    fill: var(--sc-primary-ink);
  }
  .pl.worse {
    background: var(--sc-notrec-bg);
  }
  .pl.worse .i {
    fill: var(--sc-notrec);
  }
  .cal-wrap {
    container: cal / inline-size;
  }
  .cal {
    /* The hours shown at once (--span of them) out of those laid out (--laid:
       all 24 in a boat with lights), and room for their scrollbar. */
    --track: 300px;
    --lane: 12px;
    display: grid;
    grid-template-columns: 44px repeat(7, minmax(0, 1fr)) var(--lane);
    grid-template-rows: auto var(--track) auto;
    gap: 10px 8px;
  }
  /* Every day's hours side by side, scrolling together through those laid out. */
  .cal-hours {
    grid-row: 2;
    grid-column: 1 / -1;
    overflow: hidden auto;
    overscroll-behavior: contain;
    scrollbar-width: thin;
  }
  .cal-day {
    display: grid;
    grid-template-columns: 44px repeat(7, minmax(0, 1fr));
    column-gap: 8px;
    /* As wide as the columns above and below, whatever the scrollbar takes. */
    width: calc(100cqi - var(--lane) - 8px);
    height: calc(var(--track) * var(--laid) / var(--span));
  }
  .cal-gutter {
    position: relative;
  }
  .cal-gutter span {
    position: absolute;
    right: 2px;
    top: calc(var(--t) * 100%);
    transform: translateY(-50%);
    color: var(--sc-fg3);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .cd {
    display: grid;
    grid-row: 1 / span 3;
    grid-column: var(--col);
    grid-template-rows: subgrid;
    min-width: 0;
  }
  /* The narrow layout's own hours for each day. */
  .cd-scroll {
    display: none;
  }
  .cd-head {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas: "wd wx" "date wx" "score score";
    align-items: center;
    column-gap: 6px;
    min-width: 0;
    padding: 8px 8px 6px;
    border: 0;
    border-radius: 10px;
    background: transparent;
    text-align: left;
    cursor: pointer;
  }
  .cd-head:hover {
    background: var(--sc-primary-tint);
  }
  .cd-wd {
    grid-area: wd;
    color: var(--sc-fg2);
    font-size: 11.5px;
    font-weight: 500;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
  .cd-date {
    grid-area: date;
    font-size: 26px;
    font-weight: 500;
    line-height: 1.15;
  }
  .today .cd-wd {
    color: var(--sc-primary-ink);
  }
  .today .cd-date {
    display: grid;
    justify-self: start;
    place-items: center;
    width: 36px;
    height: 36px;
    margin: 1px 0 1px -3px;
    border-radius: 50%;
    background: var(--sc-btn);
    color: var(--sc-btn-ink);
    font-size: 19px;
  }
  .cd-wx {
    display: grid;
    grid-area: wx;
    justify-items: end;
    gap: 2px;
    color: var(--sc-fg2);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }
  .cd-wx .wx {
    width: 30px;
    height: 30px;
  }
  .cd-score {
    display: flex;
    grid-area: score;
    align-items: center;
    gap: 8px;
    min-width: 0;
    margin-top: 8px;
  }
  .cd-score b {
    display: block;
    font-size: 13px;
    font-weight: 500;
  }
  .cd-score small {
    display: block;
    color: var(--sc-fg2);
    font-size: 11.5px;
  }
  .cd-off {
    color: var(--sc-fg2);
    font-size: 12px;
    line-height: 36px;
  }
  .cd-track {
    position: relative;
    min-height: 0;
  }
  .seg {
    position: absolute;
    left: 0;
    right: 0;
    top: calc(var(--s) * 100% + 1px);
    height: calc((var(--e) - var(--s)) * 100% - 2px);
    border-radius: 4px;
    background: var(--sc-h-poor);
  }
  .seg.night {
    display: grid;
    place-items: center;
    background: var(--sc-h-night);
    color: var(--sc-h-ink);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
  }
  .seg.night span {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    white-space: nowrap;
  }
  /* Sunrise and sunset sit at the edge of the night they end or start. */
  .seg.night.dawn {
    align-items: end;
    padding-bottom: 4px;
  }
  .seg.night.dusk {
    align-items: start;
    padding-top: 4px;
  }
  .seg.night .i {
    width: 14px;
    height: 14px;
  }
  /* With navigation lights, night darkens the hours under it instead. */
  .seg.night.veil {
    z-index: 1;
    background: var(--sc-h-veil);
    pointer-events: none;
  }
  .seg.night.veil span {
    padding: 1px 6px;
    border-radius: 999px;
    background: var(--sc-h-night);
  }
  .twilight {
    background: var(--sc-h-twilight);
  }
  .h-good {
    background: var(--sc-h-good);
  }
  .h-fair {
    background: var(--sc-h-fair);
  }
  .h-poor {
    background: var(--sc-h-poor);
  }
  .h-caution {
    background: var(--sc-h-caution);
  }
  .h-not_recommended {
    background: var(--sc-h-notrec);
  }
  .h-dangerous {
    background: var(--sc-h-danger);
  }
  .past {
    background: var(--sc-h-past)
      repeating-linear-gradient(135deg, var(--sc-h-hatch) 0 2px, transparent 2px 6px);
  }
  .off {
    background-image: repeating-linear-gradient(
      135deg,
      var(--sc-h-hatch) 0 2px,
      transparent 2px 6px
    );
  }
  .seg[data-hour]:hover {
    z-index: 1;
    box-shadow: inset 0 0 0 2px var(--sc-fg2);
  }
  .pill {
    position: absolute;
    z-index: 2;
    left: 4px;
    right: 4px;
    top: calc(var(--s) * 100% + 2px);
    height: calc((var(--e) - var(--s)) * 100% - 4px);
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
    padding: 5px 8px;
    overflow: hidden;
    border: 0;
    border-radius: 8px;
    background: var(--sc-event);
    box-shadow: 0 1px 3px rgba(5, 40, 60, 0.28);
    color: var(--sc-event-ink);
    text-align: left;
    cursor: pointer;
    container-type: inline-size;
  }
  .pill:hover {
    background: var(--sc-event-hover);
  }
  .pill .pt {
    display: flex;
    align-items: center;
    gap: 3px;
    max-width: 100%;
    overflow: hidden;
    font-size: 12px;
    font-weight: 700;
    line-height: 1.3;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .pill .ps {
    font-size: 11.5px;
    opacity: 0.9;
    white-space: nowrap;
  }
  .pill .pn {
    display: none;
    font-size: 12px;
    font-weight: 700;
  }
  .pill .pc {
    position: absolute;
    right: 6px;
    bottom: 5px;
    width: 16px;
    height: 16px;
    opacity: 0.95;
  }
  .pill .pstar {
    width: 12px;
    height: 12px;
  }
  .pill.added {
    background: var(--sc-event-added);
    box-shadow: inset 0 0 0 2px rgba(255, 255, 255, 0.6);
  }
  .pill.worse {
    box-shadow: inset 0 0 0 2px var(--sc-dot-notrec);
  }
  .pill.short .ps {
    display: none;
  }
  .pill.tiny .pc {
    display: none;
  }
  .nowline {
    position: absolute;
    z-index: 3;
    left: -2px;
    right: 0;
    top: calc(var(--s) * 100% - 1px);
    height: 2px;
    background: var(--sc-now);
    pointer-events: none;
  }
  .nowline::before {
    content: "";
    position: absolute;
    left: -2px;
    top: -3px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--sc-now);
  }
  .cd-axis {
    display: none;
  }
  .cd-info {
    display: grid;
    grid-row: 3;
    align-content: start;
    gap: 6px;
    min-width: 0;
    padding: 2px 6px 0;
    font-size: 12.5px;
  }
  .ci {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    font-variant-numeric: tabular-nums;
  }
  .ci .i {
    width: 15px;
    height: 15px;
    fill: var(--sc-fg3);
  }
  .ci .arr {
    width: 15px;
    height: 15px;
  }
  .cd-wins {
    display: none;
  }
  /* The sailor's hours that day, which can be changed for the date. */
  .hrs-set {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    padding: 0;
    border: 0;
    background: none;
    color: inherit;
    font: inherit;
    text-align: start;
    cursor: pointer;
  }
  .hrs-set span {
    overflow-wrap: anywhere;
    text-decoration: underline dotted var(--sc-fg3);
    text-underline-offset: 3px;
  }
  .hrs.changed {
    color: var(--sc-primary-ink);
    font-weight: 500;
  }
  .hrs.changed .i {
    fill: var(--sc-primary-ink);
  }
  .hrs-undo.icon-btn {
    width: 24px;
    height: 24px;
    margin: -4px 0;
  }
  .hrs-undo.icon-btn .i {
    width: 14px;
    height: 14px;
  }
  .sizes {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding-top: 4px;
  }
  .sz {
    display: inline-grid;
    place-items: center;
    width: 24px;
    height: 22px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
  }
  .sz.mine {
    box-shadow:
      0 0 0 2px var(--sc-card),
      0 0 0 3.5px var(--sc-fg);
  }
  .conf {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--sc-fg2);
    font-size: 12px;
  }
  .dots {
    display: inline-flex;
    gap: 3px;
  }
  .dots i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--sc-line);
  }
  .dots i.on {
    background: var(--sc-fg2);
  }
  @container cal (max-width: 760px) {
    .cal {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: none;
      row-gap: 10px;
    }
    .cal-hours {
      display: none;
    }
    .cd {
      grid-row: auto;
      grid-column: 1;
      grid-template-rows: none;
      row-gap: 8px;
      padding: 10px 12px 12px;
      border: 1px solid var(--sc-line);
      border-radius: 12px;
    }
    /* Each day's hours scroll sideways through those laid out. */
    .cd-scroll {
      display: block;
      overflow: auto hidden;
      overscroll-behavior-x: contain;
      scrollbar-width: thin;
    }
    .cd-hours {
      width: calc(100% * var(--laid) / var(--span));
    }
    .cd-head {
      grid-template-columns: auto minmax(0, 1fr) auto;
      grid-template-areas: "wd score wx" "date score wx";
      column-gap: 12px;
      padding: 2px 0;
    }
    .cd-score {
      margin-top: 0;
    }
    .cd-track {
      height: 34px;
    }
    .seg {
      top: 0;
      bottom: 0;
      left: calc(var(--s) * 100% + 1px);
      right: auto;
      width: calc((var(--e) - var(--s)) * 100% - 2px);
      height: auto;
    }
    .seg.night span {
      display: none;
    }
    .pill {
      top: 2px;
      bottom: 2px;
      left: calc(var(--s) * 100% + 2px);
      right: auto;
      flex-direction: row;
      align-items: center;
      gap: 4px;
      width: calc((var(--e) - var(--s)) * 100% - 4px);
      height: auto;
      padding: 0 6px;
    }
    .pill .pt,
    .pill .ps {
      display: none;
    }
    .pill .pn {
      display: block;
    }
    .pill .pc,
    .pill.tiny .pc {
      display: block;
      position: static;
      margin-left: auto;
    }
    .nowline {
      top: -3px;
      bottom: -3px;
      left: calc(var(--s) * 100% - 1px);
      width: 2px;
      height: auto;
    }
    .nowline::before {
      left: -3px;
      top: -3px;
    }
    .cd-axis {
      position: relative;
      display: block;
      height: 14px;
      margin-top: 4px;
    }
    .cd-axis span {
      position: absolute;
      left: calc(var(--s) * 100%);
      transform: translateX(-50%);
      color: var(--sc-fg3);
      font-size: 10.5px;
      white-space: nowrap;
    }
    .cd-axis span:first-child {
      transform: none;
    }
    .cd-axis span:last-child {
      transform: translateX(-100%);
    }
    .cd-info {
      grid-row: auto;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      column-gap: 12px;
      padding: 0;
    }
    .cd-wins,
    .hrs,
    .sizes,
    .conf {
      grid-column: 1 / -1;
    }
    .cd-wins {
      display: flex;
      font-weight: 500;
    }
  }
  @container (max-width: 46px) {
    .pill .pc {
      display: none !important;
    }
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
    color: var(--sc-fg2);
    font-size: 12px;
  }
  .lg {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .lg .i {
    width: 15px;
    height: 15px;
    fill: var(--sc-fg3);
  }
  .sw {
    display: inline-block;
    width: 18px;
    height: 12px;
    border-radius: 3px;
  }
  .sw.night {
    background: var(--sc-h-night);
  }
  .sw-pill {
    background: var(--sc-event);
  }
  .legend-note {
    margin: 0;
  }

  /* Day view */
  .dstrip {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 6px;
  }
  .ds {
    display: grid;
    justify-items: center;
    gap: 1px;
    min-width: 0;
    padding: 8px 4px 7px;
    border: 1px solid var(--sc-line);
    border-radius: 12px;
    background: var(--sc-card);
    cursor: pointer;
  }
  .ds:hover {
    border-color: var(--sc-primary);
  }
  .ds-wd {
    color: var(--sc-fg2);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .ds-d {
    font-size: 20px;
    font-weight: 500;
    line-height: 1.2;
  }
  .ds-sc {
    display: flex;
    align-items: center;
    gap: 5px;
    color: var(--sc-fg2);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }
  .ds-sc i {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--band, var(--sc-line));
  }
  .ds[aria-pressed="true"] {
    border-color: var(--sc-primary);
    background: var(--sc-primary-tint);
  }
  .ds[aria-pressed="true"] .ds-wd {
    color: var(--sc-primary-ink);
  }
  @media (max-width: 520px) {
    .dstrip {
      gap: 4px;
    }
    .ds {
      padding: 6px 2px;
    }
    .ds-sc span {
      display: none;
    }
  }
  .dayview {
    display: grid;
    grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
    gap: 16px;
  }
  @container panel (max-width: 900px) {
    .dayview {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  .verdict {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 4px 16px;
  }
  .verdict .ring {
    width: 76px;
    height: 76px;
  }
  .v-title {
    margin: 2px 0 0;
    font-size: 22px;
    font-weight: 500;
  }
  .v-sub {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    margin: 4px 0 0;
    color: var(--sc-fg2);
    font-size: 13px;
  }
  .v-wins {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 14px;
  }
  .win-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-height: 40px;
    padding: 0 14px 0 12px;
    border: 0;
    border-radius: 12px;
    background: var(--sc-event);
    color: var(--sc-event-ink);
    font-variant-numeric: tabular-nums;
    cursor: pointer;
  }
  .win-btn:hover {
    background: var(--sc-event-hover);
  }
  .win-btn.added {
    background: var(--sc-event-added);
    box-shadow: inset 0 0 0 2px rgba(255, 255, 255, 0.55);
  }
  .win-btn .act {
    padding-left: 8px;
    border-left: 1px solid rgba(255, 255, 255, 0.35);
    font-size: 12.5px;
    opacity: 0.9;
  }
  .advice {
    display: grid;
    gap: 9px;
    max-width: 72ch;
    margin: 16px 0 0;
    padding: 0;
    list-style: none;
  }
  .advice li {
    display: grid;
    grid-template-columns: 20px minmax(0, 1fr);
    align-items: start;
    gap: 10px;
  }
  .advice .i,
  .advice .arr {
    width: 18px;
    height: 18px;
    margin-top: 1px;
    color: var(--sc-fg3);
    fill: var(--sc-fg3);
  }
  .advice li.hot .i {
    fill: var(--sc-dot-notrec);
  }
  .ai {
    display: grid;
    gap: 6px;
    max-width: 72ch;
    margin-top: 16px;
    padding: 12px 14px;
    border: 1px solid var(--sc-line);
    border-radius: 12px;
    background: var(--sc-sunk);
  }
  .ai p {
    margin: 0;
  }
  .ai-ask {
    justify-items: start;
    padding: 0;
    border: 0;
    background: none;
  }
  .ai-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .ai .i {
    width: 18px;
    height: 18px;
    fill: var(--sc-primary-ink);
  }
  .ai-text {
    line-height: 1.5;
  }
  .ai-failed {
    color: var(--sc-danger);
  }
  .sizes-list {
    display: grid;
    gap: 10px;
  }
  .size {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 2px 10px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--sc-line2);
  }
  .size:last-child {
    padding-bottom: 0;
    border-bottom: 0;
  }
  .size .nm {
    font-weight: 500;
  }
  .size .why {
    grid-column: 1 / -1;
    color: var(--sc-fg2);
    font-size: 12px;
  }
  .tag {
    display: inline-block;
    margin-left: 6px;
    padding: 1px 7px;
    border-radius: 999px;
    background: var(--sc-primary-tint);
    color: var(--sc-primary-ink);
    font-size: 11px;
    font-weight: 500;
    vertical-align: 1px;
  }
  .chart {
    position: relative;
    width: 100%;
    min-height: 120px;
  }
  .chart svg {
    display: block;
    width: 100%;
    height: auto;
    overflow: visible;
    touch-action: pan-y;
  }
  .ax {
    font-family: var(--sc-font);
    font-size: 11px;
    fill: var(--sc-fg2);
  }
  .ax-strong {
    font-family: var(--sc-font);
    font-size: 11px;
    font-weight: 500;
    fill: var(--sc-fg);
  }
  .xh {
    stroke: var(--sc-fg2);
    stroke-width: 1;
    pointer-events: none;
  }
  .tbl-wrap {
    overflow-x: auto;
  }
  table.hours {
    min-width: 100%;
    border-collapse: separate;
    border-spacing: 3px;
    font-size: 13px;
    font-variant-numeric: tabular-nums;
  }
  .hours th {
    color: var(--sc-fg2);
    font-size: 12px;
    font-weight: 500;
    white-space: nowrap;
  }
  .hours th[scope="row"] {
    position: sticky;
    left: 0;
    z-index: 1;
    padding-right: 10px;
    background: var(--sc-card);
    text-align: left;
  }
  .hours td {
    min-width: 44px;
    padding: 5px 4px;
    border-radius: 6px;
    text-align: center;
    white-space: nowrap;
  }
  .hours td.is-past {
    opacity: 0.45;
  }
  .rate {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 500;
  }
  .score-pill {
    display: inline-grid;
    place-items: center;
    min-width: 32px;
    height: 22px;
    padding: 0 6px;
    border-radius: 7px;
    background: var(--band);
    color: var(--band-ink);
    font-weight: 700;
  }
  .sources dl {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: 6px 16px;
    margin: 0;
  }
  .sources dt {
    color: var(--sc-fg2);
  }
  .sources dd {
    margin: 0;
  }
  .warn-text {
    display: block;
    margin-top: 4px;
    white-space: pre-line;
    color: var(--sc-fg2);
  }
  .sources .notice {
    display: block;
    margin-top: 4px;
    color: var(--sc-fg2);
    font-size: 0.85em;
  }
  @media (max-width: 600px) {
    .sources dl {
      grid-template-columns: minmax(0, 1fr);
    }
    .sources dd {
      margin-bottom: 6px;
    }
  }

  /* Settings */
  .sec {
    display: grid;
    gap: 14px;
  }
  .sec-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px 16px;
  }
  .sec-head p {
    margin: 2px 0 0;
  }
  .people {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 12px;
  }
  .person {
    display: grid;
    align-content: start;
    gap: 10px;
    min-width: 0;
    padding: 14px;
    border: 1px solid var(--sc-line);
    border-radius: 12px;
  }
  .person-top {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 12px;
  }
  .person-top h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 500;
  }
  .avatar {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: var(--av);
    color: #ffffff;
    font-size: 17px;
    font-weight: 500;
  }
  .avatar.sm {
    width: 32px;
    height: 32px;
    font-size: 14px;
  }
  .skill-line {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    border-radius: 10px;
    background: var(--sc-sunk);
  }
  .skill-line b {
    display: block;
    font-weight: 500;
  }
  .bars {
    display: inline-flex;
    flex: none;
    align-items: flex-end;
    gap: 2px;
    height: 16px;
  }
  .bars i {
    width: 5px;
    border-radius: 2px;
    background: var(--sc-line);
  }
  .bars i:nth-child(1) {
    height: 6px;
  }
  .bars i:nth-child(2) {
    height: 11px;
  }
  .bars i:nth-child(3) {
    height: 16px;
  }
  .bars i.on {
    background: var(--sc-primary-ink);
  }
  .rows {
    display: grid;
  }
  .row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr) auto;
    align-items: center;
    gap: 10px 24px;
    padding: 14px 0;
    border-top: 1px solid var(--sc-line2);
  }
  .row:first-child {
    padding-top: 4px;
    border-top: 0;
  }
  .row h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 500;
  }
  .row .small {
    display: block;
  }
  @container panel (max-width: 760px) {
    .row {
      grid-template-columns: minmax(0, 1fr) auto;
    }
    .row > :nth-child(2) {
      grid-column: 1 / -1;
      grid-row: 2;
    }
  }
  .lims {
    display: grid;
    gap: 10px;
  }
  .lim {
    display: grid;
    grid-template-columns: 52px minmax(0, 1fr) 22px;
    align-items: start;
    gap: 10px;
    color: var(--sc-fg2);
    font-size: 12px;
  }
  .lim-track {
    position: relative;
    padding-bottom: 16px;
  }
  .lim-bar {
    display: flex;
    gap: 2px;
    height: 8px;
  }
  .lim-bar i {
    flex: var(--w) 1 0;
    min-width: 2px;
  }
  .lim-bar i:first-child {
    border-radius: 999px 0 0 999px;
  }
  .lim-bar i:last-child {
    border-radius: 0 999px 999px 0;
  }
  .lb-good {
    background: var(--sc-dot-good);
  }
  .lb-caution {
    background: var(--sc-dot-caution);
  }
  .lb-not_recommended {
    background: var(--sc-dot-notrec);
  }
  .lb-dangerous {
    background: var(--sc-dot-danger);
  }
  .lim-t {
    position: absolute;
    top: 10px;
    left: calc(var(--a) * 100%);
    transform: translateX(-50%);
    color: var(--sc-fg);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
  }
  .srcs {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: 3px 14px;
    margin: 0;
    font-size: 12.5px;
  }
  .srcs dt {
    color: var(--sc-fg2);
  }
  .srcs dd {
    margin: 0;
  }
  .cal-info {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: start;
    gap: 10px;
    color: var(--sc-fg2);
    font-size: 13px;
  }
  .cal-info .i {
    margin-top: 1px;
    fill: var(--sc-fg3);
  }
  .cal-info p {
    max-width: 80ch;
    margin: 0;
  }
  .sub {
    margin: 4px 0 0;
    font-size: 14px;
    font-weight: 500;
  }
  .plist {
    display: grid;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .prow {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 4px 12px;
    padding: 10px 12px;
    border-radius: 12px;
    background: var(--sc-sunk);
  }
  .prow > .i {
    fill: var(--sc-primary-ink);
  }
  .prow.worse > .i {
    fill: var(--sc-notrec);
  }
  .prow b {
    font-weight: 500;
  }
  .prow .small {
    display: block;
  }
  .pstat {
    display: block;
    font-size: 12.5px;
  }
  .prow.worse .pstat {
    color: var(--sc-notrec);
  }
  .empty {
    max-width: 80ch;
    margin: 0;
    color: var(--sc-fg2);
    font-size: 13px;
  }
  .auto-rows {
    display: grid;
    gap: 8px;
  }
  .auto-row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 4px 12px;
    padding: 10px 12px;
    border: 1px solid var(--sc-line);
    border-radius: 12px;
  }
  .auto-row b {
    display: block;
    font-weight: 500;
  }

  /* Dialogs and forms */
  dialog {
    width: min(560px, calc(100vw - 32px));
    max-height: calc(100dvh - 40px);
    padding: 0;
    border: 0;
    border-radius: 18px;
    background: var(--sc-card);
    color: var(--sc-fg);
    box-shadow: var(--sc-shadow-pop);
  }
  dialog::backdrop {
    background: var(--sc-scrim);
  }
  dialog form {
    display: flex;
    flex-direction: column;
    max-height: calc(100dvh - 40px);
  }
  .dlg-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 16px 14px 6px 22px;
  }
  .dlg-head h2 {
    margin: 0;
    font-size: 19px;
    font-weight: 500;
  }
  .dlg-body {
    display: grid;
    gap: 16px;
    padding: 8px 22px 10px;
    overflow: auto;
  }
  .dlg-foot {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    padding: 12px 18px 18px 14px;
    border-top: 1px solid var(--sc-line2);
  }
  .grow {
    flex: 1;
  }
  .fld {
    display: grid;
    gap: 6px;
    min-width: 0;
    margin: 0;
    padding: 0;
    border: 0;
  }
  .lbl {
    padding: 0;
    color: var(--sc-fg2);
    font-size: 12px;
    font-weight: 500;
  }
  legend.lbl {
    margin-bottom: 6px;
  }
  .hint {
    margin: 0;
    color: var(--sc-fg2);
    font-size: 12px;
  }
  .fld-err {
    margin: 0;
    color: var(--sc-danger);
    font-size: 12px;
  }
  dialog input[type="text"],
  dialog input[type="number"],
  dialog select,
  .sec select {
    width: 100%;
    min-height: 40px;
    padding: 8px 10px;
    border: 1px solid var(--sc-line);
    border-radius: 10px;
    background: var(--sc-card);
    color: var(--sc-fg);
  }
  .sec select {
    max-width: 420px;
  }
  input[type="range"] {
    width: 100%;
    accent-color: var(--sc-btn);
  }
  .two {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }
  .opts {
    display: grid;
    gap: 8px;
  }
  .opt {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border: 1px solid var(--sc-line);
    border-radius: 12px;
    cursor: pointer;
  }
  .opt:has(input:checked) {
    border-color: var(--sc-primary);
    background: var(--sc-primary-tint);
  }
  .opt input,
  .check input {
    flex: none;
    width: 18px;
    height: 18px;
    margin: 0;
    accent-color: var(--sc-btn);
  }
  .opt-t {
    display: grid;
    gap: 1px;
    min-width: 0;
  }
  .opt-t b {
    font-weight: 500;
  }
  .opt-t span {
    color: var(--sc-fg2);
    font-size: 12.5px;
  }
  .checks {
    display: grid;
    gap: 8px;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
  }
  .daypick {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  /* A sailor's days, a row each: whether they sail, and from and until when. */
  .dayhours {
    display: grid;
    grid-template-columns: auto repeat(2, minmax(0, 1fr));
    align-items: center;
    gap: 6px 8px;
  }
  .dayhours > .lbl {
    font-size: 12px;
  }
  .dayhours .fld-err {
    grid-column: 1 / -1;
  }
  .dayhours select {
    min-height: 34px;
    padding: 4px 8px;
  }
  .dayhours select:disabled {
    opacity: 0.45;
  }
  .dayt {
    position: relative;
    display: inline-block;
  }
  .dayt input {
    position: absolute;
    inset: 0;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }
  .dayt span {
    display: inline-grid;
    place-items: center;
    min-width: 46px;
    height: 34px;
    padding: 0 8px;
    border: 1px solid var(--sc-line);
    border-radius: 999px;
    color: var(--sc-fg2);
    font-size: 13px;
    font-weight: 500;
  }
  .dayt input:checked + span {
    border-color: var(--sc-btn);
    background: var(--sc-btn);
    color: var(--sc-btn-ink);
  }
  .dayt input:focus-visible + span {
    outline: 2px solid var(--sc-focus);
    outline-offset: 2px;
  }
  .evt {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 2px 12px;
    padding: 12px 14px;
    border-radius: 14px;
    background: var(--sc-sea);
    color: var(--sc-sea-ink);
  }
  .evt > .i {
    grid-row: span 2;
    width: 28px;
    height: 28px;
  }
  .evt b {
    font-size: 15px;
    font-weight: 500;
  }
  .evt span {
    color: var(--sc-sea-ink2);
    font-size: 12.5px;
  }
  .evt .ring {
    --ring-v: var(--sc-sea-ink);
    --ring-t: var(--sc-sea-chip);
    --ring-fg: var(--sc-sea-ink);
    grid-row: span 2;
    width: 44px;
    height: 44px;
  }
  .desc {
    padding: 10px 12px;
    border-radius: 10px;
    background: var(--sc-sunk);
    color: var(--sc-fg2);
    font-size: 12.5px;
    line-height: 1.5;
  }
  .form-err {
    margin: 0;
    padding: 8px 12px;
    border-radius: 10px;
    background: var(--sc-danger-bg);
    color: var(--sc-danger);
    font-size: 13px;
  }
  .lims-preview {
    padding: 12px;
    border-radius: 12px;
    background: var(--sc-sunk);
  }

  /* Tooltip and toast, shown in the top layer. Closed ones stay hidden even
     though their own display rules would show them. */
  .tip:not(:popover-open),
  .toast:not(:popover-open) {
    display: none;
  }
  .tip {
    position: fixed;
    inset: auto;
    max-width: 280px;
    margin: 0;
    padding: 8px 11px;
    border: 1px solid var(--sc-line);
    border-radius: 9px;
    background: var(--sc-raised);
    box-shadow: var(--sc-shadow-pop);
    color: var(--sc-fg);
    font-size: 12.5px;
    line-height: 1.5;
    pointer-events: none;
  }
  .tip b {
    font-weight: 500;
  }
  .tip .chip {
    margin-right: 6px;
  }
  .toast {
    position: fixed;
    inset: auto auto calc(20px + var(--sc-inset-bottom)) 50%;
    display: flex;
    align-items: center;
    gap: 8px;
    max-width: calc(100vw - 32px);
    margin: 0;
    padding: 10px 16px;
    border: 0;
    border-radius: 10px;
    background: var(--sc-fg);
    box-shadow: var(--sc-shadow-pop);
    color: var(--sc-card);
    font-size: 13.5px;
    transform: translateX(-50%);
  }
  .toast .i {
    fill: var(--sc-card);
  }
  @media (prefers-reduced-motion: reduce) {
    .switch input,
    .switch input::after {
      transition: none;
    }
  }
`;
