import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { HrAskResponse } from "./api/hrRag";

const LEAVE_ANSWER: HrAskResponse = {
  answer: "Employees receive twenty-one working days of annual leave. [S1]",
  citations: [
    {
      citation_id: "S1",
      document_key: "HR-SYNTHETIC-LEAVE-001",
      document_title: "Synthetic Annual Leave Policy",
      heading_path: "Synthetic Annual Leave Policy > Entitlement",
      chunk_index: 0,
      distance: 0.12,
    },
  ],
  insufficient_evidence: false,
};

const REMOTE_ANSWER: HrAskResponse = {
  answer: "Remote work is approved for up to three days each week. [S1]",
  citations: [
    {
      citation_id: "S1",
      document_key: "HR-SYNTHETIC-REMOTE-002",
      document_title: "Synthetic Remote Work Policy",
      heading_path: "Synthetic Remote Work Policy > Eligibility",
      chunk_index: 1,
      distance: 0.2,
    },
  ],
  insufficient_evidence: false,
};

// What the reader should see: the same answer with its [Sn] markers stripped.
const LEAVE_ANSWER_VISIBLE =
  "Employees receive twenty-one working days of annual leave.";
const REMOTE_ANSWER_VISIBLE =
  "Remote work is approved for up to three days each week.";

const INSUFFICIENT_ANSWER: HrAskResponse = {
  answer: "I do not have enough approved HR information to answer this question.",
  citations: [],
  insufficient_evidence: true,
};

const TEST_USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "ada@example.com",
  display_name: "Ada Lovelace",
  role: "admin" as const,
  theme: "light" as const,
  has_avatar: false,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "X-Correlation-ID": "correlation-1",
    },
  });
}

function routeFetch(url: string, ask: () => Response): Response {
  if (url.includes("/api/v1/chats")) return jsonResponse([]);
  if (url.includes("/api/v1/me/avatar")) {
    return new Response(null, { status: 404 });
  }
  if (url.includes("/api/v1/me")) {
    return jsonResponse(TEST_USER);
  }
  return ask();
}

/** Answer each successive request with the next body in the queue. */
function mockSequence(...bodies: unknown[]): void {
  const queue = [...bodies];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input) =>
      routeFetch(String(input), () =>
        jsonResponse(queue.shift() ?? bodies[bodies.length - 1]),
      ),
    ),
  );
}

function mockStatus(body: unknown, status: number): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input) =>
      routeFetch(String(input), () => jsonResponse(body, status)),
    ),
  );
}

function hrAskCalls() {
  return vi.mocked(fetch).mock.calls.filter(([url]) => String(url).includes("/hr/ask"));
}

function composer(): HTMLTextAreaElement {
  return screen.getByLabelText(/your (hr )?question/i) as HTMLTextAreaElement;
}

function sendButton(): HTMLElement {
  return screen.getByRole("button", { name: /send question/i });
}

async function ask(question: string): Promise<void> {
  const user = userEvent.setup();
  await user.type(composer(), question);
  await user.click(sendButton());
}

async function renderChat(): Promise<void> {
  window.localStorage.setItem("oiap.access_token", "test-token");
  render(<App />);
  await screen.findByRole("button", { name: /send question/i });
}

