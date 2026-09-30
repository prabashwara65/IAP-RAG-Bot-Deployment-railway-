import { useCallback, useEffect, useState } from "react";
import {
  fetchAvatarBlob,
  fetchProfile,
  logout as logoutRequest,
  updateProfile,
} from "./api/auth";
import type { OtpIssued, Profile, ThemePreference } from "./api/auth";
import { getAccessToken, setAccessToken } from "./api/session";
import { AppHeader } from "./components/AppHeader";
import { AuthScreen } from "./components/AuthScreen";
import { ChatWorkspace } from "./components/ChatWorkspace";
import { OtpScreen } from "./components/OtpScreen";
import { LogoutConfirmModal } from "./components/LogoutConfirmModal";
import { ProfileScreen } from "./components/ProfileScreen";

type Screen = "auth" | "otp" | "chat" | "profile";

function applyTheme(theme: ThemePreference) {
  const root = document.documentElement;

  if (theme === "system") {
    const dark = window.matchMedia(
      "(prefers-color-scheme: dark)",
    ).matches;

    root.dataset.theme = dark ? "dark" : "light";
    return;
  }

  root.dataset.theme = theme;
}

export function App() {
  const [screen, setScreen] = useState<Screen>("auth");
  const [user, setUser] = useState<Profile | null>(null);

  const [otp, setOtp] = useState<{
    issued: OtpIssued;
    mode: "signup" | "login" | "reset" | "totp";
    name: string;
    password: string;
    email: string;
  } | null>(null);

  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);

  const [logoutOpen, setLogoutOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const loadAvatar = useCallback(async (profile: Profile) => {
    if (!profile.has_avatar) {
      setAvatarUrl((previous) => {
        if (previous !== null) {
          URL.revokeObjectURL(previous);
        }

        return null;
      });

      return;
    }

    const blob = await fetchAvatarBlob();

    if (blob === null) {
      setAvatarUrl(null);
      return;
    }

    const url = URL.createObjectURL(blob);

    setAvatarUrl((previous) => {
      if (previous !== null) {
        URL.revokeObjectURL(previous);
      }

      return url;
    });
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function restore() {
      const token = getAccessToken();

      if (token === null) {
        setBooting(false);
        return;
      }

      try {
        const profile = await fetchProfile();

        if (cancelled) {
          return;
        }

        setUser(profile);
        applyTheme(profile.theme);
        setScreen("chat");

        await loadAvatar(profile);
      } catch {
        setAccessToken(null);
      } finally {
        if (!cancelled) {
          setBooting(false);
        }
      }
    }

    void restore();

    return () => {
      cancelled = true;
    };
  }, [loadAvatar]);

  useEffect(() => {
    const media = window.matchMedia(
      "(prefers-color-scheme: dark)",
    );

    const sync = () => {
      if (user?.theme === "system" || user === null) {
        applyTheme(user?.theme ?? "system");
      }
    };

    media.addEventListener("change", sync);

    applyTheme(user?.theme ?? "system");

    return () => {
      media.removeEventListener("change", sync);
    };
  }, [user]);

  async function handleLogout() {
    await logoutRequest();

    setUser(null);
    setOtp(null);
    setScreen("auth");

    setAvatarUrl((previous) => {
      if (previous !== null) {
        URL.revokeObjectURL(previous);
      }

      return null;
    });
  }

  async function confirmLogout() {
    if (isLoggingOut) {
      return;
    }

    setIsLoggingOut(true);

    try {
      await handleLogout();
      setLogoutOpen(false);
    } finally {
      setIsLoggingOut(false);
    }
  }

  async function handleTheme(theme: ThemePreference) {
    if (user === null) {
      applyTheme(theme);
      return;
    }

    try {
      const updated = await updateProfile({
        theme,
      });

      setUser(updated);
      applyTheme(updated.theme);
    } catch {
      applyTheme(theme);
    }
  }

  if (booting) {
    return (
      <div className="auth-layout">
        <p
          className="chat__empty"
          role="status"
        >
          Loading…
        </p>
      </div>
    );
  }

  if (screen === "auth" || user === null) {
    if (screen === "otp" && otp !== null) {
      return (
        <OtpScreen
          displayName={otp.name}
          issued={otp.issued}
          mode={otp.mode}
          onBack={() => setScreen("auth")}
          onVerified={(profile) => {
            setUser(profile);
            applyTheme(profile.theme);
            setScreen("chat");

            void loadAvatar(profile);
          }}
          password={otp.password}
        />
      );
    }

    return (
      <AuthScreen
        initialEmail={otp?.email ?? ""}
        initialMode={otp?.mode === "reset" ? "forgot" : otp?.mode === "login" ? "login" : "signup"}
        onOtpIssued={(
          issued,
          mode,
          displayName,
          password,
          email,
        ) => {
          setOtp({
            issued,
            mode,
            name: displayName,
            password,
            email,
          });

          setScreen("otp");
        }}
        onSignedIn={(profile) => {
          setUser(profile);
          applyTheme(profile.theme);
          setScreen("chat");
          void loadAvatar(profile);
        }}
      />
    );
  }

  if (screen === "otp" && otp !== null) {
    return (
      <OtpScreen
        displayName={otp.name}
        issued={otp.issued}
        mode={otp.mode}
        onBack={() => setScreen("auth")}
        onVerified={(profile) => {
          setUser(profile);
          applyTheme(profile.theme);
          setScreen("chat");

          void loadAvatar(profile);
        }}
        password={otp.password}
      />
    );
  }

  return (
    <div className="page">
      <AppHeader
        active={
          screen === "profile"
            ? "profile"
            : "chat"
        }
        avatarUrl={avatarUrl}
        onLogout={() => setLogoutOpen(true)}
        onOpenChat={() => setScreen("chat")}
        onOpenProfile={() => setScreen("profile")}
        onThemeChange={(theme) => {
          void handleTheme(theme);
        }}
        theme={user.theme}
        user={user}
      />

      {screen === "profile" ? (
        <ProfileScreen
          avatarUrl={avatarUrl}
          onAvatarChanged={() => {
            void loadAvatar(user);
          }}
          onClose={() => setScreen("chat")}
          onUpdated={(profile) => {
            setUser(profile);
            applyTheme(profile.theme);

            void loadAvatar(profile);
          }}
          user={user}
        />
      ) : (
        <ChatWorkspace
          onUnauthenticated={() => {
            void handleLogout();
          }}
        />
      )}

      <LogoutConfirmModal
        isLoggingOut={isLoggingOut}
        isOpen={logoutOpen}
        onCancel={() => setLogoutOpen(false)}
        onConfirm={() => {
          void confirmLogout();
        }}
      />

      <footer className="page__footer">
        <p>
          Answers are generated only from documents approved for retrieval.
          Always confirm anything consequential with your team.
        </p>
      </footer>
    </div>
  );
}