import { render, screen, waitFor } from "@testing-library/react";
import { vi, beforeEach, it, expect } from "vitest";
import HealthBadge from "./HealthBadge";

beforeEach(() => vi.restoreAllMocks());

it("ok dot when health ok", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ status: "ok" }),
  } as unknown as Response));
  render(<HealthBadge />);
  await waitFor(() => expect(screen.getByTestId("health-dot")).toHaveClass("dot-ok"));
});

it("err dot when health fails", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
  render(<HealthBadge />);
  await waitFor(() => expect(screen.getByTestId("health-dot")).toHaveClass("dot-err"));
});
