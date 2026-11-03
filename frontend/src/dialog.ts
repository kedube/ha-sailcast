/**
 * A modal dialog the panel opens and removes again. Each kind of dialog
 * renders its body and footer; this gives them the frame, the error line,
 * closing, and a delete button that asks for a second select.
 */
import { html, LitElement, nothing, type TemplateResult } from "lit";

import type { Ctx } from "./context";
import { icon } from "./glyphs";
import { styles } from "./styles";

export abstract class ScDialog extends LitElement {
  static override styles = styles;
  static override properties = {
    ctx: { attribute: false },
    error: { state: true },
    busy: { state: true },
    armed: { state: true },
  };

  declare ctx: Ctx;
  declare error?: string;
  declare busy: boolean;
  /** Whether the delete button has been selected once. */
  declare armed: boolean;

  constructor() {
    super();
    this.busy = false;
    this.armed = false;
  }

  protected abstract heading(): string;
  protected abstract body(): TemplateResult;
  protected abstract footer(): TemplateResult;
  /** Do what the dialog is for; return an error to show, or nothing to close. */
  protected abstract submit(form: HTMLFormElement): Promise<string | void>;

  protected t(key: string, values?: Record<string, string | number>): string {
    return this.ctx.t(key, values);
  }

  protected get dialog(): HTMLDialogElement | null {
    return this.renderRoot.querySelector("dialog");
  }

  protected override firstUpdated(): void {
    this.dialog?.showModal();
  }

  /** Close the dialog; the panel then removes it. */
  close(): void {
    this.dialog?.close();
  }

  protected override render(): TemplateResult {
    return html`<dialog
      aria-labelledby="title"
      @close=${() => this.dispatchEvent(new Event("closed"))}
      @cancel=${() => this.close()}
    >
      <form novalidate @submit=${this.onSubmit}>
        <div class="dlg-head">
          <h2 id="title">${this.heading()}</h2>
          <button
            type="button"
            class="icon-btn"
            aria-label=${this.t("dialog.close")}
            @click=${() => this.close()}
          >
            ${icon("close")}
          </button>
        </div>
        <div class="dlg-body">
          ${this.error ? html`<p class="form-err" role="alert">${this.error}</p>` : nothing}
          ${this.body()}
        </div>
        <div class="dlg-foot">${this.footer()}</div>
      </form>
    </dialog>`;
  }

  private onSubmit = async (event: SubmitEvent): Promise<void> => {
    event.preventDefault();
    if (this.busy) return;
    this.busy = true;
    try {
      const error = await this.submit(event.target as HTMLFormElement);
      if (error) {
        this.error = error;
      } else {
        this.close();
      }
    } catch (err) {
      this.error = errorText(err);
    } finally {
      this.busy = false;
    }
  };

  /** Footer buttons: Cancel and a submit button. */
  protected actions(label: string, disabled = false): TemplateResult {
    return html`<span class="grow"></span>
      <button type="button" class="btn btn-text" @click=${() => this.close()}>
        ${this.t("dialog.cancel")}
      </button>
      <button type="submit" class="btn btn-primary" ?disabled=${disabled || this.busy}>
        ${label}
      </button>`;
  }

  /** A delete button that asks for a second select before it runs. */
  protected deleteButton(name: string, run: () => Promise<string | void>): TemplateResult {
    return html`<button
      type="button"
      class="btn btn-danger"
      ?disabled=${this.busy}
      @click=${async () => {
        if (!this.armed) {
          this.armed = true;
          return;
        }
        this.busy = true;
        try {
          const error = await run();
          if (error) this.error = error;
          else this.close();
        } catch (err) {
          this.error = errorText(err);
        } finally {
          this.busy = false;
          this.armed = false;
        }
      }}
    >
      ${icon("del")}<span
        >${this.armed ? this.t("dialog.delete_confirm", { name }) : this.t("dialog.delete")}</span
      >
    </button>`;
  }
}

/** The message in an error from Home Assistant or the browser. */
export function errorText(err: unknown): string {
  if (typeof err === "object" && err && "message" in err) return String(err.message);
  return String(err);
}

/** The value of a form field, by name. */
export function value(form: HTMLFormElement, name: string): string {
  const field = form.elements.namedItem(name);
  if (field instanceof RadioNodeList) return field.value;
  if (field instanceof HTMLInputElement || field instanceof HTMLSelectElement) return field.value;
  if (field instanceof HTMLTextAreaElement) return field.value;
  return "";
}

/** The checked values of checkboxes that share a name. */
export function checked(form: HTMLFormElement, name: string): string[] {
  return [...form.querySelectorAll<HTMLInputElement>(`input[name="${name}"]:checked`)].map(
    (input) => input.value,
  );
}

/** A number field's value, or null when it's empty. */
export function numberOrNull(form: HTMLFormElement, name: string): number | null {
  const text = value(form, name).trim();
  if (!text) return null;
  const number = Number(text.replace(",", "."));
  return Number.isFinite(number) ? number : null;
}

/** Define an element, unless a build loaded earlier already has. */
export function define(name: string, element: CustomElementConstructor): void {
  if (!customElements.get(name)) customElements.define(name, element);
}
