import { useEffect, useRef } from "react";
import { ThemeToggle } from "./ThemeToggle";
import { AvatarMark } from "./AvatarMark";
import type { Profile, ThemePreference } from "../api/auth";

interface AppHeaderProps {
  user: Profile;
  avatarUrl: string | null;
  theme: ThemePreference;
  onThemeChange: (theme: ThemePreference) => void;
  onOpenProfile: () => void;
  onOpenChat: () => void;
  onLogout: () => void;
  active: "chat" | "profile" | "users";
  onOpenUsers?: () => void;
}

function Icon({ kind }: { kind: "menu" | "bot" | "moon" | "chevron" | "profile" | "logout" }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {kind === "menu" && <path d="M4 6h16M4 12h16M4 18h16" />}
    {kind === "moon" && <path d="M20.8 13a9 9 0 0 1-9.8-9.8A9 9 0 1 0 20.8 13Z" />}
    {kind === "profile" && <><circle cx="12" cy="8" r="3.5" /><path d="M5 21v-2a7 7 0 0 1 14 0v2" /></>}
    {kind === "logout" && <><path d="M9 4H4v16h5M15 8l4 4-4 4M9 12h10" /></>}
    {kind === "chevron" && <path d="m8 10 4 4 4-4" />}
    {kind === "bot" && <><rect x="4" y="7" width="16" height="13" rx="4" /><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8" /></>}
  </svg>;
}

export function AppHeader({ user, avatarUrl, theme, onThemeChange, onOpenProfile, onLogout, onOpenChat, onOpenUsers, active }: AppHeaderProps) {
  const headerRef = useRef<HTMLElement>(null);
  const animations = useRef(new Map<HTMLDetailsElement, Animation>());
  function setPanel(details: HTMLDetailsElement, open: boolean) {
    const panel = details.querySelector<HTMLElement>(".oiap-nav__panel");
    const current = animations.current.get(details);
    const from = panel && details.open ? {
      opacity: window.getComputedStyle(panel).opacity,
      transform: window.getComputedStyle(panel).transform,
    } : { opacity: "0", transform: "translateY(-8px) scale(0.98)" };
    if (current) {
      current.onfinish = null;
      current.cancel();
      animations.current.delete(details);
    }
    details.dataset.closing = open ? "false" : "true";
    if (!panel || typeof panel.animate !== "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      details.open = open;
      delete details.dataset.closing;
      return;
    }
    if (open) details.open = true;
    if (!details.open) return;
    const animation = panel.animate([
      from,
      open ? { opacity: "1", transform: "translateY(0) scale(1)" }
           : { opacity: "0", transform: "translateY(-8px) scale(0.98)" },
    ], { duration: open ? 200 : 150, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)", fill: "both" });
    animations.current.set(details, animation);
    animation.onfinish = () => {
      details.open = open;
      delete details.dataset.closing;
      animations.current.delete(details);
      animation.cancel();
    };
  }
  function closePanels() {
    headerRef.current?.querySelectorAll<HTMLDetailsElement>("details[open]").forEach((panel) => {
      if (panel.dataset.closing !== "true") setPanel(panel, false);
    });
  }
  function navigate(action: () => void) { closePanels(); action(); }

  useEffect(() => {
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !headerRef.current?.contains(event.target)) closePanels();
    }
    function escape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      headerRef.current?.querySelectorAll<HTMLDetailsElement>("details[open]").forEach((panel) => {
        if (panel.contains(document.activeElement)) panel.querySelector("summary")?.focus();
        setPanel(panel, false);
      });
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
      animations.current.forEach((animation) => { animation.onfinish = null; animation.cancel(); });
      animations.current.clear();
    };
  }, []);

  function navigation() {
    return <>
      <button type="button" className="oiap-nav__link" aria-current={active === "chat" ? "page" : undefined} onClick={() => navigate(onOpenChat)}>Assistant</button>
      {user.role === "admin" && onOpenUsers ? <button type="button" className="oiap-nav__link" aria-current={active === "users" ? "page" : undefined} onClick={() => navigate(onOpenUsers)}>Manage Users</button> : null}
    </>;
  }

  return (
    <header className="oiap-nav" ref={headerRef} onBlur={(event) => {
      if (event.relatedTarget instanceof Node && !event.currentTarget.contains(event.relatedTarget)) closePanels();
    }} onClick={(event) => {
      if (!(event.target instanceof Element)) return;
      const summary = event.target.closest("summary");
      const details = summary?.parentElement;
      if (!(details instanceof HTMLDetailsElement)) return;
      event.preventDefault();
      const open = !details.open || details.dataset.closing === "true";
      if (open) {
        headerRef.current?.querySelectorAll<HTMLDetailsElement>("details[open]").forEach((other) => {
          if (other !== details && other.dataset.closing !== "true") setPanel(other, false);
        });
      }
      setPanel(details, open);
    }}>
      <details className="oiap-nav__disclosure oiap-nav__mobile">
        <summary className="oiap-nav__icon" aria-label="Navigation"><Icon kind="menu" /></summary>
        <nav className="oiap-nav__panel oiap-nav__mobile-links" aria-label="Mobile navigation">{navigation()}</nav>
      </details>
      <button type="button" className="oiap-nav__brand" onClick={() => navigate(onOpenChat)} aria-label="OIAP Office Assistant home">
        <span className="oiap-nav__logo"><Icon kind="bot" /></span>
        <span><strong>OIAP</strong><span className="oiap-nav__tagline">Office Assistant</span></span>
      </button>
      <nav className="oiap-nav__desktop" aria-label="Main navigation">{navigation()}</nav>
      <div className="oiap-nav__account">
        <details className="oiap-nav__disclosure">
          <summary className="oiap-nav__profile" aria-label={`Account: ${user.display_name}`}>
            <AvatarMark imageUrl={avatarUrl} name={user.display_name} />
            <span className="oiap-nav__greeting">Hi, {user.display_name}</span><Icon kind="chevron" />
          </summary>
          <div className="oiap-nav__panel oiap-nav__account-panel">
            <div className="oiap-nav__identity"><span className="oiap-nav__identity-label">Logged in as</span><strong>{user.email}</strong></div>
            <button className="oiap-nav__menu-action" type="button" onClick={() => navigate(onOpenProfile)} aria-current={active === "profile" ? "page" : undefined}><Icon kind="profile" />My Profile</button>
            <button className="oiap-nav__menu-action oiap-nav__logout" type="button" onClick={() => navigate(onLogout)}><Icon kind="logout" />Sign Out</button>
          </div>
        </details>
        <details className="oiap-nav__disclosure">
          <summary className="oiap-nav__icon" aria-label="Appearance"><Icon kind="moon" /></summary>
          <div className="oiap-nav__panel oiap-nav__theme-panel"><strong>Appearance</strong><ThemeToggle theme={theme} onChange={onThemeChange} /></div>
        </details>
      </div>
    </header>
  );
}
