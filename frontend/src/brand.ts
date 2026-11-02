import { html, svg } from "lit";

/** The SailCast icon: a sloop's sails over two waves, under the sun. */
export const brandIcon = html`<svg viewBox="0 0 512 512" role="img" aria-label="SailCast">
  <defs>
    <linearGradient id="sc-bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0855b1" />
      <stop offset="1" stop-color="#010e54" />
    </linearGradient>
    <radialGradient id="sc-glow" cx=".76" cy=".24" r=".62">
      <stop offset="0" stop-color="#4fa5d8" stop-opacity=".5" />
      <stop offset="1" stop-color="#4fa5d8" stop-opacity="0" />
    </radialGradient>
    <linearGradient id="sc-main" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ffffff" />
      <stop offset="1" stop-color="#daeaf7" />
    </linearGradient>
    <clipPath id="sc-clip"><rect width="512" height="512" rx="116" /></clipPath>
  </defs>
  <g clip-path="url(#sc-clip)">
    <rect width="512" height="512" fill="url(#sc-bg)" />
    <rect width="512" height="512" fill="url(#sc-glow)" />
    <circle cx="394" cy="132" r="44" fill="#daeaf7" opacity=".95" />
    <path d="M226 116 L226 400 L106 400 C124 312 166 210 226 116 Z" fill="#4fa5d8" />
    <path d="M244 56 C320 140 364 252 372 400 L244 400 Z" fill="url(#sc-main)" />
    <path
      d="M0 372 C70 342 150 346 224 372 C298 398 370 402 440 376 C470 365 494 360 512 361 L512 512 L0 512 Z"
      fill="#0855b1"
    />
    <path
      d="M0 428 C76 402 150 404 226 428 C302 452 380 454 456 430 C480 422 498 418 512 417 L512 512 L0 512 Z"
      fill="#4fa5d8"
    />
    <path
      d="M0 428 C76 402 150 404 226 428 C302 452 380 454 456 430 C480 422 498 418 512 417"
      fill="none"
      stroke="#daeaf7"
      stroke-width="8"
      stroke-linecap="round"
      opacity=".75"
    />
  </g>
</svg>`;

/**
 * Two waves for the bottom of the welcome banner, shaped like the icon's. The
 * panel colors them through the `back`, `front` and `crest` classes.
 */
export const bannerWaves = svg`
  <path class="back" d="M0 50 C150 20 300 24 450 50 C600 76 750 80 900 54 C1000 37 1100 32 1200 36 L1200 120 L0 120 Z" />
  <path class="front" d="M0 84 C160 58 310 60 460 84 C610 108 770 110 920 86 C1030 70 1120 64 1200 66 L1200 120 L0 120 Z" />
  <path class="crest" d="M0 84 C160 58 310 60 460 84 C610 108 770 110 920 86 C1030 70 1120 64 1200 66" />
`;
