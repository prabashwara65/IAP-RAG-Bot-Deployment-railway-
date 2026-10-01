import { useEffect, useRef } from "react";

interface LogoutSuccessModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function LogoutSuccessModal({
  isOpen,
  onClose,
}: LogoutSuccessModalProps) {
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    buttonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Tab") {
        event.preventDefault();
        buttonRef.current?.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);

      if (
        previousFocus instanceof HTMLElement &&
        previousFocus.isConnected
      ) {
        previousFocus.focus();
      }
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="logout-modal__backdrop" role="presentation">
      <section
        className="logout-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="logout-success-title"
        aria-describedby="logout-success-description"
      >
        <h2 className="logout-modal__title" id="logout-success-title">
          Signed out
        </h2>
        <p
          className="logout-modal__description"
          id="logout-success-description"
        >
          Thank you for using OIAP Office Assistant. You have successfully signed out.
        </p>
        <div
          className="logout-modal__actions"
          style={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
          }}
        >
          <button
            ref={buttonRef}
            className="logout-modal__button logout-modal__button--confirm"
            type="button"
            onClick={onClose}
            style={{
              minWidth: "100px",
              margin: "0 auto",
              textAlign: "center",
            }}
          >
            OK
          </button>
        </div>
      </section>
    </div>
  );
}