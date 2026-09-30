import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";

const geist = localFont({
  src: [
    { path: "./fonts/Geist-Regular.ttf", weight: "400" },
    { path: "./fonts/Geist-Medium.ttf", weight: "500" },
    { path: "./fonts/Geist-SemiBold.ttf", weight: "600" },
    { path: "./fonts/Geist-Bold.ttf", weight: "700" },
  ],
  variable: "--font-geist",
  display: "swap",
});

const newsreader = localFont({
  src: [
    { path: "./fonts/Newsreader-Regular.ttf", weight: "400" },
    { path: "./fonts/Newsreader-Italic.ttf", weight: "400", style: "italic" },
    { path: "./fonts/Newsreader-Medium.ttf", weight: "500" },
    { path: "./fonts/Newsreader-SemiBold.ttf", weight: "600" },
  ],
  variable: "--font-newsreader",
  display: "swap",
});

const geistMono = localFont({
  src: [{ path: "./fonts/GeistMono-Regular.ttf", weight: "400" }],
  variable: "--font-geist-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Factify: know what's true before you share it", template: "%s · Factify" },
  description:
    "Factify checks forwards, news links, pictures, videos and voice notes against reliable sources, and shows every source it used.",
  icons: { icon: "/seal.svg" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f3ee" },
    { media: "(prefers-color-scheme: dark)", color: "#151513" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* The chosen theme, applied before the first paint so the page never flashes. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('fct_theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}",
          }}
        />
      </head>
      <body className={`${geist.variable} ${newsreader.variable} ${geistMono.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
