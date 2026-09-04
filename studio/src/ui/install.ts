import { packFilename } from "../pack";
import { h } from "./dom";
import type { View } from "./view";

export function installView(): View {
  const file = packFilename();
  return {
    title: "Getting it onto Purple",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Purple has no internet, no file manager, and no browser, on purpose. A pack goes in on a USB stick, and the stick's name is the whole trick."),
      h("h3", {}, "With a second USB stick"),
      h("ol", { class: "plain" },
        h("li", {}, "Take any USB stick and name it ", h("span", { class: "mono" }, "PURPLE_UPDATE"), ". On a Mac that is Disk Utility, Erase, and the name field; on Windows, right-click the drive, Format, and the volume label. Capitals and the underscore matter."),
        h("li", {}, "Copy ", h("span", { class: "mono" }, file), " onto it. More than one pack is fine."),
        h("li", {}, "Plug it into the Purple computer, then turn Purple on."),
      ),
      h("p", {}, "While Purple starts it notices the stick's name, reads the packs off it, and puts them where the rooms look. The new words, voices, pictures, and instruments are there from the first screen. If the stick goes in while Purple is already running, restart Purple once."),
      h("p", { class: "dim small" }, "This works the same whether Purple is installed on the laptop or running from the Purple Key. From the Key nothing is kept between sessions, so leave the stick plugged in alongside the Key and the packs come back every time. Purple only ever reads from the stick, and it ignores every stick with any other name."),
      h("h3", {}, "From the parent menu's terminal"),
      h("p", {}, "On an installed Purple, a pack on any stick can also be put in by hand. Open the parent menu, then the terminal, plug in the stick, and run:"),
      h("pre", {}, h("code", {}, [
        "sudo mkdir -p /mnt/stick",
        "sudo mount /dev/sdb1 /mnt/stick",
        `python3 -m purple_tui.usb_updater /mnt/stick`,
        "sudo umount /mnt/stick",
      ].join("\n"))),
      h("p", { class: "dim small" }, "The stick is usually ", h("span", { class: "mono" }, "/dev/sdb1"), "; ", h("span", { class: "mono" }, "lsblk"), " lists what is plugged in. Packs land in ", h("span", { class: "mono" }, "~/.purple/packs/"), "; to take one out again, delete its folder there."),
      h("h3", {}, "Sharing"),
      h("p", {}, "The pack is a plain file. Email it to Grandma, or put it on a stick for a cousin. There is no place to upload it and nothing to sign up for."),
    ),
    stage: () => null,
  };
}

export function formatView(): View {
  const tree = [
    "manifest.json                  id, name, version, type, format",
    "content/",
    "  emoji.json                   word -> emoji            Play room",
    "  synonyms.json                nickname -> word         Play room",
    "  rankings.txt                 one word per line        Play room autocomplete",
    "  letters/a.wav … 9.wav        your voice, per key      Music room, Say Letters",
    "  voice/<phrase>.wav           your voice, per phrase   spoken instead of Purple's voice",
    "  pictures/<name>.json, .png   paint list and preview   parent menu, Pictures",
    "  <instrument>/c1.wav … d7.wav one note per file        Music room",
    "  instruments/<name>.json      the slider numbers       re-rendered by Purple's own synth",
    "  theme.json                   background and key rows  not read yet",
  ].join("\n");
  return {
    title: "What is in the pack",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "A pack is a compressed folder. Everything in it is plain data: JSON, text, sound, and images. Purple checks each file before installing and refuses a pack that contains code."),
      h("pre", {}, h("code", {}, tree)),
      h("p", {}, "The third column is where each file shows up on Purple. The layout copies the folders Purple already uses for its own built-in sounds and words, and Purple's source repository documents it in ", h("span", { class: "mono" }, "studio/PACK_FORMAT.md"), " along with a small command-line tool that builds, checks, and installs packs without this page, for anyone who would rather write a pack by hand."),
    ),
    stage: () => null,
  };
}
