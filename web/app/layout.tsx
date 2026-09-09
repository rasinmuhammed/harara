import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

const TITLE = "Harara. Decide when to work by the forecast.";
const DESC =
  "Harara reads the weather forecast for your site, works out how hard the heat will be on the body hour by hour, and plans when the crew should work, ease off, or stop.";

export const metadata: Metadata = {
  metadataBase: new URL("https://harara.vercel.app"),
  title: TITLE,
  description: DESC,
  applicationName: "Harara",
  authors: [{ name: "Muhammed Rasin" }],
  openGraph: { title: TITLE, description: DESC, type: "website" },
  twitter: { card: "summary_large_image", title: TITLE, description: DESC },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0b0b0c" },
    { media: "(prefers-color-scheme: light)", color: "#fbfaf8" },
  ],
  width: "device-width",
  initialScale: 1,
};

const THEME_INIT = `(function(){try{var t=localStorage.getItem('harara-theme');if(t==='dark'||t==='light')document.documentElement.setAttribute('data-theme',t);}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className="font-sans">
        <a href="#main" className="skip-link">Skip to content</a>
        {children}
      </body>
    </html>
  );
}
