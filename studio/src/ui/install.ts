import { packFilename } from "../pack";
import { packId } from "../state";
import { h } from "./dom";

export function installView(): HTMLElement {
  const file = packFilename();
  const id = packId();
  return h(
    "section",
    {},
    h("h2", {}, "Getting it onto Purple"),
    h("p", { class: "lead" }, "Purple has no internet, no file manager, and no browser, on purpose. So moving a pack over is a hands-on step, and today it only works on a Purple that has been installed onto the laptop."),
    h("h3", {}, "If Purple is installed on the laptop"),
    h("ol", { class: "plain" },
      h("li", {}, "Copy ", h("span", { class: "mono" }, file), " onto any USB stick."),
      h("li", {}, "On Purple, open the parent menu, then the terminal."),
      h("li", {}, "Plug in the stick and run:"),
    ),
    h("pre", {}, h("code", {}, [
      "sudo mkdir -p /mnt/stick",
      "sudo mount /dev/sdb1 /mnt/stick",
      `mkdir -p ~/.purple/packs/${id}`,
      `tar -xzf /mnt/stick/${file} -C ~/.purple/packs/${id}`,
      "sudo umount /mnt/stick",
    ].join("\n"))),
    h("p", { class: "dim small" }, "The stick is usually ", h("span", { class: "mono" }, "/dev/sdb1"), "; ", h("span", { class: "mono" }, "lsblk"), " lists what is plugged in. Restart Purple and the new words are there. To take the pack out again, delete that folder."),
    h("h3", {}, "If your kid runs Purple from the Key"),
    h("p", {}, "A pack cannot be added yet. The Purple Key is read-only and forgets everything at shutdown, including anything copied onto it. That is what makes it safe to hand to a three-year-old, and it also means there is nowhere for a pack to live. Keep the file; it will still be good."),
    h("h3", {}, "Sharing"),
    h("p", {}, "The pack is a plain file. Email it to Grandma, or put it on a stick for a cousin. There is no place to upload it and nothing to sign up for."),
  );
}

export function formatView(): HTMLElement {
  const tree = [
    "manifest.json                 id, name, version, type: \"emoji\"",
    "content/",
    "  emoji.json                  word -> emoji            read by Purple today",
    "  synonyms.json               nickname -> word         read by Purple today",
    "  rankings.txt                one word per line        read by Purple today",
    "  letters/a.wav … 9.wav       your voice, per key      proposed",
    "  voice/<phrase>.wav          your voice, per phrase   proposed",
    "  pictures/<name>.json, .png  paint list and preview   proposed",
    "  <instrument>/c1.wav … d7.wav one note per file       proposed",
    "  theme.json                  background and key rows  proposed",
  ].join("\n");
  return h(
    "section",
    {},
    h("h2", {}, "What is in the pack"),
    h("p", { class: "lead" }, "A pack is a compressed folder. Everything in it is plain data: JSON, text, sound, and images. Purple refuses packs that contain code."),
    h("pre", {}, h("code", {}, tree)),
    h("p", {}, "The three lines marked as read today match Purple's own core emoji pack exactly. The proposed ones copy the folder layout Purple already uses for its built-in sounds, so the change on Purple's side is small. The full write-up lives in the source repository as ", h("span", { class: "mono" }, "studio/PACK_FORMAT.md"), "."),
  );
}
