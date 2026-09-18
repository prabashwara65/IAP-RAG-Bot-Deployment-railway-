import { useState } from "react";
import type { FormEvent } from "react";
import {
  AUTH_FAILURE_MESSAGES,
  AuthApiError,
  requestLogin,
  requestSignup,
} from "../api/auth";
import type { OtpIssued } from "../api/auth";

interface AuthScreenProps {
  onOtpIssued: (
    issued: OtpIssued,
    mode: "signup" | "login",
    displayName: string,
    password: string,
  ) => void;
}

export function AuthScreen({ onOtpIssued }: AuthScreenProps) {
  const [mode, setMode] = useState<"signup" | "login">("signup");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const issued =
        mode === "signup"
          ? await requestSignup(email.trim(), displayName.trim(), password)
          : await requestLogin(email.trim(), password);
      onOtpIssued(issued, mode, displayName.trim(), password);
    } catch (error) {
      const kind = error instanceof AuthApiError ? error.kind : "unexpected";
      setMessage(
        kind === "unauthenticated"
          ? "That email or password is not correct."
          : AUTH_FAILURE_MESSAGES[kind],
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-layout">
      <section className="glass auth-card">
        <p className="eyebrow">Office Intelligence</p>
        <h1 className="auth-card__title">OIAP HR Assistant</h1>
        <p className="auth-card__lede">
          Sign in with your email and password. We then email a one-time code to
          your Gmail inbox as two-factor authentication.
        </p>

        <div className="segmented" role="tablist" aria-label="Account">
          <button
            className={mode === "signup" ? "segmented__btn is-active" : "segmented__btn"}
            onClick={() => setMode("signup")}
            type="button"
          >
            Sign up
          </button>
          <button
            className={mode === "login" ? "segmented__btn is-active" : "segmented__btn"}
            onClick={() => setMode("login")}
            type="button"
          >
            Log in
          </button>
        </div>

        <form className="stack" onSubmit={handleSubmit}>
          {mode === "signup" ? (
            <label className="field">
              <span className="field__label">Display name</span>
              <input
                autoComplete="name"
                className="field__input"
                maxLength={80}
                onChange={(event) => setDisplayName(event.target.value)}
                required
                value={displayName}
              />
            </label>
          ) : null}

          <label className="field">
            <span className="field__label">Work email</span>
            <input
              autoComplete="email"
              className="field__input"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </label>

          <label className="field">
            <span className="field__label">Password</span>
            <input
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              className="field__input"
              minLength={8}
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>

          {message === null ? null : (
            <p className="notice notice--error" role="alert">
              {message}
            </p>
          )}

          <button className="btn btn--primary" disabled={busy} type="submit">
            {busy
              ? "Sending code…"
              : mode === "signup"
                ? "Send verification code"
                : "Send sign-in code"}
          </button>
        </form>
      </section>
    </div>
  );
}
