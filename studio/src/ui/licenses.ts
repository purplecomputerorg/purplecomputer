import { features } from "../state";
import { h } from "./dom";
import type { View } from "./view";

const REPO = "https://github.com/purplecomputerorg/purplecomputer";
const out = (href: string, text: string, cls?: string) => h("a", { href, class: cls, target: "_blank", rel: "noopener" }, text);

type Credit = [name: string, href: string, does: string, license: string, extra?: Node];

const credit = ([name, href, does, license, extra]: Credit) =>
  h("li", {}, h("div", { class: "credit-head" }, out(href, name), h("span", { class: "license" }, license)), h("p", {}, does), extra ?? "");

// espeak-ng is GPL: its source is served right beside the voice it builds.
const espeakSource = () => h("p", { class: "credit-source" }, "Source for Studio's WebAssembly build: ",
  out("voice/espeak-ng/README.md", "notes"), ", ", out("voice/espeak-ng/espeak_bridge.c", "bridge"), ", ", out("voice/espeak-ng/build.sh", "build script"), ".");

const purple = (): Credit[] => [
  ["Ubuntu", "https://ubuntu.com/legal/open-source-licences", "The base OS.", "Various"],
  ["Debian", "https://www.debian.org/legal/licenses/", "The base OS on 32-bit machines.", "Various"],
  ["Python", "https://www.python.org", "Purple's language and runtime.", "PSF"],
  ["pygame-ce", "https://pyga.me", "Rendering and audio.", "LGPL-2.1"],
  ["Piper voice", "https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/libritts_r/medium", "Text to speech model, run on device.", "CC BY 4.0"],
  ["espeak-ng", "https://github.com/espeak-ng/espeak-ng", "Phonemizer for the Piper voice.", "GPL-3.0", espeakSource()],
  ["spectral.js", "https://github.com/rvanwijnen/spectral.js", "Paint mixing in the Art room.", "MIT"],
  ["Noto Color Emoji", "https://github.com/googlefonts/noto-emoji", "Emoji font.", "OFL-1.1"],
  ["Twemoji", "https://github.com/jdecked/twemoji", "Source art for some stickers and Studio's icons.", "CC BY 4.0"],
];

const STUDIO: Credit[] = [
  ["Pyodide", "https://pyodide.org", "Runs Purple's Python in the browser.", "MPL-2.0"],
  ["ONNX Runtime Web", "https://onnxruntime.ai", "Runs the voice models in the browser.", "MIT"],
  ...(features.rooms ? [
    ["Kokoro", "https://huggingface.co/hexgrad/Kokoro-82M", "Text to speech for rooms made in Studio.", "Apache-2.0"],
    ["Blockly", "https://developers.google.com/blockly", "The blocks for making rooms.", "Apache-2.0"],
  ] satisfies Credit[] : []),
  ["Emojibase", "https://emojibase.dev", "Emoji search in the emoji picker.", "MIT"],
  ["Figtree, Inter, Sora, Caveat, Nunito, Spectral", "https://fontsource.org", "Studio's fonts, self-hosted.", "OFL-1.1"],
];

export function licensesView(): View {
  return {
    title: "Open source licenses",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "The open source projects Purple and Purple Studio are built on."),
      h("div", { class: "card code-card" },
        h("h3", {}, "Purple's source"),
        h("p", {}, "All of Purple's code, Studio included, is public on GitHub."),
        h("p", { class: "row" }, out(REPO, "Purple on GitHub", "btn"), out(`${REPO}/tree/main/studio`, "How Studio works")),
        h("p", { class: "dim" }, "Purple itself is under the ", out(`${REPO}/blob/main/LICENSE`, "Purple Computer Source-Available License 1.1"), ": personal use and modification are allowed, redistribution and commercial use are not."),
      ),
      h("h3", {}, "Inside Purple"),
      h("ul", { class: "credits" }, ...purple().map(credit)),
      h("h3", {}, "Inside Purple Studio"),
      h("ul", { class: "credits" }, ...STUDIO.map(credit)),
    ),
  };
}
