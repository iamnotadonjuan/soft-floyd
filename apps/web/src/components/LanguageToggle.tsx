import { LOCALE_NAMES, LOCALES, useI18n } from "../i18n/I18nProvider";

// Compact EN / ES switch shown in every page header, onboarding included,
// so a new rider can pick a language before answering anything.
export default function LanguageToggle() {
  const { locale, setLocale, m } = useI18n();

  return (
    <div role="group" aria-label={m.common.language} className="lang-toggle">
      {LOCALES.map((option) => (
        <button
          key={option}
          type="button"
          lang={option}
          title={LOCALE_NAMES[option]}
          aria-label={LOCALE_NAMES[option]}
          aria-pressed={locale === option}
          onClick={() => setLocale(option)}
        >
          {option.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
