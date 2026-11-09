/**
 * The AI briefing at the top of the week view: the AI's write-up of the
 * sailor's week across their spots and boats, with up to three of SailCast's
 * windows picked out. A pick shows SailCast's own times and score, and opens
 * its day. The day view shows the briefing's note for that day.
 */
import { html, nothing, type TemplateResult } from "lit";

import type { Ctx } from "./context";
import { band, localTime } from "./format";
import { icon } from "./glyphs";
import type { BriefingPick } from "./types";

/** When a briefing was written: the time today, or the day and time before. */
export function writtenText(ctx: Ctx, made: string): string {
  const { t, fmt } = ctx;
  const zone = fmt.zone;
  const today = localTime(ctx.forecast?.now ?? new Date().toISOString(), zone).date;
  const date = localTime(made, zone).date;
  if (date === today) return t("ai.written", { time: fmt.clock(made) });
  return t("ai.written_day", { day: fmt.weekday(date, "long"), time: fmt.clock(made) });
}

/** The forecast changed since the briefing was written: say so, and offer a new one. */
export function aiChanged(ctx: Ctx): TemplateResult {
  const { t } = ctx;
  return html`<div class="ai-changed">
    <p class="small">${t("ai.changed")}</p>
    <button
      type="button"
      class="btn btn-tonal"
      ?disabled=${ctx.briefingBusy}
      aria-busy=${ctx.briefingBusy ? "true" : "false"}
      @click=${() => ctx.act.writeBriefing()}
    >
      ${icon("ai")}${ctx.briefingBusy ? t("ai.writing") : t("ai.update")}
    </button>
  </div>`;
}

function pickButton(ctx: Ctx, pick: BriefingPick): TemplateResult {
  const { t, fmt, config } = ctx;
  const spot = config.spots.find((item) => item.id === pick.spot)?.name ?? "";
  const boat = config.boats.find((item) => item.id === pick.boat)?.name ?? "";
  const day =
    ctx.forecast?.days[0]?.date === pick.date ? t("week.today") : fmt.weekday(pick.date, "long");
  return html`<button type="button" class="brief-pick" @click=${() => ctx.act.openPick(pick)}>
    <span class="brief-when"
      ><b>${day}</b> ${fmt.span(pick.start, pick.end)}
      <span class="brief-score">${pick.score} · ${t(`band_word.${band(pick.score)}`)}</span></span
    >
    <span class="brief-where">${spot} · ${boat}</span>
    ${pick.why ? html`<span class="brief-why">${pick.why}</span>` : nothing}
  </button>`;
}

/** The briefing card, with AI on: the briefing, or that it's being written. */
export function briefingCard(ctx: Ctx): TemplateResult | typeof nothing {
  const { t } = ctx;
  if (!ctx.config.ai) return nothing;
  const briefing = ctx.briefing;
  const failed = ctx.briefingError
    ? html`<p class="small ai-failed" role="alert">${ctx.briefingError}</p>`
    : nothing;
  if (!briefing) {
    if (briefing === undefined && !ctx.briefingBusy && !ctx.briefingError) return nothing;
    return html`<section class="card brief brief-ask" aria-label=${t("ai.title")}>
      <div class="ai-head">${icon("ai")}<b>${t("ai.title")}</b></div>
      ${
        ctx.briefingBusy
          ? html`<p class="small" aria-live="polite">${t("ai.writing")}</p>`
          : html`${failed}
              <div>
                <button type="button" class="btn btn-tonal" @click=${() => ctx.act.writeBriefing()}>
                  ${icon("ai")}${ctx.briefingError ? t("ai.again") : t("ai.button")}
                </button>
              </div>`
      }
    </section>`;
  }
  return html`<section class="card brief" aria-label=${t("ai.title")}>
    <div class="ai-head">
      ${icon("ai")}<b>${t("ai.title")}</b>
      <span class="small">${writtenText(ctx, briefing.made)}</span>
    </div>
    ${briefing.current ? nothing : aiChanged(ctx)}
    <p class="brief-head">${briefing.headline}</p>
    <p class="ai-text">${briefing.summary}</p>
    ${
      briefing.picks.length
        ? html`<div class="brief-picks" role="list" aria-label=${t("ai.picks")}>
            ${briefing.picks.map(
              (pick) => html`<div role="listitem">${pickButton(ctx, pick)}</div>`,
            )}
          </div>`
        : nothing
    }
    ${
      briefing.recheck
        ? html`<p class="small brief-recheck">${icon("clock")}<span>${briefing.recheck}</span></p>`
        : nothing
    }
    <p class="small">${t("ai.note")}</p>
    ${failed}
  </section>`;
}
