import { render, screen, act } from "@testing-library/react";
import { it, expect } from "vitest";
import Toast from "./Toast";
import { useAppStore } from "../store/appStore";

it("renders queued toasts from the store", () => {
  render(<Toast />);
  act(() => useAppStore.getState().pushToast("err", "boom"));
  expect(screen.getByText("boom")).toBeInTheDocument();
});