beforeEach(() => {
  // jsdom does not implement scrollIntoView.
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("conversation", () => {
  it("shows the assistant header and no tenant field", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    expect(
      screen.getByRole("heading", { name: /how can I help, Ada/i }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/tenant id/i)).not.toBeInTheDocument();
  });

  it("keeps the existing tenant in the request body", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    await ask("How much leave?");

    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    const askCall = vi.mocked(fetch).mock.calls.find(([url]) =>
      String(url).includes("/hr/ask"),
    ) as [string, RequestInit];
    expect(JSON.parse(String(askCall[1].body))).toEqual({
      question: "How much leave?",
      tenant_id: "tenant-real",
    });
  });

  it("sends the selected document type with the question", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();
    const user = userEvent.setup();
    await user.click(screen.getByText("Documents", { selector: "summary" }));
    await user.selectOptions(screen.getByLabelText(/search document type/i), "CV");

    await user.type(
      screen.getByLabelText(/^your question$/i),
      "Find information in CV documents.",
    );
    await user.click(sendButton());

    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    const askCall = vi.mocked(fetch).mock.calls.find(([url]) =>
      String(url).includes("/hr/ask"),
    ) as [string, RequestInit];
    expect(JSON.parse(String(askCall[1].body))).toEqual({
      question: "Find information in CV documents.",
      tenant_id: "tenant-real",
      document_type: "CV",
    });
  });

  it("shows the first user message and the first assistant response", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    await ask("How many annual leave days do employees receive?");

    expect(
      screen.getByText("How many annual leave days do employees receive?"),
    ).toBeInTheDocument();
    expect(await screen.findByText(LEAVE_ANSWER_VISIBLE)).toBeInTheDocument();
  });

  it("keeps earlier turns visible when a second question is asked", async () => {
    mockSequence(LEAVE_ANSWER, REMOTE_ANSWER);
    await renderChat();

    await ask("How much leave?");
    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    await ask("How many remote days?");
    await screen.findByText(REMOTE_ANSWER_VISIBLE);

    expect(screen.getByText("How much leave?")).toBeInTheDocument();
    expect(screen.getByText(LEAVE_ANSWER_VISIBLE)).toBeInTheDocument();
    expect(screen.getByText("How many remote days?")).toBeInTheDocument();
    expect(screen.getByText(REMOTE_ANSWER_VISIBLE)).toBeInTheDocument();
  });

  it("renders the transcript in chronological order", async () => {
    mockSequence(LEAVE_ANSWER, REMOTE_ANSWER);
    await renderChat();

    await ask("How much leave?");
    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    await ask("How many remote days?");
    await screen.findByText(REMOTE_ANSWER_VISIBLE);

    const transcript = screen.getByRole("log", { name: /conversation/i });
    const rendered = Array.from(
      transcript.querySelectorAll(".message__text"),
    ).map((node) => node.textContent);
    expect(rendered).toEqual([
      "How much leave?",
      LEAVE_ANSWER_VISIBLE,
      "How many remote days?",
      REMOTE_ANSWER_VISIBLE,
    ]);
  });

  it("renders each answer's citations under that answer", async () => {
    mockSequence(LEAVE_ANSWER, REMOTE_ANSWER);
    await renderChat();

    await ask("How much leave?");
    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    await ask("How many remote days?");
    await screen.findByText(REMOTE_ANSWER_VISIBLE);

    const messages = document.querySelectorAll(".message--assistant");
    expect(messages).toHaveLength(2);
    expect(
      within(messages[0] as HTMLElement).getByText("HR-SYNTHETIC-LEAVE-001"),
    ).toBeInTheDocument();
    expect(
      within(messages[1] as HTMLElement).getByText("HR-SYNTHETIC-REMOTE-002"),
    ).toBeInTheDocument();
    expect(
      within(messages[0] as HTMLElement).queryByText("HR-SYNTHETIC-REMOTE-002"),
    ).not.toBeInTheDocument();
  });
});

