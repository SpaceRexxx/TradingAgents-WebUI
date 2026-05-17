import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { it, expect } from "vitest";
import TabNav from "./TabNav";

it("renders 4 tab links with correct hrefs", () => {
  render(<MemoryRouter initialEntries={["/analysis"]}><TabNav /></MemoryRouter>);
  expect(screen.getByRole("link", { name: "分析" })).toHaveAttribute("href", "/analysis");
  expect(screen.getByRole("link", { name: "历史" })).toHaveAttribute("href", "/history");
  expect(screen.getByRole("link", { name: "配置" })).toHaveAttribute("href", "/config");
  expect(screen.getByRole("link", { name: "诊断" })).toHaveAttribute("href", "/diagnostics");
});
