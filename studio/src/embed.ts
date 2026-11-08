// The pages purplecomputer.org shows in an iframe (try.html, cards.html). The landing page says hello,
// and from then on hears the page's height, so the frame fits it, plus whatever the page adds.
export type FromEmbed = { type: "purple-embed"; height: number } & Record<string, unknown>;

// purplecomputer.org, its Vercel previews, and its dev server.
const EMBEDDER = /^(https:\/\/(www\.)?purplecomputer\.org|https:\/\/landing-[a-z0-9-]+-tavinathanson\.vercel\.app|http:\/\/(localhost|simba):3002)$/;

// Returns tell(), which sends the height and state() along with anything extra.
export function embed(app: HTMLElement, onMessage: (m: { type: string } & Record<string, unknown>) => void = () => {}, state: () => object = () => ({})) {
  let parentOrigin: string | null = null;
  const tell = (extra: object = {}) => {
    if (!parentOrigin) return;
    const m: FromEmbed = { type: "purple-embed", height: Math.max(app.scrollHeight, Math.ceil(app.getBoundingClientRect().height)), ...state(), ...extra };
    parent.postMessage(m, parentOrigin);
  };
  addEventListener("message", (e: MessageEvent) => {
    if (!EMBEDDER.test(e.origin) || typeof e.data?.type !== "string") return;
    parentOrigin = e.origin;
    onMessage(e.data);
    tell();
  });
  // The page's own height, not the window's, so the frame can shrink to fit as well as grow.
  new ResizeObserver(() => tell()).observe(app);
  return tell;
}
