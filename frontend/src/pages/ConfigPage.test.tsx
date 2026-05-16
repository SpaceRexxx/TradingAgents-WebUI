import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, beforeEach, it, expect } from "vitest";
import ConfigPage from "./ConfigPage";

const PROVIDERS = {
  providers: [
    { id: "deepseek", name: "deepseek", env_var: "DEEPSEEK_API_KEY", base_url: "https://api.deepseek.com", configured: true },
    { id: "volcengine", name: "volcengine", env_var: "ARK_API_KEY", base_url: "https://ark...", configured: false },
  ],
};

beforeEach(() => vi.restoreAllMocks());

function fetchMock(handler: (url: string, init?: RequestInit) => { status?: number; body: unknown }) {
  return vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
    const { status = 200, body } = handler(url, init);
    return { ok: status < 300, status, json: async () => body } as unknown as Response;
  });
}

it("lists providers, never shows a key", async () => {
  vi.stubGlobal("fetch", fetchMock(() => ({ body: PROVIDERS })));
  render(<ConfigPage />);
  await waitFor(() => expect(screen.getByText("deepseek")).toBeInTheDocument());
  expect(screen.getByText("volcengine")).toBeInTheDocument();
  expect(screen.queryByText(/sk-/)).toBeNull();
});

it("submits a key", async () => {
  const f = fetchMock((url, init) =>
    init?.method === "POST" && url.endsWith("/key")
      ? { body: { id: "volcengine", configured: true } } : { body: PROVIDERS });
  vi.stubGlobal("fetch", f);
  render(<ConfigPage />);
  await waitFor(() => screen.getByText("volcengine"));
  await userEvent.type(screen.getByTestId("key-input-volcengine"), "ark-secret");
  await userEvent.click(screen.getByTestId("key-save-volcengine"));
  await waitFor(() =>
    expect(f).toHaveBeenCalledWith("/api/providers/volcengine/key",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ api_key: "ark-secret" }) })));
});

it("test button shows result", async () => {
  const f = fetchMock((url, init) =>
    init?.method === "POST" && url.endsWith("/test")
      ? { body: { id: "deepseek", ok: true, reason: "reachable", status: 200 } } : { body: PROVIDERS });
  vi.stubGlobal("fetch", f);
  render(<ConfigPage />);
  await waitFor(() => screen.getByText("deepseek"));
  await userEvent.click(screen.getByTestId("key-test-deepseek"));
  await waitFor(() => expect(screen.getByText(/reachable/)).toBeInTheDocument());
});
