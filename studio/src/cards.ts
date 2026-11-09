// cards.html: the home page's six cards alone, for purplecomputer.org to show in an iframe. Each
// opens its Studio page in a new tab, and tells the landing page which one was opened.
import "./fonts";
import "./styles.css";
import { startEmojiPictures } from "./emoji";
import { embed } from "./embed";
import { homeCards, SECTIONS } from "./ui/home";
import { h } from "./ui/dom";

const app = document.getElementById("app")!;
// bleed: the room left beside the cards for their shadows (styles.css, .embed .home-cards), so the landing
// page can widen the frame by just that much and keep the cards in line with its column, whichever deploys first.
// Keep it at most 24px: that is the landing page's gutter on a phone.
const bleed = () => ({ bleed: parseFloat(getComputedStyle(app.querySelector(".home-cards")!).marginLeft) || 0 });
const tell = embed(app, undefined, bleed);
app.append(h("section", { class: "home" }, homeCards(SECTIONS, (id) => tell({ opened: id }))));
void startEmojiPictures();
