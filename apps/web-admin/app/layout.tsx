import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "长卷 Admin",
  description: "Phase 1 operations console",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
