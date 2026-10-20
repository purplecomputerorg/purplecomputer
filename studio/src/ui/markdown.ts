// Just enough Markdown for Studio's own guides: headings, paragraphs, lists, tables, fenced code,
// `code`, and **bold**. Text only ever becomes text nodes, never HTML.
import { h } from "./dom";

function inline(text: string): (Node | string)[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/).filter(Boolean).map((part) =>
    part.startsWith("`") ? h("code", {}, part.slice(1, -1)) : part.startsWith("**") ? h("b", {}, part.slice(2, -2)) : part);
}

const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map((c) => c.trim());

export function markdown(source: string): HTMLElement[] {
  const out: HTMLElement[] = [];
  const lines = source.split("\n");
  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    const take = (more: (l: string) => boolean) => {
      const block = [];
      while (i < lines.length && more(lines[i])) block.push(lines[i++]);
      return block;
    };
    if (!line.trim()) {
      i++;
    } else if (line.startsWith("```")) {
      i++;
      out.push(h("pre", {}, take((l) => !l.startsWith("```")).join("\n")));
      i++;
    } else if (/^#{1,3} /.test(line)) {
      const level = line.indexOf(" ");
      out.push(h(level === 1 ? "h2" : "h3", {}, ...inline(line.slice(level + 1))));
      i++;
    } else if (line.startsWith("|")) {
      const [head, , ...rows] = take((l) => l.startsWith("|"));
      out.push(h("table", {}, h("thead", {}, h("tr", {}, ...cells(head).map((c) => h("th", {}, ...inline(c))))),
        h("tbody", {}, ...rows.map((r) => h("tr", {}, ...cells(r).map((c) => h("td", {}, ...inline(c))))))));
    } else if (line.startsWith("- ")) {
      out.push(h("ul", {}, ...take((l) => l.startsWith("- ")).map((l) => h("li", {}, ...inline(l.slice(2))))));
    } else {
      out.push(h("p", {}, ...inline(take((l) => !!l.trim() && !/^(#|```|\||- )/.test(l)).join(" "))));
    }
  }
  return out;
}
