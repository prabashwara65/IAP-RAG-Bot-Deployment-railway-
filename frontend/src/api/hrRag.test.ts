import { afterEach, describe, expect, it, vi } from "vitest";
import { askHrQuestion, HrAskError, MAX_QUESTION_LENGTH } from "./hrRag";
import type { HrAskResponse } from "./hrRag";

const SUCCESS_BODY: HrAskResponse = {
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

function jsonResponse(
  body: unknown,
  init: { status?: number; correlationId?: string } = {},
): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: {
      "Content-Type": "application/json",
      ...(init.correlationId === undefined
        ? {}
        : { "X-Correlation-ID": init.correlationId }),
    },
  });
}

function mockFetch(implementation: typeof fetch): void {
  vi.stubGlobal("fetch", vi.fn(implementation));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("askHrQuestion", () => {
  it("posts the wire contract to the HR ask endpoint", async () => {
    mockFetch(async () => jsonResponse(SUCCESS_BODY));

    await askHrQuestion({ question: "How much leave?", tenant_id: "tenant-synthetic" });

    const call = vi.mocked(fetch).mock.calls[0];
    expect(call).toBeDefined();
    const [url, init] = call as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/hr/ask");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init.body))).toEqual({
      question: "How much leave?",
      tenant_id: "tenant-synthetic",
    });
  });

  it("returns the parsed grounded answer", async () => {
    mockFetch(async () => jsonResponse(SUCCESS_BODY));

    const response = await askHrQuestion({
      question: "How much leave?",
      tenant_id: "tenant-synthetic",
    });

    expect(response).toEqual(SUCCESS_BODY);
    expect(response.citations[0]?.citation_id).toBe("S1");
  });

  it("uses the configured base URL without a duplicated slash", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://oiap.example.internal/");
    mockFetch(async () => jsonResponse(SUCCESS_BODY));

    await askHrQuestion({ question: "q", tenant_id: "t" });

    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe(
      "https://oiap.example.internal/api/v1/hr/ask",
    );
  });

  it.each([
    [422, "invalid_request"],
    [503, "unavailable"],
    [502, "upstream"],
    [504, "upstream"],
    [500, "unexpected"],
  ])("maps status %i onto the %s failure kind", async (status, kind) => {
    mockFetch(async () =>
      jsonResponse({ error: { message: "internal detail" } }, {
        status,
        correlationId: "correlation-1",
      }),
    );

    const error = await askHrQuestion({ question: "q", tenant_id: "t" }).catch(
      (thrown: unknown) => thrown,
    );

    expect(error).toBeInstanceOf(HrAskError);
    expect((error as HrAskError).kind).toBe(kind);
    expect((error as HrAskError).correlationId).toBe("correlation-1");
  });

  it("never carries backend error text into the thrown error", async () => {
    const leakMarker = "internal-backend-detail";
    mockFetch(async () =>
      jsonResponse({ error: { message: leakMarker } }, { status: 502 }),
    );

    const error = (await askHrQuestion({ question: "q", tenant_id: "t" }).catch(
      (thrown: unknown) => thrown,
    )) as HrAskError;

    expect(error.message).not.toContain(leakMarker);
  });

  it("reports an unreachable backend as a network failure", async () => {
    mockFetch(async () => {
      throw new TypeError("Failed to fetch");
    });

    const error = (await askHrQuestion({ question: "q", tenant_id: "t" }).catch(
      (thrown: unknown) => thrown,
    )) as HrAskError;

    expect(error.kind).toBe("network");
    expect(error.correlationId).toBeNull();
  });

  it("rejects a response that does not match the contract", async () => {
    mockFetch(async () => jsonResponse({ answer: "text" }));

    const error = (await askHrQuestion({ question: "q", tenant_id: "t" }).catch(
      (thrown: unknown) => thrown,
    )) as HrAskError;

    expect(error.kind).toBe("unexpected");
  });

  it("rejects a response whose citation is missing required fields", async () => {
    mockFetch(async () =>
      jsonResponse({
        answer: "Employees receive annual leave. [S1]",
        insufficient_evidence: false,
        citations: [{ citation_id: "S1", document_title: "Synthetic Policy" }],
      }),
    );

    const error = (await askHrQuestion({ question: "q", tenant_id: "t" }).catch(
      (thrown: unknown) => thrown,
    )) as HrAskError;

    expect(error).toBeInstanceOf(HrAskError);
    expect(error.kind).toBe("unexpected");
  });

  it.each([
    ["citation_id", 1],
    ["document_key", null],
    ["document_title", 42],
    ["heading_path", { nested: true }],
    ["chunk_index", "0"],
    ["chunk_index", 1.5],
    ["distance", "0.12"],
  ])("rejects a citation whose %s has the wrong type", async (field, wrongValue) => {
    const citation = { ...SUCCESS_BODY.citations[0], [field]: wrongValue };
    mockFetch(async () => jsonResponse({ ...SUCCESS_BODY, citations: [citation] }));

    const error = (await askHrQuestion({ question: "q", tenant_id: "t" }).catch(
      (thrown: unknown) => thrown,
    )) as HrAskError;

    expect(error.kind).toBe("unexpected");
  });

  it("rejects a response where only one citation of several is malformed", async () => {
    mockFetch(async () =>
      jsonResponse({
        ...SUCCESS_BODY,
        citations: [SUCCESS_BODY.citations[0], { citation_id: "S2" }],
      }),
    );

    const error = (await askHrQuestion({ question: "q", tenant_id: "t" }).catch(
      (thrown: unknown) => thrown,
    )) as HrAskError;

    expect(error.kind).toBe("unexpected");
  });

  it("accepts an insufficient-evidence response carrying no citations", async () => {
    mockFetch(async () =>
      jsonResponse({
        answer: "I do not have enough approved HR information to answer this question.",
        insufficient_evidence: true,
        citations: [],
      }),
    );

    const response = await askHrQuestion({ question: "q", tenant_id: "t" });

    expect(response.insufficient_evidence).toBe(true);
    expect(response.citations).toEqual([]);
  });

  it("exposes the backend question limit to the UI", () => {
    expect(MAX_QUESTION_LENGTH).toBe(2000);
  });
});