describe("collapsible sources", () => {
  it("shows a collapsed Sources control when an answer has citations", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    await ask("How much leave?");
    await screen.findByText(LEAVE_ANSWER_VISIBLE);

    const details = document.querySelector(".citations") as HTMLDetailsElement;
    expect(details).not.toBeNull();
    expect(details.open).toBe(false);
    expect(screen.getByText("Sources")).toBeInTheDocument();
  });

  it("expands and collapses the citation list when Sources is clicked", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    await ask("How much leave?");
    await screen.findByText(LEAVE_ANSWER_VISIBLE);

    const details = document.querySelector(".citations") as HTMLDetailsElement;
    const user = userEvent.setup();

    await user.click(screen.getByText("Sources"));
    expect(details.open).toBe(true);

    await user.click(screen.getByText("Sources"));
    expect(details.open).toBe(false);
  });

  it("keeps every citation field inside the expanded control", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    await ask("How much leave?");
    await screen.findByText(LEAVE_ANSWER_VISIBLE);

    const user = userEvent.setup();
    await user.click(screen.getByText("Sources"));

    const details = document.querySelector(".citations") as HTMLElement;
    const source = within(details);
    expect(source.queryByText("[S1]")).not.toBeInTheDocument();
    expect(source.getByText("Synthetic Annual Leave Policy")).toBeInTheDocument();
    expect(
      source.getByText("Synthetic Annual Leave Policy > Entitlement"),
    ).toBeInTheDocument();
    expect(source.getByText("HR-SYNTHETIC-LEAVE-001")).toBeInTheDocument();
  });

  it("gives each assistant message its own Sources control", async () => {
    mockSequence(LEAVE_ANSWER, REMOTE_ANSWER);
    await renderChat();

    await ask("How much leave?");
    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    await ask("How many remote days?");
    await screen.findByText(REMOTE_ANSWER_VISIBLE);

    const messages = document.querySelectorAll(".message--assistant");
    expect(document.querySelectorAll(".citations")).toHaveLength(2);
    expect(
      within(messages[0] as HTMLElement).getByText("Sources"),
    ).toBeInTheDocument();
    expect(
      within(messages[1] as HTMLElement).getByText("Sources"),
    ).toBeInTheDocument();
  });

  it("hides inline citation markers from the visible answer text", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    await ask("How much leave?");

    const answer = await screen.findByText(LEAVE_ANSWER_VISIBLE);
    expect(answer).not.toHaveTextContent(/\[S\d+\]/);
    expect(answer.closest(".citations")).toBeNull();
    expect(document.body.textContent).not.toContain("[S1]");
  });

  it("keeps the raw answer, markers included, in the data model", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    await ask("How much leave?");

    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    // The fixture the client parsed still carries its marker; only the
    // rendered text drops it.
    expect(LEAVE_ANSWER.answer).toContain("[S1]");
    expect(LEAVE_ANSWER.citations.map((c) => c.citation_id)).toEqual(["S1"]);
  });

  it("no longer shows the grounded badge on a successful answer", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    await ask("How much leave?");

    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    expect(
      screen.queryByText(/grounded in approved sources/i),
    ).not.toBeInTheDocument();
  });
});

describe("evidence and failures", () => {
  it("presents insufficient evidence as a normal outcome, not a failure", async () => {
    mockSequence(INSUFFICIENT_ANSWER);
    await renderChat();

    await ask("What is the visitor parking policy?");

    expect(await screen.findByText(/insufficient evidence/i)).toBeInTheDocument();
    expect(document.querySelector(".badge--caution")).not.toBeNull();
    expect(
      screen.getByText(/did not contain enough information/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
  });

  it("shows the dedicated rate-limit message for HTTP 429", async () => {
    mockStatus({ error: { code: "HTTP_429", message: "backend wording" } }, 429);
    await renderChat();

    await ask("How much leave?");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      /maximum 5 questions per minute\. Please wait and try again shortly\./i,
    );
    expect(alert).not.toHaveTextContent(/something went wrong/i);
    expect(document.body.textContent).not.toContain("backend wording");
    expect(document.body.textContent).not.toContain("HTTP_429");
  });

  it("keeps the reference id on a rate-limit failure", async () => {
    mockStatus({ error: {} }, 429);
    await renderChat();

    await ask("How much leave?");

    expect(await screen.findByRole("alert")).toHaveTextContent(/correlation-1/);
  });

  it("keeps the rate-limited question visible in the transcript", async () => {
    mockStatus({ error: {} }, 429);
    await renderChat();

    await ask("How much leave?");

    await screen.findByRole("alert");
    expect(screen.getByText("How much leave?")).toBeInTheDocument();
  });

  it("still shows the generic message for an unexpected failure", async () => {
    const leakMarker = "internal-backend-detail";
    mockStatus({ error: { message: leakMarker, code: "HTTP_502" } }, 502);
    await renderChat();

    await ask("How much leave?");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/could not produce a grounded answer/i);
    expect(alert).toHaveTextContent(/correlation-1/);
    expect(document.body.textContent).not.toContain(leakMarker);
    expect(document.body.textContent).not.toContain("HTTP_502");
  });

  it("shows a safe message when the backend is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input) => {
        const url = String(input);
        if (url.includes("/api/v1/chats")) return jsonResponse([]);
        if (url.includes("/api/v1/me/avatar")) {
          return new Response(null, { status: 404 });
        }
        if (url.includes("/api/v1/me")) {
          return jsonResponse(TEST_USER);
        }
        throw new TypeError("Failed to fetch");
      }),
    );
    await renderChat();

    await ask("How much leave?");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /could not be reached/i,
    );
  });
});

