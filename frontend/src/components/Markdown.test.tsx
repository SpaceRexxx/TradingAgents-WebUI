import { render, screen } from "@testing-library/react";
import { it, expect } from "vitest";
import Markdown from "./Markdown";

it("renders headings and gfm tables", () => {
  render(<Markdown>{"# Title\n\n| a | b |\n|---|---|\n| 1 | 2 |"}</Markdown>);
  expect(screen.getByRole("heading", { name: "Title" })).toBeInTheDocument();
  expect(screen.getByRole("table")).toBeInTheDocument();
});

it("renders empty string without crashing", () => {
  const { container } = render(<Markdown>{""}</Markdown>);
  expect(container).toBeInTheDocument();
});
