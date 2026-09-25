import { useEffect } from "react";


interface LogoutConfirmModalProps {
  isOpen: boolean;
  isLoggingOut: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function LogoutConfirmModal({
  isOpen,
  isLoggingOut,
  onCancel,
  onConfirm,
}: LogoutConfirmModalProps) {
  useEffect(() => {
    if (!isOpen) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !isLoggingOut) {
        onCancel();
      }
    }

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, isLoggingOut, onCancel]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="logout-modal__backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (
          event.target === event.currentTarget &&
          !isLoggingOut
        ) {
          onCancel();
        }
      }}
    >
      <section
        className="logout-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="logout-modal-title"
        aria-describedby="logout-modal-description"
      >
        <button
          className="logout-modal__close"
          type="button"
          onClick={onCancel}
          aria-label="Close logout confirmation"
          disabled={isLoggingOut}
        >
          ×
        </button>



        <h2
          className="logout-modal__title"
          id="logout-modal-title"
        >
          Log out ?
        </h2>

        <p
          className="logout-modal__description"
          id="logout-modal-description"
        >
          Are you sure you want to log out of your account?
        </p>

        <div className="logout-modal__actions">
          <button
            className="logout-modal__button logout-modal__button--cancel"
            type="button"
            onClick={onCancel}
            disabled={isLoggingOut}
          >
            Cancel
          </button>

          <button
            className="logout-modal__button logout-modal__button--confirm"
            type="button"
            onClick={onConfirm}
            disabled={isLoggingOut}
          >
            {isLoggingOut ? "Logging out…" : "Log out"}
          </button>
        </div>
      </section>
    </div>
  );
}