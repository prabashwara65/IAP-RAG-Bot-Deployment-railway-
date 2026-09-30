import { useState } from "react";
import {
  AUTH_FAILURE_MESSAGES,
  AuthApiError,
  beginTotpSetup,
  confirmTotpSetup,
  setTwoFactorMethod,
} from "../api/auth";
import type { Profile, TotpSetup } from "../api/auth";

interface TwoFactorSettingsProps {
  user: Profile;
  onUpdated: (user: Profile) => void;
  onMessage: (message: string | null) => void;
  onNotice: (notice: string | null) => void;
}

export function TwoFactorSettings({
  user,
  onUpdated,
  onMessage,
  onNotice,
}: TwoFactorSettingsProps) {
  const method = user.two_factor_method;
  const enabled = method !== "none";
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const authenticatorSelected = method === "totp" || setup !== null;

  async function run(action: () => Promise<void>) {
    setBusy(true);
    onMessage(null);
    onNotice(null);
    try {
      await action();
    } catch (error) {
      onMessage(
        error instanceof AuthApiError
          ? AUTH_FAILURE_MESSAGES[error.kind]
          : AUTH_FAILURE_MESSAGES.unexpected,
      );
    } finally {
      setBusy(false);
    }
  }

  function toggle() {
    void run(async () => {
      const updated = await setTwoFactorMethod(enabled ? "none" : "email_otp");
      setSetup(null);
      setCode("");
      onUpdated(updated);
      onNotice(
        updated.two_factor_method === "none"
          ? "Two-factor authentication is off."
          : "Email codes are on.",
      );
    });
  }

  function chooseEmail() {
    if (method === "email_otp" && setup === null) {
      return;
    }
    void run(async () => {
      const updated = await setTwoFactorMethod("email_otp");
      setSetup(null);
      setCode("");
      onUpdated(updated);
      onNotice("Email codes are on. Authenticator sign-in is off.");
    });
  }

  function startSetup() {
    void run(async () => {
      const issued = await beginTotpSetup();
      setSetup(issued);
      setCode("");
    });
  }

  function chooseAuthenticator() {
    if (method === "totp" || setup !== null) {
      return;
    }
    startSetup();
  }

  function confirm() {
    void run(async () => {
      const updated = await confirmTotpSetup(code);
      setSetup(null);
      setCode("");
      onUpdated(updated);
      onNotice("Authenticator app is on. Email codes are off.");
    });
  }

  return (
    <aside className="security-card">
      <div className="security-card__head">
        <div>
          <p className="security-card__label">Two-factor authentication</p>
          <p className="security-card__title">
            {enabled ? "On" : "Off"}
          </p>
        </div>
        <button
          aria-checked={enabled}
          aria-label={enabled ? "Turn off two-factor authentication" : "Turn on two-factor authentication"}
          className={enabled ? "switch is-on" : "switch"}
          disabled={busy}
          onClick={toggle}
          role="switch"
          type="button"
        >
          <span className="switch__thumb" />
        </button>
      </div>

      {enabled ? (
        <>
          <p className="security-card__hint">
            Only one method can be on at a time. Use Google Authenticator, Microsoft
            Authenticator, or Authy for the app option.
          </p>
          <div className="factor-options" role="radiogroup" aria-label="Two-factor method">
            <button
              aria-checked={!authenticatorSelected}
              className={
                authenticatorSelected ? "factor-option" : "factor-option is-selected"
              }
              disabled={busy}
              onClick={chooseEmail}
              role="radio"
              type="button"
            >
              <span className="factor-option__mark" aria-hidden="true" />
              <span>
                <span className="factor-option__title">Email OTP via Gmail</span>
                <span className="factor-option__hint">
                  After your password, we send a 6-digit code to {user.email}.
                </span>
              </span>
            </button>
            <button
              aria-checked={authenticatorSelected}
              className={
                authenticatorSelected ? "factor-option is-selected" : "factor-option"
              }
              disabled={busy}
              onClick={chooseAuthenticator}
              role="radio"
              type="button"
            >
              <span className="factor-option__mark" aria-hidden="true" />
              <span>
                <span className="factor-option__title">Authenticator app</span>
                <span className="factor-option__hint">
                  After your password, enter the 6-digit code from your authenticator app.
                </span>
              </span>
            </button>
          </div>

          {method === "totp" && setup === null ? (
            <div className="factor-setup">
              <p className="security-card__hint">
                Authenticator sign-in is on for this account. Email codes are off.
              </p>
              <button
                className="btn btn--ghost"
                disabled={busy}
                onClick={startSetup}
                type="button"
              >
                Set up 2FA
              </button>
            </div>
          ) : null}

          {setup !== null ? (
            <div className="factor-setup">
              <p className="security-card__title">Set up your authenticator</p>
              <p className="security-card__hint">
                Scan the QR code, or enter the secret by hand. The previous method stays
                on until you confirm this code.
              </p>
              {setup.qr_svg.trimStart().startsWith("<svg") ? (
                <div className="factor-setup__center">
                  <div
                    className="factor-setup__qr"
                    dangerouslySetInnerHTML={{ __html: setup.qr_svg }}
                  />
                </div>
              ) : null}
              <p className="factor-setup__secret">Secret: {setup.secret}</p>
              <label className="field">
                <span className="field__label">6-digit code</span>
                <input
                  autoComplete="one-time-code"
                  className="field__input"
                  inputMode="numeric"
                  maxLength={6}
                  onChange={(event) => {
                    setCode(event.target.value.replace(/\D/g, "").slice(0, 6));
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      if (code.length === 6 && !busy) {
                        confirm();
                      }
                    }
                  }}
                  placeholder="6-digit code"
                  value={code}
                />
              </label>
              <button
                className="btn btn--primary"
                disabled={busy || code.length !== 6}
                onClick={confirm}
                type="button"
              >
                {busy ? "Checking…" : "Confirm and enable"}
              </button>
            </div>
          ) : null}
        </>
      ) : (
        <p className="security-card__hint">
          Sign-in uses your password only. Turn this on to require an email code or an
          authenticator app.
        </p>
      )}
    </aside>
  );
}