describe("composer", () => {
  it("cannot send a blank or whitespace-only question", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    expect(sendButton()).toBeDisabled();

    const user = userEvent.setup();
    await user.type(composer(), "   ");
    expect(sendButton()).toBeDisabled();
    expect(hrAskCalls()).toHaveLength(0);
  });

  it("sends on Enter", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    const user = userEvent.setup();
    await user.type(composer(), "How much leave?");
    await user.keyboard("{Enter}");

    expect(await screen.findByText(LEAVE_ANSWER_VISIBLE)).toBeInTheDocument();
    expect(hrAskCalls()).toHaveLength(1);
  });

  it("inserts a newline on Shift+Enter without sending", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    const user = userEvent.setup();
    await user.type(composer(), "first line");
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    await user.type(composer(), "second line");

    expect(composer().value).toBe("first line\nsecond line");
    expect(hrAskCalls()).toHaveLength(0);
  });

  it("clears the composer after a question is sent", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    await ask("How much leave?");

    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    expect(composer().value).toBe("");
  });

  it("disables sending and shows a loading state while a request is in flight", async () => {
    let release: (() => void) | undefined;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input) => {
        const url = String(input);
        if (url.includes("/api/v1/chats")) return jsonResponse([]);
        if (url.includes("/api/v1/me/avatar")) {
          return new Response(null, { status: 404 });
        }
        if (url.includes("/api/v1/me")) {
          return jsonResponse(TEST_USER);
        }
        await pending;
        return jsonResponse(LEAVE_ANSWER);
      }),
    );
    await renderChat();

    await ask("How much leave?");

    expect(await screen.findByRole("status")).toHaveTextContent(
      /searching approved hr sources/i,
    );
    expect(sendButton()).toBeDisabled();
    expect(composer()).toBeDisabled();

    release?.();
    await waitFor(() => {
      expect(screen.getByText(LEAVE_ANSWER_VISIBLE)).toBeInTheDocument();
    });
    expect(hrAskCalls()).toHaveLength(1);
  });

  it("scrolls to the newest message", async () => {
    mockSequence(LEAVE_ANSWER);
    await renderChat();

    await ask("How much leave?");

    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    // Only the transcript scrolls; the page and its ancestors stay in place.
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });
});

