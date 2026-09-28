import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";
import { formatNumber, formatPercent } from "./lib/format";

const ROUTES = ["/", "/quellen", "/gibt-es-nicht"];

describe.each(ROUTES)("Route %s", (path) => {
  it("zeigt den Hinweis (Grundregel 5)", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getAllByTestId("disclaimer")[0].textContent).toContain("keine Anlageberatung");
  });
});

it("formatiert deutsch", () => {
  expect(formatNumber(1234.5)).toBe("1.234,50");
  expect(formatPercent(0.0123)).toContain("1,23");
});
