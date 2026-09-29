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
  onLogout,
  
}: AppHeaderProps) {
  return (
    <header className="glass topbar">

      {/* TOP SECTION */}
      <div className="topbar__top">

        {/* TOP LEFT */}
        <div className="topbar__brand">
          <p className="eyebrow">Office Intelligence</p>

          <h1 className="page__title">
            Office Assistant
          </h1>

          <p className="page__subtitle">
            Ask questions about company policies and processes.
          </p>
        </div>

        {/* TOP RIGHT */}
        <div className="topbar__account">

          {/* PROFILE AVATAR + NAME */}
          <button
            className="profile-hit"
            onClick={onOpenProfile}
            type="button"
            aria-label="Open profile"
          >
            <AvatarMark
              imageUrl={avatarUrl}
              name={user.display_name}
            />

            <span className="profile-hit__name">
              {user.display_name}
            </span>
          </button>

          {/* LOGOUT */}
          <button
            className="text-btn"
            onClick={onLogout}
            type="button"
          >
            Logout
          </button>

        </div>
      </div>

      {/* BOTTOM ACTIONS */}
      <div className="topbar__actions">

        {/* LEFT SIDE */}
        <div className="topbar__nav">

          <ThemeToggle
            theme={theme}
            onChange={onThemeChange}
          />

        </div>
      </div>

    </header>
  );
}