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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "X-Correlation-ID": "correlation-1",
    },
  });
}

/** Answer each successive request with the next body in the queue. */
function mockSequence(...bodies: unknown[]): void {
  const queue = [...bodies];
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse(queue.shift() ?? bodies[bodies.length - 1])),
  );
}

function mockStatus(body: unknown, status: number): void {
  vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(body, status)));
}

function composer(): HTMLTextAreaElement {
  return screen.getByLabelText(/your hr question/i) as HTMLTextAreaElement;
}

function sendButton(): HTMLElement {
  return screen.getByRole("button", { name: /send question/i });
}

async function ask(question: string): Promise<void> {
  const user = userEvent.setup();
  await user.type(composer(), question);
  await user.click(sendButton());
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
  it("shows the assistant header and no tenant field", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "OIAP HR Assistant" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/tenant id/i)).not.toBeInTheDocument();
  });

  it("keeps the fixed synthetic tenant in the request body", async () => {
    mockSequence(LEAVE_ANSWER);
    render(<App />);

    await ask("How much leave?");

    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      question: "How much leave?",
      tenant_id: "tenant-synthetic",
    });
  });

  it("shows the first user message and the first assistant response", async () => {
    mockSequence(LEAVE_ANSWER);
    render(<App />);

    await ask("How many annual leave days do employees receive?");

    expect(
      screen.getByText("How many annual leave days do employees receive?"),
    ).toBeInTheDocument();
    expect(await screen.findByText(LEAVE_ANSWER_VISIBLE)).toBeInTheDocument();
  });

  it("keeps earlier turns visible when a second question is asked", async () => {
    mockSequence(LEAVE_ANSWER, REMOTE_ANSWER);
    render(<App />);

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
    render(<App />);

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
    render(<App />);

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
    render(<App />);

    await ask("How much leave?");
    await screen.findByText(LEAVE_ANSWER_VISIBLE);

    const details = document.querySelector(".citations") as HTMLDetailsElement;
    expect(details).not.toBeNull();
    expect(details.open).toBe(false);
    expect(screen.getByText("Sources")).toBeInTheDocument();
  });

  it("expands and collapses the citation list when Sources is clicked", async () => {
    mockSequence(LEAVE_ANSWER);
    render(<App />);

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
    render(<App />);

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
    render(<App />);

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
    render(<App />);

    await ask("How much leave?");

    const answer = await screen.findByText(LEAVE_ANSWER_VISIBLE);
    expect(answer).not.toHaveTextContent(/\[S\d+\]/);
    expect(answer.closest(".citations")).toBeNull();
    expect(document.body.textContent).not.toContain("[S1]");
  });

  it("keeps the raw answer, markers included, in the data model", async () => {
    mockSequence(LEAVE_ANSWER);
    render(<App />);

    await ask("How much leave?");

    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    // The fixture the client parsed still carries its marker; only the
    // rendered text drops it.
    expect(LEAVE_ANSWER.answer).toContain("[S1]");
    expect(LEAVE_ANSWER.citations.map((c) => c.citation_id)).toEqual(["S1"]);
  });

  it("no longer shows the grounded badge on a successful answer", async () => {
    mockSequence(LEAVE_ANSWER);
    render(<App />);

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
    render(<App />);

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
    render(<App />);

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
    render(<App />);

    await ask("How much leave?");

    expect(await screen.findByRole("alert")).toHaveTextContent(/correlation-1/);
  });

  it("keeps the rate-limited question visible in the transcript", async () => {
    mockStatus({ error: {} }, 429);
    render(<App />);

    await ask("How much leave?");

    await screen.findByRole("alert");
    expect(screen.getByText("How much leave?")).toBeInTheDocument();
  });

  it("still shows the generic message for an unexpected failure", async () => {
    const leakMarker = "internal-backend-detail";
    mockStatus({ error: { message: leakMarker, code: "HTTP_502" } }, 502);
    render(<App />);

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
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    render(<App />);

    await ask("How much leave?");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /could not be reached/i,
    );
  });
});

describe("composer", () => {
  it("cannot send a blank or whitespace-only question", async () => {
    mockSequence(LEAVE_ANSWER);
    render(<App />);

    expect(sendButton()).toBeDisabled();

    const user = userEvent.setup();
    await user.type(composer(), "   ");
    expect(sendButton()).toBeDisabled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("sends on Enter", async () => {
    mockSequence(LEAVE_ANSWER);
    render(<App />);

    const user = userEvent.setup();
    await user.type(composer(), "How much leave?");
    await user.keyboard("{Enter}");

    expect(await screen.findByText(LEAVE_ANSWER_VISIBLE)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("inserts a newline on Shift+Enter without sending", async () => {
    mockSequence(LEAVE_ANSWER);
    render(<App />);

    const user = userEvent.setup();
    await user.type(composer(), "first line");
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    await user.type(composer(), "second line");

    expect(composer().value).toBe("first line\nsecond line");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("clears the composer after a question is sent", async () => {
    mockSequence(LEAVE_ANSWER);
    render(<App />);

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
      vi.fn(async () => {
        await pending;
        return jsonResponse(LEAVE_ANSWER);
      }),
    );
    render(<App />);

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
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("scrolls to the newest message", async () => {
    mockSequence(LEAVE_ANSWER);
    render(<App />);

    await ask("How much leave?");

    await screen.findByText(LEAVE_ANSWER_VISIBLE);
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });
});
