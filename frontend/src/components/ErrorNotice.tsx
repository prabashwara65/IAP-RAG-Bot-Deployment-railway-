import type { HrAskFailureKind } from "../api/hrRag";

interface ErrorNoticeProps {
  kind: HrAskFailureKind;
  correlationId: string | null;
}

/**
 * Present a failure in the user's terms.
 *
 * Every message is written here in the frontend. Backend messages, status
 * lines, and exception detail are never rendered, so nothing internal can
 * reach the page.
 */
const FAILURE_MESSAGES: Record<HrAskFailureKind, string> = {
  network:
    "The HR assistant could not be reached. Check that the OIAP backend is running, then try again.",
  invalid_request:
    "That question could not be submitted. Try rephrasing it, or shorten it if it is very long.",
  rate_limited:
    "Rate limit reached — maximum 5 questions per minute. Please wait and try again shortly.",
  unavailable:
    "The HR assistant is temporarily unavailable. Please try again in a few minutes.",
  unauthenticated:
    "Your session has ended. Sign in again to keep asking questions.",
  upstream:
    "The HR assistant could not produce a grounded answer this time. Please try again.",
  unexpected: "Something went wrong while answering. Please try again.",
};

export function ErrorNotice({ kind, correlationId }: ErrorNoticeProps) {
  return (
    <div className="notice notice--error" role="alert">
      <p className="notice__message">{FAILURE_MESSAGES[kind]}</p>
      {correlationId === null ? null : (
        <p className="notice__reference">Reference: {correlationId}</p>
      )}
    </div>
  );
}
