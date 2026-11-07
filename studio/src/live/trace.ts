// Studio opened with ?trace logs Purple's startup and every message between Studio and Purple's frame.
// purple.html reads it off its Studio page; try.html, inside another site's page, can only read its own.
const search = (): string => { try { return parent.location.search; } catch { return location.search; } };
export const TRACE = new URLSearchParams(search()).has("trace");
export const trace = (...what: unknown[]) => TRACE && console.info(...what);
