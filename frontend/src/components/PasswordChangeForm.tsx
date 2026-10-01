import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { AuthApiError, changePassword } from "../api/auth";

export function PasswordChangeForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const submitting = useRef(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    setError(null);
    setNotice(null);
    if (next !== confirm) { setError("New passwords do not match."); return; }
    if (next === current) { setError("Choose a new password different from your current password."); return; }
    if (next.length < 8 || next.length > 128 || next.trim() !== next || !/[A-Z]/.test(next) || !/[0-9]/.test(next) || !/[^A-Za-z0-9]/.test(next)) {
      setError("Password must be 8–128 characters, include a capital letter, a number, and a symbol, and have no spaces at either end.");
      return;
    }
    submitting.current = true;
    setBusy(true);
    try {
      await changePassword(current, next);
      setCurrent(""); setNext(""); setConfirm("");
      setNotice("Password updated successfully.");
    } catch (failure) {
      setError(failure instanceof AuthApiError ? failure.message : "Password could not be updated. Please try again.");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <form className="glass stack profile-page__settings" aria-labelledby="password-change-title" onSubmit={(event) => { void submit(event); }} aria-busy={busy}>
      <h2 id="password-change-title" className="password-change__heading">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
        Change password
      </h2>
      <label className="field"><span className="field__label">Current password</span><input className="field__input" type="password" autoComplete="current-password" required maxLength={128} disabled={busy} value={current} onChange={(event) => { setCurrent(event.target.value); setError(null); setNotice(null); }} /></label>
      <label className="field"><span className="field__label">New password</span><input className="field__input" type="password" autoComplete="new-password" required minLength={8} maxLength={128} disabled={busy} value={next} aria-describedby="password-change-hint" onChange={(event) => { setNext(event.target.value); setError(null); setNotice(null); }} /></label>
      <p className="password-change__hint" id="password-change-hint">Use 8–128 characters with a capital letter, a number, and a symbol.</p>
      <label className="field"><span className="field__label">Confirm new password</span><input className="field__input" type="password" autoComplete="new-password" required minLength={8} maxLength={128} disabled={busy} value={confirm} onChange={(event) => { setConfirm(event.target.value); setError(null); setNotice(null); }} /></label>
      {error && <p className="notice notice--error" role="alert">{error}</p>}
      {notice && <p className="notice notice--ok" role="status">{notice}</p>}
      <button className="btn btn--primary password-change__submit" type="submit" disabled={busy}>{busy ? "Updating…" : "Update password"}</button>
    </form>
  );
}
