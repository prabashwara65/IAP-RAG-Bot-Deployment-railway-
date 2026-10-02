import { useEffect, useRef, useState } from "react";
import type { Profile, UserRole } from "../api/auth";
import {
  AdminUsersError, assignRole, fetchUsers, ROLE_LABELS, ROLE_OPTIONS,
} from "../api/adminUsers";
import type { AssignedRole } from "../api/adminUsers";
import { SuccessModal } from "./SuccessModal";

interface ManageUsersScreenProps {
  currentUser: Profile;
  onUnauthenticated: () => void;
  onAccessDenied: () => void;
}

export function ManageUsersScreen({
  currentUser, onUnauthenticated, onAccessDenied,
}: ManageUsersScreenProps) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [users, setUsers] = useState<Profile[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, AssignedRole | "">>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [successOpen, setSuccessOpen] = useState(false);
  const [retry, setRetry] = useState(0);
  const callbacks = useRef({ onUnauthenticated, onAccessDenied });
  callbacks.current = { onUnauthenticated, onAccessDenied };
  const saveInProgress = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const timer = window.setTimeout(() => {
      void fetchUsers(search, page, controller.signal).then((result) => {
        if (controller.signal.aborted) return;
        setUsers(result.users);
        setTotal(result.total);
        setDrafts({});
      }).catch((failure: unknown) => {
        if (controller.signal.aborted) return;
        if (failure instanceof AdminUsersError && failure.status === 401) {
          callbacks.current.onUnauthenticated();
        } else if (failure instanceof AdminUsersError && failure.status === 403) {
          callbacks.current.onAccessDenied();
        } else {
          setError(failure instanceof Error ? failure.message : "Could not load users.");
        }
      }).finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [search, page, retry]);

  async function save(user: Profile, role: AssignedRole) {
    if (saveInProgress.current) return;
    saveInProgress.current = true;
    setSavingId(user.id);
    setError(null);
    try {
      const updated = await assignRole(user.id, role);
      if (!mounted.current) return;
      setUsers((previous) => previous.map((item) => item.id === updated.id ? updated : item));
      setDrafts((previous) => {
        const next = { ...previous };
        delete next[user.id];
        return next;
      });
      setSuccessOpen(true);
    } catch (failure) {
      if (!mounted.current) return;
      if (failure instanceof AdminUsersError && failure.status === 401) {
        callbacks.current.onUnauthenticated();
      } else if (failure instanceof AdminUsersError && failure.status === 403) {
        callbacks.current.onAccessDenied();
      } else {
        setError(failure instanceof Error ? failure.message : "Could not update the role.");
      }
    } finally {
      saveInProgress.current = false;
      if (mounted.current) setSavingId(null);
    }
  }

  return (
    <main className="users-panel glass">
      <div className="users-panel__heading">
        <div>
          <p className="eyebrow">Administration</p>
          <h2>Manage Users</h2>
          <p>New accounts start as User. Assign their role here.</p>
        </div>
        <span className="users-panel__count">{total} {total === 1 ? "account" : "accounts"}</span>
      </div>

      <label className="users-search">
        <span>Find a user</span>
        <input
          type="search"
          placeholder="Search by name or email"
          value={search}
          disabled={savingId !== null}
          onChange={(event) => { setSearch(event.target.value); setPage(1); }}
        />
      </label>

      {error && (
        <div className="users-panel__error" role="alert">
          <p>{error}</p>
          <button type="button" className="text-btn" onClick={() => setRetry((n) => n + 1)}>
            Refresh users
          </button>
        </div>
      )}

      {loading ? <p role="status">Loading users…</p> : (
        <div className="users-list">
          {users.length === 0 ? <p>No users found. Try another name or email.</p> : null}
          {users.map((user) => {
            const currentRole: UserRole = user.role ?? "user";
            const selected = drafts[user.id] ?? (currentRole === "user" ? "" : currentRole);
            const isSelf = user.id === currentUser.id;
            const canSave = selected !== "" && selected !== currentRole && savingId === null;
            return (
              <article className="user-row" key={user.id} aria-label={user.email}>
                <div className="user-row__identity">
                  <span className="user-row__avatar" aria-hidden="true">
                    {user.display_name.trim().slice(0, 1).toUpperCase() || "U"}
                  </span>
                  <div>
                    <h3>{user.display_name} {isSelf ? <small>(You)</small> : null}</h3>
                    <p>{user.email}</p>
                    <span className={`role-badge role-badge--${currentRole}`}>
                      {ROLE_LABELS[currentRole]}
                    </span>
                  </div>
                </div>
                <div className="user-row__assignment">
                  <label htmlFor={`role-${user.id}`}>Assign role</label>
                  <div className="user-row__controls">
                    <select
                      id={`role-${user.id}`}
                      value={selected}
                      disabled={savingId !== null || isSelf}
                      onChange={(event) => setDrafts((previous) => ({
                        ...previous, [user.id]: event.target.value as AssignedRole | "",
                      }))}
                    >
                      <option value="" disabled>Select role</option>
                      {ROLE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                    <button
                      className="users-save"
                      type="button"
                      disabled={!canSave}
                      aria-label={`Save role for ${user.display_name}`}
                      onClick={() => { if (selected !== "") void save(user, selected); }}
                    >
                      {savingId === user.id ? "Saving…" : "Save changes"}
                    </button>
                  </div>
                  <small>{isSelf ? "Your administrator access is protected." : "Changes apply after you save."}</small>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <nav className="users-pagination" aria-label="User list pages">
        <button type="button" className="text-btn" disabled={page === 1 || loading || savingId !== null}
          onClick={() => setPage((n) => n - 1)}>Previous</button>
        <span>Page {page} of {Math.max(1, Math.ceil(total / 20))}</span>
        <button type="button" className="text-btn" disabled={page * 20 >= total || loading || savingId !== null}
          onClick={() => setPage((n) => n + 1)}>Next</button>
      </nav>

      <SuccessModal
        isOpen={successOpen}
        title="Role updated"
        message="Role updated successfully."
        onClose={() => setSuccessOpen(false)}
      />
    </main>
  );
}