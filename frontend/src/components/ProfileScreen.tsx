import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  AUTH_FAILURE_MESSAGES,
  AuthApiError,
  deleteAvatar,
  updateProfile,
  uploadAvatar,
} from "../api/auth";
import type { Profile, ThemePreference } from "../api/auth";
import { AvatarMark } from "./AvatarMark";
import { ThemeToggle } from "./ThemeToggle";
import { TwoFactorSettings } from "./TwoFactorSettings";
import { PasswordChangeForm } from "./PasswordChangeForm";
import { ROLE_LABELS } from "../api/adminUsers";

interface ProfileScreenProps {
  user: Profile;
  avatarUrl: string | null;
  onUpdated: (user: Profile) => void;
  onAvatarChanged: () => void;
  onClose: () => void;
}

export function ProfileScreen({
  user,
  avatarUrl,
  onUpdated,
  onAvatarChanged,
  onClose,
}: ProfileScreenProps) {
  const [displayName, setDisplayName] = useState(user.display_name);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [photoChanged, setPhotoChanged] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => { titleRef.current?.focus(); }, []);

  const hasUnsavedName = displayName.trim() !== user.display_name;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!hasUnsavedName) return;

    setBusy(true);
    setMessage(null);
    setNotice(null);

    try {
      const updated = await updateProfile({
        display_name: displayName.trim(),
      });

      onUpdated(updated);
      setNotice("Profile saved.");
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

  async function changeTheme(theme: ThemePreference) {
    try {
      const updated = await updateProfile({ theme });
      onUpdated(updated);
    } catch (error) {
      setMessage(
        error instanceof AuthApiError
          ? AUTH_FAILURE_MESSAGES[error.kind]
          : AUTH_FAILURE_MESSAGES.unexpected,
      );
    }
  }

  async function onFile(file: File | undefined) {
    if (file === undefined) {
      return;
    }

    setBusy(true);
    setMessage(null);

    try {
      const updated = await uploadAvatar(file);

      onUpdated(updated);
      onAvatarChanged();
      setPhotoChanged(true);
      setNotice("Profile image updated.");
    } catch (error) {
      setMessage(
        error instanceof AuthApiError
          ? AUTH_FAILURE_MESSAGES[error.kind]
          : AUTH_FAILURE_MESSAGES.unexpected,
      );
    } finally {
      setBusy(false);

      if (fileInput.current !== null) {
        fileInput.current.value = "";
      }
    }
  }

  async function removePhoto() {
    setBusy(true);
    setMessage(null);

    try {
      const updated = await deleteAvatar();

      onUpdated(updated);
      onAvatarChanged();
      setPhotoChanged(false);
      setNotice("Profile image removed.");
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
    <main className="profile-page" aria-labelledby="profile-page-title">
      <header className="profile-page__header">
        <button className="profile-page__back" type="button" onClick={onClose}>
          <span aria-hidden="true">←</span> Back to Assistant
        </button>
        <h1 id="profile-page-title" className="profile-page__title" ref={titleRef} tabIndex={-1}>My Profile</h1>
        <p className="page__subtitle">Manage your personal details, appearance, and account security.</p>
      </header>
      <div className="profile-page__layout">
      <aside className="glass profile-page__summary" aria-label="Account summary">
        <AvatarMark
          imageUrl={avatarUrl}
          name={user.display_name}
          size="lg"
        />

        <div className="profile-page__identity">
          <h2>{user.display_name}</h2>
          <p>{user.email}</p>
          <span className={`role-badge role-badge--${user.role ?? "user"}`}>{ROLE_LABELS[user.role ?? "user"]}</span>
        </div>
        <div className="stack profile-page__photo-actions">
          <input
            accept="image/jpeg,image/png,image/webp"
            className="sr-only"
            onChange={(event) => {
              void onFile(event.target.files?.[0]);
            }}
            ref={fileInput}
            type="file"
          />

          {!photoChanged ? (
            <button
              className="btn btn--primary"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
              type="button"
            >
              Change photo
            </button>
          ) : null}

          {user.has_avatar ? (
            <button
              className="btn btn--ghost"
              disabled={busy}
              onClick={() => {
                void removePhoto();
              }}
              type="button"
            >
              Remove photo
            </button>
          ) : null}
        </div>
      </aside>

      <div className="stack profile-page__forms">
      <form
        className="glass stack profile-page__settings"
        onSubmit={save}
        aria-labelledby="profile-settings-title"
      >
        <h2 id="profile-settings-title">Account settings</h2>
        <label className="field">
          <span className="field__label">
            Display name
          </span>

          <input
            className="field__input"
            maxLength={80}
            onChange={(event) =>
              setDisplayName(event.target.value)
            }
            required
            value={displayName}
          />
        </label>

        <label className="field">
          <span className="field__label">
            Email
          </span>

          <input
            className="field__input"
            disabled
            readOnly
            value={user.email}
          />
        </label>

        <TwoFactorSettings
          onMessage={setMessage}
          onNotice={setNotice}
          onUpdated={onUpdated}
          user={user}
        />

        <div className="field">
          <span className="field__label">
            Appearance
          </span>

          <ThemeToggle
            onChange={(theme) => void changeTheme(theme)}
            theme={user.theme}
          />
        </div>

        {message === null ? null : (
          <p
            className="notice notice--error"
            role="alert"
          >
            {message}
          </p>
        )}

        {notice === null ? null : (
          <p
            className="notice notice--ok"
            role="status"
          >
            {notice}
          </p>
        )}

        {hasUnsavedName ? (
          <button
            className="btn btn--primary"
            disabled={busy}
            type="submit"
          >
            {busy ? "Saving…" : "Save profile"}
          </button>
        ) : null}
      </form>
      <PasswordChangeForm />
      </div>
      </div>
    </main>
  );
}