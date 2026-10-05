import { useEffect, useId, useRef, useState } from "react";
import type { Profile, ThemePreference } from "../api/auth";
import { ROLE_LABELS } from "../api/adminUsers";
import { AvatarMark } from "./AvatarMark";
import { ThemeToggle } from "./ThemeToggle";
import { ShellIcon } from "./ShellIcon";

interface Props {
  user: Profile;
  avatarUrl: string | null;
  onThemeChange: (theme: ThemePreference) => void;
  onOpenProfile: () => void;
  onOpenUsers: () => void;
  onLogout: () => void;
}

export function SidebarAccountMenu({ user, avatarUrl, onThemeChange, onOpenProfile, onOpenUsers, onLogout }: Props) {
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const role = ROLE_LABELS[user.role ?? "user"];

  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !wrapper.current?.contains(event.target)) setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape" && wrapper.current?.contains(document.activeElement)) {
        event.stopPropagation();
        setOpen(false);
        trigger.current?.focus();
      }
    }
    document.addEventListener("pointerdown", outside);
    const element = wrapper.current;
    element?.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      element?.removeEventListener("keydown", escape);
    };
  }, [open]);

  function navigate(action: () => void) { setOpen(false); action(); }

  return <div className="sidebar-account" ref={wrapper} onBlur={(event) => {
    if (event.relatedTarget instanceof Node && !event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }}>
    {open ? <section id={panelId} className="sidebar-account__panel" aria-label="Account options">
      <div className="sidebar-account__identity">
        <strong>{user.display_name}</strong><span>{user.email}</span><span className="role-badge">{role}</span>
      </div>
      <div className="sidebar-account__appearance"><span>Appearance</span>
        <ThemeToggle theme={user.theme} onChange={onThemeChange} />
      </div>
      <button type="button" onClick={() => navigate(onOpenProfile)}><ShellIcon name="profile" />Profile</button>
      {user.role === "admin" ? <button type="button" onClick={() => navigate(onOpenUsers)}><ShellIcon name="users" />Manage Users</button> : null}
      <button type="button" onClick={() => navigate(onLogout)}><ShellIcon name="logout" />Sign Out</button>
    </section> : null}
    <button type="button" className="sidebar-account__trigger" ref={trigger} aria-expanded={open}
      aria-controls={open ? panelId : undefined} aria-label={`Account: ${user.display_name}`}
      onClick={() => setOpen((previous) => !previous)}>
      <AvatarMark imageUrl={avatarUrl} name={user.display_name} />
      <span className="sidebar-account__who"><strong>{user.display_name}</strong><span>{role}</span></span>
      <ShellIcon name="chevron" />
    </button>
  </div>;
}
