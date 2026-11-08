// cards.html: the home page's six cards alone, for purplecomputer.org to show in an iframe. Each
// opens its Studio page in a new tab, and tells the landing page which one was opened.
import "./fonts";
import "./styles.css";
import { startEmojiPictures } from "./emoji";
import { embed } from "./embed";
import { homeCards, SECTIONS } from "./ui/home";
import { h } from "./ui/dom";

const app = document.getElementById("app")!;
const tell = embed(app);
app.append(h("section", { class: "home" }, homeCards(SECTIONS, (id) => tell({ opened: id }))));
void startEmojiPictures();
