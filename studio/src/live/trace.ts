// Studio opened with ?trace logs Purple's startup and every message between Studio and Purple's frame.
export const TRACE = new URLSearchParams(parent.location.search).has("trace");
export const trace = (...what: unknown[]) => TRACE && console.info(...what);
