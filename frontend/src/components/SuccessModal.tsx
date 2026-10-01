import { useEffect, useRef } from "react";

interface SuccessModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  onClose: () => void;
  showButton?: boolean;
  note?: string;
}

export function SuccessModal({
  isOpen,
  title,
  message,
  onClose,
  showButton = true,
  note,
}: SuccessModalProps) {
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);
  useEffect(() => {
    if (!isOpen || !showButton) return;
    const timer = window.setTimeout(() => closeRef.current(), 3_000);
    return () => window.clearTimeout(timer);
  }, [isOpen, showButton]);

  const buttonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    (showButton ? buttonRef.current : dialogRef.current)?.focus();
    function trapFocus(event: KeyboardEvent) {
      if (event.key === "Tab") {
        event.preventDefault();
        (showButton ? buttonRef.current : dialogRef.current)?.focus();
      }
    }
    document.addEventListener("keydown", trapFocus);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", trapFocus);
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
        previousFocus.focus();
      }
    };
  }, [isOpen, showButton]);

  if (!isOpen) return null;

  return (
    <div className="logout-modal__backdrop" role="presentation">
      <section
        ref={dialogRef}
        tabIndex={-1}
        className="logout-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="success-modal-title"
        aria-describedby={note ? "success-modal-description success-modal-note" : "success-modal-description"}
      >
        <span className="success-modal__mark" aria-hidden="true">✓</span>
        <h2 className="logout-modal__title" id="success-modal-title">{title}</h2>
        <p className="logout-modal__description" id="success-modal-description">
          {message}
        </p>
        {note ? <p className="logout-modal__description" id="success-modal-note">{note}</p> : null}
        {showButton ? (
          <div
            className="logout-modal__actions success-modal__actions"
            style={{ display: "flex", justifyContent: "center", alignItems: "center" }}
          >
            <button
              ref={buttonRef}
              className="logout-modal__button logout-modal__button--confirm"
              type="button"
              onClick={onClose}
              style={{ flex: "0 0 auto", width: "100px", maxWidth: "100%", margin: "0 auto" }}
            >
              OK
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
