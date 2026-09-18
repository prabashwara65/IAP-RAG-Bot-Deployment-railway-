import { useState } from "react";
import type { FormEvent } from "react";
import {
  AUTH_FAILURE_MESSAGES,
  AuthApiError,
  requestLogin,
  requestSignup,
  verifyOtp,
} from "../api/auth";
import type { OtpIssued, Profile } from "../api/auth";

interface OtpScreenProps {
  issued: OtpIssued;
  mode: "signup" | "login";
  displayName: string;
  password: string;
  onVerified: (user: Profile) => void;
  onBack: () => void;
}

export function OtpScreen({
  issued,
  mode,
  displayName,
  password,
  onVerified,
  onBack,
}: OtpScreenProps) {
  const [code, setCode] = useState(
    issued.delivery === "on_screen" ? (issued.otp_code ?? "") : "",
  );
  const [current, setCurrent] = useState(issued);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const emailed = current.delivery === "email" || current.otp_code === null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const session = await verifyOtp(current.email, code.trim());
      onVerified(session.user);
    } catch (error) {
      setMessage(
        error instanceof AuthApiError
          ? AUTH_FAILURE_MESSAGES[error.kind]
          : AUTH_FAILURE_MESSAGES.unexpected,
      );
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setBusy(true);
    setMessage(null);
    try {
      const next =
        mode === "signup"
          ? await requestSignup(current.email, displayName, password)
          : await requestLogin(current.email, password);
      setCurrent(next);
      setCode(next.delivery === "on_screen" ? (next.otp_code ?? "") : "");
    } catch (error) {
      setMessage(
        error instanceof AuthApiError
          ? AUTH_FAILURE_MESSAGES[error.kind]
          : AUTH_FAILURE_MESSAGES.unexpected,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-layout">
      <section className="glass auth-card">
        <button className="text-btn" onClick={onBack} type="button">
          Back
        </button>
        <h1 className="auth-card__title">Enter your code</h1>
        <p className="auth-card__lede">
          {emailed ? (
            <>
              Check Gmail for a 6-digit code sent to <strong>{current.email}</strong>.
              It expires in {Math.round(current.expires_in_seconds / 60)} minutes.
            </>
          ) : (
            <>
              We issued a one-time code for <strong>{current.email}</strong>. It
              expires in {Math.round(current.expires_in_seconds / 60)} minutes.
            </>
          )}
        </p>

        {emailed || current.otp_code === null ? null : (
          <aside className="otp-inbox" aria-live="polite">
            <p className="otp-inbox__label">Your verification code</p>
            <p className="otp-inbox__code">{current.otp_code}</p>
            <p className="otp-inbox__hint">
              Shown here because Gmail SMTP is not configured in this environment.
            </p>
          </aside>
        )}

        {emailed ? (
          <aside className="otp-inbox" aria-live="polite">
            <p className="otp-inbox__label">Two-factor email</p>
            <p className="otp-inbox__hint">
              Open the message from OIAP HR Assistant and enter the code below.
              The code is not shown in this app when Gmail SMTP is configured.
            </p>
          </aside>
        ) : null}

        <form className="stack" onSubmit={handleSubmit}>
          <label className="field">
            <span className="field__label">6-digit code</span>
            <input
              autoComplete="one-time-code"
              className="field__input field__input--otp"
              inputMode="numeric"
              maxLength={6}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
              pattern="\d{6}"
              required
              value={code}
            />
          </label>

          {message === null ? null : (
            <p className="notice notice--error" role="alert">
              {message}
            </p>
          )}

          <button className="btn btn--primary" disabled={busy} type="submit">
            {busy ? "Checking…" : "Verify and continue"}
          </button>
          <button
            className="btn btn--ghost"
            disabled={busy}
            onClick={() => {
              void resend();
            }}
            type="button"
          >
            Resend code
          </button>
        </form>
      </section>
    </div>
  );
}
