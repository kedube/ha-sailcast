import en from "./translations/en.json";

interface Strings {
  [key: string]: string | Strings;
}

// English is built in. Each other language is a file of its own, loaded the
// first time someone uses it, so the panel doesn't carry all twelve.
const FILES = import.meta.glob<Strings>(["./translations/*.json", "!./translations/en.json"], {
  import: "default",
});
const LANGUAGES: Record<string, Strings> = { en };

/** The language SailCast has for one, such as "pt-BR", or "de" for "de-CH". */
function available(language: string): string | undefined {
  return [language, language.split("-")[0]].find(
    (code) => code in LANGUAGES || `./translations/${code}.json` in FILES,
  );
}

/**
 * Load a language's strings, if SailCast has that language and hasn't loaded
 * it yet. Resolves to whether new strings arrived.
 */
export async function loadLanguage(language: string | undefined): Promise<boolean> {
  const code = language && available(language);
  if (!code || code in LANGUAGES) return false;
  LANGUAGES[code] = await FILES[`./translations/${code}.json`]();
  return true;
}

/**
 * Return a panel string in the user's language, falling back to English.
 * Keys are dotted paths, and `{name}` placeholders are filled from `values`.
 */
export function localize(
  language: string | undefined,
  key: string,
  values: Record<string, string | number> = {},
): string {
  const code = language && available(language);
  const strings = (code && LANGUAGES[code]) || en;
  const text = lookup(strings, key) ?? lookup(en, key) ?? key;
  return text.replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    name in values ? String(values[name]) : placeholder,
  );
}

function lookup(strings: Strings, key: string): string | undefined {
  let node: string | Strings | undefined = strings;
  for (const part of key.split(".")) {
    if (typeof node !== "object") return undefined;
    node = node[part];
  }
  return typeof node === "string" ? node : undefined;
}
