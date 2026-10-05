import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { MAX_QUESTION_LENGTH } from "../api/hrRag";

interface ChatComposerProps {
  isLoading: boolean;
  onAsk: (question: string) => void;
}

/**
 * Chat composer pinned to the bottom of the conversation.
 *
 * Enter sends and Shift+Enter inserts a newline, matching the convention of
 * every chat interface. Blank and whitespace-only questions are rejected here
 * rather than on a round trip, matching the backend contract.
 *
 * The tenant is no longer collected from the reader. It is a fixed internal
 * routing value for this public demo, not something a visitor should set.
 */
export function ChatComposer({ isLoading, onAsk }: ChatComposerProps) {
  const [question, setQuestion] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const trimmedQuestion = question.trim();
  const canSubmit = !isLoading && trimmedQuestion.length > 0;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(textarea.scrollHeight || 28, 140) + "px";
    }
  }, [question]);

  function submit() {
    if (!canSubmit) {
      return;
    }
    onAsk(trimmedQuestion);
    setQuestion("");
    textareaRef.current?.focus();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Shift+Enter must fall through to the textarea so it inserts a newline.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <label className="composer__label" htmlFor="question">
        Your question
      </label>
      <div className="composer__row">
        <textarea
          className="composer__input"
          disabled={isLoading}
          id="question"
          maxLength={MAX_QUESTION_LENGTH}
          name="question"
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about leave, remote work, expenses or probation…"
          ref={textareaRef}
          rows={1}
          value={question}
        />
        <button
          className="composer__send"
          disabled={!canSubmit}
          type="submit"
          aria-label="Send question"
        >
          {isLoading ? <span className="composer__spinner" aria-hidden="true" /> :
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 19V5m-6 6 6-6 6 6" />
            </svg>}
        </button>
      </div>
      <p className="composer__hint">
        Enter to send · words{" "}
        {trimmedQuestion.length}/{MAX_QUESTION_LENGTH}
      </p>
    </form>
  );
}
