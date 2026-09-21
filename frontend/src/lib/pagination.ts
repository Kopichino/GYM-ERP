import { api } from "./api";

/** One page of a list endpoint, as the API returns it. */
export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** Rows per page on screens that page through a list -- the server's default. */
export const PAGE_SIZE = 20;
/** The server's cap on `page_size`. */
const MAX_PAGE_SIZE = 100;
/** Stops a runaway walk: a hundred full pages is ten thousand rows. */
const MAX_PAGES = 100;

export async function fetchPage<T>(url: string, page = 1, params: Record<string, unknown> = {}) {
  const res = await api.get<Page<T>>(url, { params: { ...params, page } });
  return res.data;
}

/**
 * Every row of a paginated list, for the few places that need the whole set: a
 * picker, or a person's own history.
 *
 * Walks the pages by number rather than following `next`. That link is an
 * absolute URL built by the server, and requesting it would bypass the tenant
 * prefix this client adds to every path.
 */
export async function fetchAll<T>(url: string, params: Record<string, unknown> = {}) {
  const rows: T[] = [];
  for (let page = 1; page <= MAX_PAGES; page++) {
    const data = await fetchPage<T>(url, page, { ...params, page_size: MAX_PAGE_SIZE });
    rows.push(...data.results);
    if (!data.next || rows.length >= data.count) break;
  }
  return rows;
}
