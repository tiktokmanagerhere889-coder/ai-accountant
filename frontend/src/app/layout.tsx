import type { Metadata } from "next";
import "./globals.css";

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
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
