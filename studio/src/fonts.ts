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

// Browsers fetch a face only when text first needs it, so Caveat's notes would draw in a stand-in
// font for a moment when they appear. Fetching it now has it ready long before Purple is.
export const handwriting = Promise.all([500, 600, 700].map((w) => document.fonts.load(`${w} 1em Caveat`))).catch(() => {});
