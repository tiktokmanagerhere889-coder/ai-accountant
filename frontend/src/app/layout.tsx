import type { Metadata } from "next";
import "./globals.css";
import { Inter } from "next/font/google";
import { cn } from "@/lib/utils";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "AI Accountant Portal",
  description: "High-trust professional financial accounting interface",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className={cn("font-sans", inter.variable)}>
      <head>
        {/* Pre-paint theme bootstrap: apply the persisted theme before first
            paint to avoid a light flash for dark-mode users. Mirrors the
            reconciliation in page.tsx (defaults to dark when nothing stored). */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function () {
  try {
    var theme = localStorage.getItem("theme");
    if (theme === "dark" || theme === null) {
      document.documentElement.classList.add("dark");
    }
  } catch (e) {}
})();`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
