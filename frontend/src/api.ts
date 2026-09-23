import type { Analysis, Health, Mode } from "./types";
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${url}`, init);
  } catch {
    throw new Error(
      "Cannot reach the analysis service. Check that the backend is running, then try again.",
    );
  }
  if (!response.ok) {
    let message = `Request failed (${response.status}). Please try again.`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail))
        message = body.detail.map((e: { msg: string }) => e.msg).join("; ");
    } catch {
      /* Keep HTTP status when no JSON is returned. */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export const api = {
  health: () => request<Health>("/health"),
  list: () => request<Analysis[]>("/analyses"),
  get: (id: string) => request<Analysis>(`/analyses/${encodeURIComponent(id)}`),
  create: (title: string, mode: Mode, before: File[], after: File[]) => {
    const data = new FormData();
    data.append("title", title);
    data.append("mode", mode);
    before.forEach((file) => data.append("before_files", file));
    after.forEach((file) => data.append("after_files", file));
    return request<Analysis>("/analyses", { method: "POST", body: data });
  },
  demo: (mode: Mode) =>
    request<Analysis>(`/analyses/demo?mode=${mode}`, { method: "POST" }),
};
