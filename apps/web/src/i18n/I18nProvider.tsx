import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import en, { type Messages } from "./en";
import es from "./es";

export const LOCALES = ["en", "es"] as const;
export type Locale = (typeof LOCALES)[number];

// Shown in each language's own name, whatever the current UI language.
export const LOCALE_NAMES: Record<Locale, string> = { en: "English", es: "Español" };

const MESSAGES: Record<Locale, Messages> = { en, es };
// Passed to toLocaleString/Intl for dates and numbers.
const INTL_LOCALE: Record<Locale, string> = { en: "en-US", es: "es" };

// The language choice lives in this browser only for now. When the
// profile grows a settings field, load and save it here instead — nothing
// else in the app knows where it's stored.
const STORAGE_KEY = "soft-floyd.locale";

function readStoredLocale(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return LOCALES.find((l) => l === stored) ?? "en";
  } catch {
    return "en";
  }
}

interface I18nValue {
  locale: Locale;
  intlLocale: string;
  m: Messages;
  setLocale: (locale: Locale) => void;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage blocked (private mode) — the choice just won't survive a reload.
    }
  }, []);

  const value = useMemo(
    () => ({ locale, intlLocale: INTL_LOCALE[locale], m: MESSAGES[locale], setLocale }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside <I18nProvider>");
  return value;
}
