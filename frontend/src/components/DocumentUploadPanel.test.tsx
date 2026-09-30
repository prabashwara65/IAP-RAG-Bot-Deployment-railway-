import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DocumentUploadPanel } from "./DocumentUploadPanel";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("document upload panel", () => {
  it("sends a selected document and displays its chunks", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            filename: "guide.txt",
            document_type: "CV",
            document_key: "UPLOAD-TEST",
            version_id: "version-1",
            version_status: "candidate",
            chunk_count: 1,
            chunks: [
              {
                chunk_index: 0,
                content_text: "Extracted policy text",
                content_hash: "a".repeat(64),
              },
            ],
          }),
          { status: 200 },
        ),
      ),
    );
    render(<DocumentUploadPanel onUnauthenticated={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/document type for upload/i), {
      target: { value: "CV" },
    });

    fireEvent.change(screen.getByLabelText(/choose document/i), {
      target: { files: [new File(["source text"], "guide.txt", { type: "text/plain" })] },
    });

    expect(await screen.findByText("Extracted policy text")).toBeInTheDocument();
    expect(screen.getByText("guide.txt")).toBeInTheDocument();
    expect(screen.getByText(/stored as CV/i)).toBeInTheDocument();
    expect(screen.getByText(/as a candidate\. it is not searchable until approved/i)).toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    const request = vi.mocked(fetch).mock.calls[0]?.[1];
    expect(request?.body).toBeInstanceOf(FormData);
    expect((request?.body as FormData).get("document_type")).toBe("CV");
  });

  it("shows a clear message for an unsupported document", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 415 })),
    );
    render(<DocumentUploadPanel onUnauthenticated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/choose document/i), {
      target: { files: [new File(["text"], "guide.rtf")] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Choose a TXT, Markdown, PDF, or DOCX file.",
    );
  });
});