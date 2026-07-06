import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ZoidLab · AI Workflow Builder",
  description: "Visually build, test, and deploy AI workflows on the Nyquest runtime.",
  icons: { icon: "/logo.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