describe("authentication", () => {
  it("shows signup when there is no session", async () => {
    render(<App />);

    expect(await screen.findByRole("button", { name: /send verification code/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/work email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/your hr question/i)).not.toBeInTheDocument();
  });

  it("shows the demo OTP after signup", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          otp_sent: true,
          email: "ada@example.com",
          expires_in_seconds: 600,
          otp_code: "123456",
          delivery: "on_screen",
        }),
      ),
    );
    render(<App />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/display name/i), "Ada");
    await user.type(screen.getByLabelText(/work email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "Password12!");
    await user.type(screen.getByLabelText(/^confirm password$/i), "Password12!");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    expect(await screen.findByText("123456")).toBeInTheDocument();
    expect(screen.getByText(/your verification code/i)).toBeInTheDocument();
  });

  it("asks the user to check Gmail when SMTP delivered the OTP", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          otp_sent: true,
          email: "ada@example.com",
          expires_in_seconds: 600,
          otp_code: null,
          delivery: "email",
        }),
      ),
    );
    render(<App />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/display name/i), "Ada");
    await user.type(screen.getByLabelText(/work email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "Password12!");
    await user.type(screen.getByLabelText(/^confirm password$/i), "Password12!");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    expect(await screen.findByText(/check gmail/i)).toBeInTheDocument();
    expect(screen.queryByText("123456")).not.toBeInTheDocument();
  });

  it("prevents signup when password does not meet complexity requirements", async () => {
    render(<App />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/display name/i), "Ada");
    await user.type(screen.getByLabelText(/work email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "simple");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    expect(
      await screen.findByText(
        /password must be at least 8 characters and include a capital letter, a number, and a symbol/i,
      ),
    ).toBeInTheDocument();
  });

  it("prevents signup when confirm password does not match", async () => {
    render(<App />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/display name/i), "Ada");
    await user.type(screen.getByLabelText(/work email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "Password12!");
    await user.type(screen.getByLabelText(/^confirm password$/i), "Different12!");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument();
  });

  it("toggles password visibility between password and text", async () => {
    render(<App />);

    const passwordInput = screen.getByLabelText(/^password$/i);
    expect(passwordInput).toHaveAttribute("type", "password");

    const toggleButton = screen.getByLabelText(/show password/i);
    const user = userEvent.setup();
    await user.click(toggleButton);

    expect(passwordInput).toHaveAttribute("type", "text");
    expect(screen.getByLabelText(/hide password/i)).toBeInTheDocument();
  });

  it("switches to forgot password mode and requests password reset", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          otp_sent: true,
          email: "ada@example.com",
          expires_in_seconds: 600,
          otp_code: "998877",
          delivery: "on_screen",
        }),
      ),
    );
    render(<App />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^log in$/i }));
    await user.click(screen.getByRole("button", { name: /forgot password\?/i }));

    expect(screen.getByText(/reset your password/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/work email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^new password$/i), "NewPassword123!");
    await user.type(screen.getByLabelText(/confirm new password/i), "NewPassword123!");
    await user.click(screen.getByRole("button", { name: /send reset code/i }));

    expect(await screen.findByText("998877")).toBeInTheDocument();
  });

  it("disables resend code button with countdown timer on the OTP screen", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          otp_sent: true,
          email: "ada@example.com",
          expires_in_seconds: 600,
          otp_code: "123456",
          delivery: "on_screen",
        }),
      ),
    );
    render(<App />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/display name/i), "Ada");
    await user.type(screen.getByLabelText(/work email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "Password12!");
    await user.type(screen.getByLabelText(/^confirm password$/i), "Password12!");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    await screen.findByText("123456");
    const resendButton = screen.getByRole("button", { name: /resend code in/i });
    expect(resendButton).toBeDisabled();
  });

  it("renders 6-cell segmented OTP input and static expiration notice", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          otp_sent: true,
          email: "ada@example.com",
          expires_in_seconds: 600,
          otp_code: null,
          delivery: "email",
        }),
      ),
    );
    render(<App />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/display name/i), "Ada");
    await user.type(screen.getByLabelText(/work email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "Password12!");
    await user.type(screen.getByLabelText(/^confirm password$/i), "Password12!");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    expect(await screen.findByText(/valid for 10 minutes/i)).toBeInTheDocument();

    for (let i = 1; i <= 6; i++) {
      expect(screen.getByLabelText(new RegExp(`digit ${i} of 6`, "i"))).toBeInTheDocument();
    }

    await user.type(screen.getByLabelText(/digit 1 of 6/i), "1");
    await user.type(screen.getByLabelText(/digit 2 of 6/i), "2");
    await user.type(screen.getByLabelText(/digit 3 of 6/i), "3");
    await user.type(screen.getByLabelText(/digit 4 of 6/i), "4");
    await user.type(screen.getByLabelText(/digit 5 of 6/i), "5");
    await user.type(screen.getByLabelText(/digit 6 of 6/i), "6");

    expect(screen.getByLabelText(/digit 1 of 6/i)).toHaveValue("1");
    expect(screen.getByLabelText(/digit 6 of 6/i)).toHaveValue("6");
    expect(screen.getByRole("button", { name: /verify and continue/i })).toBeEnabled();
  });
});
