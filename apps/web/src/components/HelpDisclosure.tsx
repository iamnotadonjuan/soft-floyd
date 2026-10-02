import { useI18n } from "../i18n/I18nProvider";

export default function HelpDisclosure({ title, children }: { title: string; children: string }) {
  const { m } = useI18n();
  return (
    <details className="help-disclosure">
      <summary aria-label={m.help.aboutAria(title)}>?</summary>
      <p className="body-muted mt-2 text-sm leading-relaxed">{children}</p>
    </details>
  );
}
