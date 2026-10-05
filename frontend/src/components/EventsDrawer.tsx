import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { calendarToday, createEvent, deleteEvent, EventApiError, fetchCalendarTimezone, fetchEvents, isCalendarDate } from "../api/events";
import type { CalendarEvent } from "../api/events";
import "./events.css";

const MONTH_NAMES = Array.from({ length: 12 }, (_, index) =>
  new Intl.DateTimeFormat("en-GB", { month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2026, index, 1))));

interface Props {
  isOpen: boolean;
  onUnauthenticated: () => void;
}
function dateLabel(value: string): string {
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
    .format(new Date(value + "T12:00:00Z"));
}
function timeLabel(value: string): string {
  const [hour = "0", minute = "00"] = value.split(":");
  const number = Number(hour);
  return (number % 12 || 12) + ":" + minute + (number < 12 ? " AM" : " PM");
}
function ordered(events: CalendarEvent[]): CalendarEvent[] {
  return [...events].sort((a, b) => a.event_date.localeCompare(b.event_date)
    || (a.event_time ?? "").localeCompare(b.event_time ?? "") || a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
}
// Kept mounted inside the sidebar so collapsing Events preserves its draft.
export function EventsDrawer({ isOpen, onUnauthenticated }: Props) {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [timezone, setTimezone] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [reload, setReload] = useState(0);
  const [notice, setNotice] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [eventTime, setEventTime] = useState("");
  const [sendEmail, setSendEmail] = useState(false);
  const [month, setMonth] = useState<string | null>(null);
  const [yearDraft, setYearDraft] = useState("");
  const [adding, setAdding] = useState(false);
  const [changing, setChanging] = useState(new Set<string>());
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());
  const unauthorizedRef = useRef(onUnauthenticated);
  const addingRef = useRef(false);
  const changingRef = useRef(new Set<string>());
  useEffect(() => { unauthorizedRef.current = onUnauthenticated; }, [onUnauthenticated]);

  useEffect(() => {
    if (!isOpen) return;
    setNow(new Date());
    const clockTimer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => {
      window.clearInterval(clockTimer);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setLoading(true); setLoadError(false); setNotice("");
    async function load() {
      try {
        const zone = await fetchCalendarTimezone();
        if (cancelled) return;
        setTimezone(zone);
        const today = calendarToday(zone);
        setMonth((previous) => previous || today.slice(0, 7));
        const items = await fetchEvents();
        if (cancelled) return;
        setEvents(ordered(items));
      } catch (error) {
        if (cancelled) return;
        setLoadError(true);
        if (error instanceof EventApiError && error.kind === "unauthenticated") unauthorizedRef.current();
      } finally { if (!cancelled) setLoading(false); }
    }
    void load();
    return () => { cancelled = true; };
  }, [isOpen, reload]);

  function reportFailure(error: unknown, message: string) {
    if (error instanceof EventApiError && error.kind === "unauthenticated") {
      unauthorizedRef.current(); return;
    }
    setNotice(message);
  }
  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (addingRef.current || loading || loadError || timezone === null) return;
    if (!title.trim() || !isCalendarDate(selectedDate) || selectedDate < calendarToday(timezone)) {
      setNotice("Enter an event title and choose today or a future date."); return;
    }
    addingRef.current = true; setAdding(true); setNotice("");
    try {
      const created = await createEvent({
        title: title.trim(), description: description.trim() || null,
        event_date: selectedDate, event_time: eventTime || null, send_email: sendEmail,
      });
      setEvents((previous) => ordered([...previous, created]));
      setTitle(""); setDescription(""); setEventTime(""); setSendEmail(false);
      setNotice(sendEmail
        ? created.email_sent ? "Event added. Event details emailed to your account."
          : "Event added. The event email could not be sent."
        : "Event added.");
    } catch (error) {
      reportFailure(error, error instanceof EventApiError && error.kind === "invalid"
        ? "Check the title, description, date, and time."
        : "Unable to confirm whether the event was saved. Reload events before trying again.");
    } finally { addingRef.current = false; setAdding(false); }
  }
  function clearDraft() {
    if (addingRef.current) return;
    setTitle(""); setDescription(""); setEventTime(""); setSendEmail(false);
    setSelectedDate("");
    setNotice("Draft cleared.");
  }
  async function removeEvent(event: CalendarEvent) {
    if (changingRef.current.has(event.id)) return;
    changingRef.current.add(event.id); setChanging(new Set(changingRef.current)); setNotice("");
    try {
      await deleteEvent(event.id);
      setEvents((previous) => previous.filter((item) => item.id !== event.id));
      setNotice("Event deleted.");
      setDeleteTarget(null);
    } catch (error) {
      reportFailure(error, "Unable to confirm the result. Reload events before trying again.");
    } finally { changingRef.current.delete(event.id); setChanging(new Set(changingRef.current)); }
  }
  const today = timezone === null ? "" : calendarToday(timezone, now);
  const unavailable = loading || loadError || timezone === null;
  const busy = adding || changing.size > 0;
  const monthDate = month === null ? null : new Date(month + "-01T12:00:00Z");
  const year = monthDate?.getUTCFullYear() ?? now.getUTCFullYear();
  useEffect(() => { setYearDraft(String(year)); }, [year]);
  const monthIndex = monthDate?.getUTCMonth() ?? 0;
  const days = new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
  const offset = ((monthDate?.getUTCDay() ?? 1) + 6) % 7;
  const marked = new Set(events.filter((event) => !event.cancelled).map((event) => event.event_date));
  function changeMonth(delta: number) {
    const next = new Date(Date.UTC(year, monthIndex + delta, 1));
    setMonth(next.toISOString().slice(0, 7));
  }
  function changeYear(value: string) {
    setYearDraft(value);
    const nextYear = Number(value);
    if (/^\d{4}$/.test(value) && nextYear >= 1000 && nextYear <= 9999) {
      setMonth(value + "-" + String(monthIndex + 1).padStart(2, "0"));
    }
  }
  return (
    <section id="sidebar-events" className="sidebar-events" aria-label="Events" hidden={!isOpen}>
      {loading ? <p role="status">Loading events...</p> : null}
      {loadError ? <p className="notice" role="alert">Events are temporarily unavailable. Reload events to enable saving.</p> : null}
      <button type="button" className="events-reload" disabled={loading || busy} onClick={() => setReload((value) => value + 1)}>Reload events</button>
      {monthDate !== null ? (
        <section className="events-calendar" aria-label="Calendar">
          <div className="events-calendar__heading">
            <button type="button" className="events-icon-button" disabled={adding || month === "1000-01"} onClick={() => changeMonth(-1)} aria-label="Previous month">&#8249;</button>
            <div className="events-calendar__picker">
              <select aria-label="Calendar month" value={monthIndex} disabled={adding}
                onChange={(event) => setMonth(String(year) + "-" + String(Number(event.target.value) + 1).padStart(2, "0"))}>
                {MONTH_NAMES.map((name, index) => <option key={name} value={index}>{name}</option>)}
              </select>
              <input aria-label="Calendar year" type="number" min={1000} max={9999} step={1}
                value={yearDraft} disabled={adding} onChange={(event) => changeYear(event.target.value)}
                onBlur={() => setYearDraft(String(year))}
                onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); event.currentTarget.blur(); } }} />
            </div>
            <button type="button" className="events-icon-button" disabled={adding || month === "9999-12"} onClick={() => changeMonth(1)} aria-label="Next month">&#8250;</button>
          </div>
          <div className="events-calendar__grid">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => <span className="events-calendar__weekday" key={day}>{day}</span>)}
            {Array.from({ length: offset }, (_, index) => <span key={"gap-" + index} />)}
            {Array.from({ length: days }, (_, index) => {
              const value = month + "-" + String(index + 1).padStart(2, "0");
              return <button type="button" key={value} className="events-calendar__day"
                aria-label={dateLabel(value)} aria-pressed={value === selectedDate} data-today={value === today}
                disabled={adding || value < today} onClick={() => setSelectedDate(value)}>
                {index + 1}{marked.has(value) ? <span className="events-calendar__dot" aria-label="Has events" /> : null}
              </button>;
            })}
          </div>
        </section>
      ) : null}
      {isCalendarDate(selectedDate) ? <>
      <p className="events-selected">Selected: {dateLabel(selectedDate)}</p>
      <form className="events-form" onSubmit={(event) => { void add(event); }}>
        <h3>Add an event</h3>
        <label>Event Title<input className="field__input" required maxLength={200} value={title} disabled={adding} onChange={(event) => setTitle(event.target.value)} /></label>
        <label>Event Time (optional)<input className="field__input" type="time" step={60} value={eventTime} disabled={adding} onChange={(event) => setEventTime(event.target.value)} /></label>
        <label>Event Description<textarea className="field__input" rows={3} maxLength={2000} value={description} disabled={adding} onChange={(event) => setDescription(event.target.value)} /></label>
        <label className="events-email-option">
          <input type="checkbox" checked={sendEmail} disabled={adding} onChange={(event) => setSendEmail(event.target.checked)} />
          Send event details to my email
        </label>
        <div className="events-form__actions">
          <button className="btn btn--primary" type="submit" disabled={unavailable || adding}>{adding ? "Adding..." : "Add Event"}</button>
          <button className="btn" type="button" disabled={adding} onClick={clearDraft}>Cancel</button>
        </div>
      </form>
      </> : monthDate !== null ? <p className="events-muted events-calendar__hint">Choose a date to add an event.</p> : null}
      {notice ? <p className="notice" role="status">{notice}</p> : null}
      <section className="events-list" aria-label="Saved events">
        <h3>Events</h3>
        {!unavailable && events.length === 0 ? <p className="events-muted">No events yet.</p> : null}
        <ul>{events.map((event) => (
          <li className="events-item" key={event.id}>
            <div><strong>{event.title}</strong>
              <p className="events-muted">{dateLabel(event.event_date)}</p>
              {event.event_time !== null ? <p className="events-muted">{timeLabel(event.event_time)}</p> : null}
              <div className="events-item__actions">
                <button className="btn" type="button" aria-label={"Delete " + event.title}
                  disabled={unavailable || changing.has(event.id)}
                  onClick={() => setDeleteTarget(event.id)}>Delete</button>
              </div>
              {deleteTarget === event.id ? <div className="events-delete-confirm" role="group" aria-label={"Delete confirmation for " + event.title}>
                <p>Delete this event permanently?</p>
                <div className="events-item__actions">
                  <button className="btn" type="button" disabled={changing.has(event.id)}
                    onClick={() => { void removeEvent(event); }}>Delete event</button>
                  <button className="btn" type="button" disabled={changing.has(event.id)}
                    onClick={() => setDeleteTarget(null)}>Keep event</button>
                </div>
              </div> : null}
            </div>
          </li>
        ))}</ul>
      </section>
    </section>
  );
}
