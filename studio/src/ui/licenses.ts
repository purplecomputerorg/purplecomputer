import { features } from "../state";
import { h } from "./dom";
import type { View } from "./view";

const REPO = "https://github.com/purplecomputerorg/purplecomputer";
const out = (href: string, text: string, cls?: string) => h("a", { href, class: cls, target: "_blank", rel: "noopener" }, text);

type Credit = [name: string, href: string, does: string, license: string, extra?: Node];

const credit = ([name, href, does, license, extra]: Credit) =>
  h("li", {}, h("div", { class: "credit-head" }, out(href, name), h("span", { class: "license" }, license)), h("p", {}, does), extra ?? "");

// espeak-ng is GPL: its source is served right beside the voice it builds.
const espeakSource = () => h("p", { class: "credit-source" }, "Its source, as Studio builds it: ",
  out("voice/espeak-ng/README.md", "notes"), ", ", out("voice/espeak-ng/espeak_bridge.c", "bridge"), ", ", out("voice/espeak-ng/build.sh", "build script"), ".");

const purple = (): Credit[] => [
  ["Ubuntu", "https://ubuntu.com/legal/open-source-licences", "The Linux Purple starts on, underneath everything else.", "Mostly GPL"],
  ["Python", "https://www.python.org", "The language Purple is written in, and the one kids write code in.", "PSF"],
  ["pygame-ce", "https://pyga.me", "Draws Purple's screen and plays its sounds.", "LGPL-2.1"],
  ["Piper voice", "https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/libritts_r/medium", "Purple's voice, which speaks right on the laptop.", "CC BY 4.0"],
  ["espeak-ng", "https://github.com/espeak-ng/espeak-ng", "Tells Purple's voice how each word sounds.", "GPL-3.0", espeakSource()],
  ["spectral.js", "https://github.com/rvanwijnen/spectral.js", "Mixes paint in the Art room, so yellow and blue make green.", "MIT"],
  ["Noto Color Emoji", "https://github.com/googlefonts/noto-emoji", "Every emoji Purple draws.", "OFL-1.1"],
  ["Twemoji", "https://github.com/jdecked/twemoji", "The drawings behind a few stickers and Studio's icons, recolored purple.", "CC BY 4.0"],
];

const STUDIO: Credit[] = [
  ["Pyodide", "https://pyodide.org", "Runs Purple's own Python right in your browser.", "MPL-2.0"],
  ["ONNX Runtime Web", "https://onnxruntime.ai", "Runs Purple's voice in your browser.", "MIT"],
  ...(features.rooms ? [["Kokoro", "https://huggingface.co/hexgrad/Kokoro-82M", "The voice for the rooms you make.", "Apache-2.0"] satisfies Credit] : []),
  ["Emojibase", "https://emojibase.dev", "Lets you find an emoji by name, so \"lol\" finds 😂.", "MIT"],
  ["Figtree, Inter, Sora, Caveat, Nunito, Spectral", "https://fontsource.org", "Studio's lettering, served from here so a visit contacts no one else.", "OFL-1.1"],
];

export function licensesView(): View {
  return {
    title: "Open source licenses",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Purple is built on work that people around the world share freely. Here is what's inside, and what each piece does."),
      h("div", { class: "card code-card" },
        h("h3", {}, "Read Purple's code"),
        h("p", {}, "All of Purple's code, and Purple Studio's, is public on GitHub, so you can see exactly what runs on your kid's computer. Curious how the Art room mixes paint, or how Purple talks? It's all there."),
        h("p", { class: "row" }, out(REPO, "Purple on GitHub", "btn"), out(`${REPO}/tree/main/studio`, "How Studio works")),
        h("p", { class: "dim" }, "You're welcome to change your own copy for personal use. Purple is a paid product with its own ", out(`${REPO}/blob/main/LICENSE`, "license"), ", so please don't share or resell it."),
      ),
      h("h3", {}, "Inside Purple"),
      h("ul", { class: "credits" }, ...purple().map(credit)),
      h("h3", {}, "Inside Purple Studio"),
      h("ul", { class: "credits" }, ...STUDIO.map(credit)),
      h("p", { class: "dim" }, "Thank you to everyone who makes these."),
    ),
  };
}
