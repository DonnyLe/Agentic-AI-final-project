import { useEffect, useState } from "react";

export type Route =
  | { screen: "cases" }
  | { screen: "case"; caseId: string }
  | { screen: "runs" }
  | { screen: "run"; evaluationId: string }
  | { screen: "policy" };

function parse(hash: string): Route {
  const [screen, id] = hash.replace(/^#\/?/, "").split("/");

  if (screen === "cases" && id) {
    return { screen: "case", caseId: decodeURIComponent(id) };
  }

  if (screen === "runs" && id) {
    return { screen: "run", evaluationId: id };
  }

  if (screen === "runs") {
    return { screen: "runs" };
  }

  if (screen === "policy") {
    return { screen: "policy" };
  }

  return { screen: "cases" };
}

export function href(route: Route): string {
  switch (route.screen) {
    case "case":
      return `#/cases/${encodeURIComponent(route.caseId)}`;
    case "run":
      return `#/runs/${route.evaluationId}`;
    default:
      return `#/${route.screen}`;
  }
}

export function navigate(route: Route) {
  window.location.hash = href(route);
}

/** The current route, from the URL hash so links and the back button just work. */
export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);

    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return route;
}
