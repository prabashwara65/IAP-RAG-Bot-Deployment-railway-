import { useRef, useState } from "react";
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
    <section className="glass profile-panel">
      <button
        className="profile-panel__close"
        type="button"
        onClick={onClose}
        aria-label="Close profile"
        title="Close"
      >
        ×
      </button>

      <h2 className="profile-panel__title">
        Your profile
      </h2>

      <p className="page__subtitle">
        Manage how you appear in the assistant, including your photo and theme.
      </p>

      <div className="profile-hero">
        <AvatarMark
          imageUrl={avatarUrl}
          name={user.display_name}
          size="lg"
        />

        <div className="stack">
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
      </div>

      <form
        className="stack"
        onSubmit={save}
      >
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
    </section>
  );
}