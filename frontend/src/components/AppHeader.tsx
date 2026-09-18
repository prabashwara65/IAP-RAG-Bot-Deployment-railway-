import { ThemeToggle } from "./ThemeToggle";
import { AvatarMark } from "./AvatarMark";
import type { Profile } from "../api/auth";
import type { ThemePreference } from "../api/auth";

interface AppHeaderProps {
  user: Profile;
  avatarUrl: string | null;
  theme: ThemePreference;
  onThemeChange: (theme: ThemePreference) => void;
  onOpenProfile: () => void;
  onOpenChat: () => void;
  onLogout: () => void;
  active: "chat" | "profile";
}

export function AppHeader({
  user,
  avatarUrl,
  theme,
  onThemeChange,
  onOpenProfile,
  onOpenChat,
  onLogout,
  active,
}: AppHeaderProps) {
  return (
    <header className="glass topbar">
      <div className="topbar__brand">
        <p className="eyebrow">Office Intelligence</p>
        <h1 className="page__title">OIAP HR Assistant</h1>
        <p className="page__subtitle">Ask questions using approved HR knowledge.</p>
      </div>
      <div className="topbar__actions">
        <ThemeToggle theme={theme} onChange={onThemeChange} />
        <button
          className={active === "chat" ? "chip is-active" : "chip"}
          onClick={onOpenChat}
          type="button"
        >
          Chat
        </button>
        <button
          className={active === "profile" ? "chip is-active" : "chip"}
          onClick={onOpenProfile}
          type="button"
        >
          Profile
        </button>
        <button
          className="profile-hit"
          onClick={onOpenProfile}
          type="button"
          aria-label="Open profile"
        >
          <AvatarMark imageUrl={avatarUrl} name={user.display_name} />
          <span className="profile-hit__name">{user.display_name}</span>
        </button>
        <button className="text-btn" onClick={onLogout} type="button">
          Log out
        </button>
      </div>
    </header>
  );
}
