import {
  CalendarDays,
  SquarePen,
  Menu,
  X,
  User,
  LogOut,
  Users,
  ChevronUp,
  Sparkles,
  Save,
  RefreshCw,
  Trash2,
} from "lucide-react";

type IconName = "calendar" | "new-chat" | "menu" | "close" | "profile" | "logout" | "users" | "chevron" | "assistant" | "save" | "refresh" | "delete";

const icons = {
  calendar: CalendarDays,
  "new-chat": SquarePen,
  menu: Menu,
  close: X,
  profile: User,
  logout: LogOut,
  users: Users,
  chevron: ChevronUp,
  assistant: Sparkles,
  save: Save,
  refresh: RefreshCw,
  delete: Trash2,
};

export function ShellIcon({ name }: { name: IconName }) {
  const Icon = icons[name];

  return <Icon size={18} strokeWidth={1.7} aria-hidden="true" />;
}
