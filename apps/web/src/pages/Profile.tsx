import { useState } from "react";

import { api } from "../api/client";
import type { AccountOut } from "../api/types";
import LanguageToggle from "../components/LanguageToggle";
import { useI18n } from "../i18n/I18nProvider";

export default function Profile({ account, onBack, onSignOut }: {
  account: AccountOut;
  onBack: () => void;
  onSignOut: () => void;
}) {
  const { m } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  async function signOut() {
    setBusy(true);
    setError(false);
    try {
      await api.logout();
      onSignOut();
    } catch {
      setError(true);
      setBusy(false);
    }
  }
  return (
    <main className="app-shell min-h-screen">
      <div className="page-wrap max-w-4xl">
        <header className="mb-12 flex items-center justify-between gap-4">
          <span className="brand">Soft Floyd / {m.auth.profile}</span>
          <div className="flex items-center gap-4">
            <button className="text-button" onClick={onBack}>{m.common.back}</button>
            <LanguageToggle />
          </div>
        </header>
        <p className="eyebrow mb-3">{m.auth.account}</p>
        <h1 className="display-title">{m.auth.profileTitle}</h1>
        <p className="body-muted mt-4">{m.auth.profileIntro}</p>
        <section className="surface mt-9 flex flex-wrap items-center gap-5 p-6 sm:p-8">
          {account.picture_url ?
            <img src={account.picture_url} alt="" referrerPolicy="no-referrer"
              className="h-20 w-20 rounded-full object-cover" /> :
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-[#dce8d8] font-serif text-3xl text-[#31563e]" aria-hidden="true">
              {account.name.charAt(0).toUpperCase()}
            </div>}
          <div className="min-w-0">
            <h2 className="font-serif text-2xl text-[#243e2c]">{account.name}</h2>
            <p className="body-muted mt-1 break-all">{account.email}</p>
            <p className="body-muted mt-2 text-xs">{m.auth.accountId(account.id)}</p>
          </div>
        </section>
        <button className="secondary-button mt-8" disabled={busy} onClick={signOut}>
          {m.auth.signOut}
        </button>
        {error && <p className="notice-error mt-4" role="alert">{m.auth.signOutError}</p>}
      </div>
    </main>
  );
}
