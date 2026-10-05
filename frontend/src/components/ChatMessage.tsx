import type { HrAskResponse } from "../api/hrRag";
import { CitationList } from "./CitationList";
import { ShellIcon } from "./ShellIcon";

export interface UserTurn {
  id: string;
  role: "user";
  question: string;
}

export interface AssistantTurn {
  id: string;
  role: "assistant";
  response: HrAskResponse;
}

export type ChatTurn = UserTurn | AssistantTurn;

const INSUFFICIENT_EVIDENCE_NOTE =
  "The approved HR sources did not contain enough information to answer this question. " +
  "This is not an error: nothing was invented to fill the gap.";

/** Matches `[S1]`, `[S12]`, and grouped forms such as `[S1, S2]`. */
const CITATION_MARKER = /\s*\[S\d+(?:\s*,\s*S\d+)*\]/g;

/**
 * Strip inline citation markers for display only.
 *
 * The markers are how the model attributes a claim, and the grounding service
 * still validates every one of them before an answer is accepted. They are
 * removed here purely because they read as technical noise in a public demo;
 * `response.answer` keeps the original text and `response.citations` keeps the
 * evidence, so nothing is lost from the data model.
 */
function withoutCitationMarkers(answer: string): string {
  return answer.replace(CITATION_MARKER, "").replace(/\s{2,}/g, " ").trim();
}

/**
 * Render one turn of the conversation.
 *
 * Both the question and the answer are rendered as plain text. No Markdown or
 * HTML is interpreted, so neither reader input nor model output can inject
 * markup into the page.
 */
export function ChatMessage({ turn }: { turn: ChatTurn }) {
  if (turn.role === "user") {
    return (
      <article className="message message--user">
        <p className="message__role">You</p>
        <p className="message__text">{turn.question}</p>
      </article>
    );
  }

  const insufficient = turn.response.insufficient_evidence;

  return (
    <article className="message message--assistant">
      <span className="assistant-mark"><ShellIcon name="assistant" /></span>
      <div className="message__content">
      <header className="message__header">
        <p className="message__role">HR Assistant</p>
        {insufficient ? (
          <span className="badge badge--caution">Insufficient evidence</span>
        ) : null}
      </header>

      <p className="message__text">
        {withoutCitationMarkers(turn.response.answer)}
      </p>

      {insufficient ? (
        <p className="message__note">{INSUFFICIENT_EVIDENCE_NOTE}</p>
      ) : null}

      <CitationList citations={turn.response.citations} />
      </div>
    </article>
  );
}
