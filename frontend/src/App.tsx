import "./components/manageUsers.css";
import { useCallback, useEffect, useState } from "react";
import {
  fetchAvatarBlob,
  fetchProfile,
  logout as logoutRequest,
  updateProfile,
} from "./api/auth";
import type { OtpIssued, Profile, ThemePreference } from "./api/auth";
import { getAccessToken, setAccessToken } from "./api/session";
import { AuthScreen } from "./components/AuthScreen";
import { ChatWorkspace } from "./components/ChatWorkspace";
import { OtpScreen } from "./components/OtpScreen";
import { LogoutConfirmModal } from "./components/LogoutConfirmModal";
import { ManageUsersScreen } from "./components/ManageUsersScreen";
import { SuccessModal } from "./components/SuccessModal";
import { ProfileScreen } from "./components/ProfileScreen";
import { clearActiveChat } from "./services/activeChatStorage";

type Screen =
  | "auth"
  | "otp"
  | "chat"
  | "profile"
  | "users"
  | "sign-in-success";

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

  const [successDialog, setSuccessDialog] = useState<{
    title: string;
    message: string;
  } | null>(null);

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
    if (user !== null) {
      clearActiveChat(user.id);
    }

    await logoutRequest();

    setUser(null);
    setOtp(null);
    setSuccessDialog(null);
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

      setSuccessDialog({
        title: "Signed out",
        message:
          "Thank you for using OIAP Office Assistant. You have successfully signed out.",
      });
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

  useEffect(() => {
    if (screen !== "sign-in-success") {
      return;
    }

    const timer = window.setTimeout(() => {
      setScreen("chat");
    }, 3_000);

    return () => {
      window.clearTimeout(timer);
    };
  }, [screen]);

  function acceptSignIn(profile: Profile) {
    clearActiveChat(profile.id);
    setUser(profile);
    setOtp(null);
    applyTheme(profile.theme);
    setSuccessDialog(null);
    setScreen("sign-in-success");
    void loadAvatar(profile);
  }

  async function handleAccessDenied() {
    setScreen("chat");

    try {
      const profile = await fetchProfile();
      setUser(profile);
    } catch {
      await handleLogout();
    }
  }

  const successModal = (
    <SuccessModal
      isOpen={successDialog !== null}
      title={successDialog?.title ?? ""}
      message={successDialog?.message ?? ""}
      onClose={() => setSuccessDialog(null)}
    />
  );

  if (booting) {
    return (
      <div className="auth-layout">
        <p className="chat__empty" role="status">
          Loading…
        </p>
      </div>
    );
  }

  if (screen === "sign-in-success" && user !== null) {
    return (
      <div className="auth-layout">
        <SuccessModal
          isOpen
          title="Signed in successfully"
          message="Welcome to OIAP HR Assistant. You have successfully signed in."
          note="Opening the RAG bot in 3 seconds…"
          showButton={false}
          onClose={() => {}}
        />
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
          onVerified={acceptSignIn}
          password={otp.password}
        />
      );
    }

    return (
      <>
        <AuthScreen
          initialEmail={otp?.email ?? ""}
          initialMode={
            otp?.mode === "reset"
              ? "forgot"
              : otp?.mode === "login"
                ? "login"
                : "signup"
          }
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
          onSignedIn={acceptSignIn}
        />

        {successModal}
      </>
    );
  }

  if (screen === "otp" && otp !== null) {
    return (
      <OtpScreen
        displayName={otp.name}
        issued={otp.issued}
        mode={otp.mode}
        onBack={() => setScreen("auth")}
        onVerified={acceptSignIn}
        password={otp.password}
      />
    );
  }

  return (
    <>
      <ChatWorkspace key={user.id} userId={user.id} userRole={user.role} user={user} avatarUrl={avatarUrl}
        onOpenChat={() => setScreen("chat")}
        onOpenProfile={() => setScreen("profile")}
        onOpenUsers={() => { if (user.role === "admin") setScreen("users"); }}
        onThemeChange={(theme) => { void handleTheme(theme); }}
        onLogout={() => setLogoutOpen(true)}
        onUnauthenticated={() => { void handleLogout(); }}
        content={screen === "users" && user.role === "admin" ? (
          <ManageUsersScreen currentUser={user}
            onUnauthenticated={() => { void handleLogout(); }}
            onAccessDenied={() => { void handleAccessDenied(); }} />
        ) : screen === "profile" ? (
          <ProfileScreen avatarUrl={avatarUrl}
            onAvatarChanged={() => { void loadAvatar(user); }}
            onClose={() => setScreen("chat")}
            onUpdated={(profile) => {
              setUser(profile);
              applyTheme(profile.theme);
              void loadAvatar(profile);
            }} user={user} />
        ) : undefined}
      />
      <LogoutConfirmModal isLoggingOut={isLoggingOut} isOpen={logoutOpen}
        onCancel={() => setLogoutOpen(false)} onConfirm={() => { void confirmLogout(); }} />
      {successModal}
    </>
  );
}
