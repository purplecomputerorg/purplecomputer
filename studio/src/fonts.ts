// Served from Studio itself, not Google Fonts, so a visit contacts no one else.
import "@fontsource/figtree/400.css";
import "@fontsource/figtree/500.css";
import "@fontsource/figtree/600.css";
import "@fontsource/figtree/700.css";
import "@fontsource/caveat/500.css";
import "@fontsource/caveat/600.css";
import "@fontsource/caveat/700.css";
import "@fontsource/nunito/800.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/sora/800.css";
import "@fontsource/spectral/400-italic.css";
import "@fontsource/spectral/500-italic.css";

// Until Caveat arrives the browser draws handwriting in a stand-in font, so styles.css hides it till then.
const ready = () => document.documentElement.classList.add("handwriting");
void Promise.all([500, 600, 700].map((w) => document.fonts.load(`${w} 1em Caveat`))).then(ready, ready);
