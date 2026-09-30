import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  AUTH_FAILURE_MESSAGES,
  AuthApiError,
  requestLogin,
  requestResetPassword,
  requestSignup,
  verifyOtp,
  verifyTotp,
} from "../api/auth";
import type { OtpIssued, Profile } from "../api/auth";

interface OtpScreenProps {
  issued: OtpIssued;
  mode: "signup" | "login" | "reset" | "totp";
  displayName: string;
  password: string;
  onVerified: (user: Profile) => void;
  onBack: () => void;
}

const OTP_LENGTH = 6;
const MAX_OTP_ATTEMPTS = 3;

export function OtpScreen({
  issued,
  mode,
  displayName,
  password,
  onVerified,
  onBack,
}: OtpScreenProps) {
  const [current, setCurrent] = useState(issued);
  const [digits, setDigits] = useState<string[]>(() => {
    const initial = (
      issued.delivery === "on_screen" ? (issued.otp_code ?? "") : ""
    ).slice(0, OTP_LENGTH);
    return Array.from({ length: OTP_LENGTH }, (_, i) => initial[i] ?? "");
  });
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(60);
  const [message, setMessage] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const [wrongAttempts, setWrongAttempts] = useState(0);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  const emailed = current.delivery === "email" || current.otp_code === null;
  const code = digits.join("");
  const isComplete = code.length === OTP_LENGTH;

  useEffect(() => {
    const firstEmptyIndex = digits.findIndex((digit) => !digit);
    const focusTarget = firstEmptyIndex === -1 ? 0 : firstEmptyIndex;
    inputRefs.current[focusTarget]?.focus();
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return;

    const interval = setInterval(() => {
      setCooldown((previous) => (previous > 0 ? previous - 1 : 0));
    }, 1000);

    return () => clearInterval(interval);
  }, [cooldown]);

  function handleDigitChange(index: number, value: string) {
    const cleaned = value.replace(/\D/g, "");

    if (!cleaned) {
      const next = [...digits];
      next[index] = "";
      setDigits(next);
      return;
    }

    if (cleaned.length > 1) {
      const next = [...digits];
      for (let i = 0; i < cleaned.length && index + i < OTP_LENGTH; i++) {
        const character = cleaned[i];
        if (character !== undefined) {
          next[index + i] = character;
        }
      }
      setDigits(next);
      const targetIndex = Math.min(index + cleaned.length, OTP_LENGTH - 1);
      inputRefs.current[targetIndex]?.focus();
      return;
    }

    const next = [...digits];
    next[index] = cleaned;
    setDigits(next);

    if (index < OTP_LENGTH - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  }

  function handleKeyDown(
    index: number,
    event: React.KeyboardEvent<HTMLInputElement>,
  ) {
    if (event.key === "Backspace") {
      if (!digits[index] && index > 0) {
        event.preventDefault();
        const next = [...digits];
        next[index - 1] = "";
        setDigits(next);
        inputRefs.current[index - 1]?.focus();
      }
    } else if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      inputRefs.current[index - 1]?.focus();
    } else if (event.key === "ArrowRight" && index < OTP_LENGTH - 1) {
      event.preventDefault();
      inputRefs.current[index + 1]?.focus();
    }
  }

  function handlePaste(event: React.ClipboardEvent<HTMLInputElement>) {
    event.preventDefault();

    const pasted = event.clipboardData
      .getData("text")
      .replace(/\D/g, "")
      .slice(0, OTP_LENGTH);

    if (!pasted) return;

    const next = Array.from(
      { length: OTP_LENGTH },
      (_, i) => pasted[i] ?? "",
    );
    setDigits(next);

    const targetIndex = Math.min(pasted.length, OTP_LENGTH - 1);
    inputRefs.current[targetIndex]?.focus();
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (busy || locked) return;

    if (code.length < OTP_LENGTH) {
      setMessage("Please enter all 6 digits of your verification code.");
      return;
    }

    setBusy(true);
    setMessage(null);

    try {
      const session =
        mode === "totp"
          ? await verifyTotp(current.email, code.trim())
          : await verifyOtp(current.email, code.trim());
      onVerified(session.user);
    } catch (error) {
      if (error instanceof AuthApiError && error.code === "INVALID_OTP") {
        const nextAttempts = wrongAttempts + 1;
        setWrongAttempts(nextAttempts);

        if (nextAttempts >= MAX_OTP_ATTEMPTS) {
          setLocked(true);
          setDigits(Array(OTP_LENGTH).fill(""));
          setMessage("Too many incorrect codes. Request a new one.");
        } else {
          setMessage(
            `Incorrect code. ${MAX_OTP_ATTEMPTS - nextAttempts} attempts remaining.`,
          );
        }
      } else if (
        error instanceof AuthApiError &&
        error.code === "OTP_LOCKED"
      ) {
        setLocked(true);
        setDigits(Array(OTP_LENGTH).fill(""));
        setMessage("Too many incorrect codes. Request a new one.");
      } else {
        setMessage(
          error instanceof AuthApiError
            ? AUTH_FAILURE_MESSAGES[error.kind]
            : AUTH_FAILURE_MESSAGES.unexpected,
        );
      }
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
          : mode === "reset"
            ? await requestResetPassword(current.email, password)
            : await (async () => {
                const result = await requestLogin(current.email, password);
                if (result.kind !== "email_otp") {
                  throw new AuthApiError("unexpected");
                }
                return result.issued;
              })();
      setCurrent(next);
      setLocked(false);
      setWrongAttempts(0);

      const nextCode = (
        next.delivery === "on_screen" ? (next.otp_code ?? "") : ""
      ).slice(0, OTP_LENGTH);

      setDigits(
        Array.from({ length: OTP_LENGTH }, (_, i) => nextCode[i] ?? ""),
      );
      setCooldown(60);
      inputRefs.current[0]?.focus();
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
      <div className="auth-canvas">
        <header className="auth-brand-header">
          <div className="auth-brand-logo" aria-hidden="true">
            <svg width="48" height="48" viewBox="0 0 40 40" fill="none">
              <defs>
                <linearGradient
                  id="brand-otp-grad"
                  x1="0%"
                  y1="0%"
                  x2="100%"
                  y2="100%"
                >
                  <stop offset="0%" stopColor="#2f6dff" />
                  <stop offset="100%" stopColor="#8b5cf6" />
                </linearGradient>
              </defs>
              <rect
                width="40"
                height="40"
                rx="12"
                fill="url(#brand-otp-grad)"
              />
              <path
                d="M20 9L29 14.5V25.5L20 31L11 25.5V14.5L20 9Z"
                stroke="white"
                strokeWidth="2"
                strokeLinejoin="round"
                fill="none"
              />
              <circle cx="20" cy="20" r="3.5" fill="white" />
              <path
                d="M20 23.5V31M11 14.5L17 18M29 14.5L23 18"
                stroke="white"
                strokeWidth="1.75"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <p className="eyebrow">Two-Factor Security</p>
          <h1 className="auth-card__title">Enter your code</h1>
          <p className="auth-card__lede">
            {mode === "totp" ? (
              <>
                Enter the 6-digit code from your authenticator app for{" "}
                <strong>{current.email}</strong>.
              </>
            ) : emailed ? (
              <>
                Check Gmail for a 6-digit code sent to{" "}
                <strong>{current.email}</strong>. The code is valid for{" "}
                {Math.round(current.expires_in_seconds / 60)} minutes.
              </>
            ) : (
              <>
                We issued a one-time code for{" "}
                <strong>{current.email}</strong>. The code is valid for{" "}
                {Math.round(current.expires_in_seconds / 60)} minutes.
              </>
            )}
          </p>
        </header>

        <section className="glass auth-card">
          <div className="auth-card__back-row">
            <button
              className="auth-card__back-btn text-btn text-btn--subtle"
              onClick={onBack}
              type="button"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Back
            </button>
          </div>

          {mode === "totp" || emailed || current.otp_code === null ? null : (
            <aside className="otp-inbox" aria-live="polite">
              <p className="otp-inbox__label">Your verification code</p>
              <p className="otp-inbox__code">{current.otp_code}</p>
              <p className="otp-inbox__hint">
                Shown here because Gmail SMTP is not configured in this
                environment.
              </p>
            </aside>
          )}

          {mode === "totp" || !emailed ? null : (
            <aside className="otp-inbox" aria-live="polite">
              <p className="otp-inbox__label">Two-factor email</p>
              <p className="otp-inbox__hint">
                Open the message from OIAP HR Assistant and enter the code
                below. The code is not shown in this app when Gmail SMTP is
                configured.
              </p>
            </aside>
          )}

          <form className="stack" onSubmit={handleSubmit}>
            <div className="field">
              <label className="field__label" id="otp-inputs-label">
                6-digit verification code
              </label>
              <div
                className="otp-inputs"
                role="group"
                aria-labelledby="otp-inputs-label"
                onPaste={handlePaste}
              >
                {digits.map((digit, index) => (
                  <input
                    key={index}
                    ref={(element) => {
                      inputRefs.current[index] = element;
                    }}
                    aria-label={`Digit ${index + 1} of 6`}
                    autoComplete={index === 0 ? "one-time-code" : "off"}
                    className={`otp-digit ${digit ? "is-filled" : ""}`}
                    disabled={locked}
                    inputMode="numeric"
                    maxLength={1}
                    onChange={(event) =>
                      handleDigitChange(index, event.target.value)
                    }
                    onFocus={(event) => event.target.select()}
                    onKeyDown={(event) => handleKeyDown(index, event)}
                    pattern="[0-9]*"
                    required
                    type="text"
                    value={digit}
                  />
                ))}
              </div>
            </div>

            {message === null ? null : (
              <p className="notice notice--error" role="alert">
                {message}
              </p>
            )}

            <button
              className="btn btn--primary"
              disabled={busy || locked || !isComplete}
              type="submit"
            >
              {busy ? "Checking…" : "Verify and continue"}
            </button>
            {mode === "totp" ? null : (
              <button
                className="btn btn--ghost"
                disabled={busy || cooldown > 0}
                onClick={() => {
                  void resend();
                }}
                type="button"
              >
                {cooldown > 0 ? `Resend code in ${cooldown}s` : "Resend code"}
              </button>
            )}
          </form>
        </section>

        <footer className="auth-footer">
          <p className="auth-footer__text">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <rect
                width="18"
                height="11"
                x="3"
                y="11"
                rx="2"
                ry="2"
              />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            Session Guard Active • Encrypted Token Exchange
          </p>
        </footer>
      </div>
    </div>
  );
}