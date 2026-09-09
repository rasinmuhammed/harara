import type { Metadata, Viewport } from "next";
import { Fraunces, Inter } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const SITE = "Harara — heat-safe shift planner";
const DESC =
  "Reshape the working day around the WBGT forecast: same work-hours, materially lower peak and tail heat load than Qatar's fixed 10:00–15:30 calendar ban.";

export const metadata: Metadata = {
  title: SITE,
  description: DESC,
  applicationName: "Harara",
  authors: [{ name: "Muhammed Rasin" }],
  openGraph: {
    title: SITE,
    description: DESC,
    type: "website",
  },
  twitter: { card: "summary_large_image", title: SITE, description: DESC },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbf9f5" },
    { media: "(prefers-color-scheme: dark)", color: "#15120e" },
  ],
  width: "device-width",
  initialScale: 1,
};

// no-flash theme init: runs before paint
const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem('harara-theme');if(t==='dark'||t==='light')document.documentElement.setAttribute('data-theme',t);}catch(e){}})();`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${fraunces.variable} ${inter.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <a href="#results" className="skip-link">
          Skip to results
        </a>
        {children}
      </body>
    </html>
  );
}
