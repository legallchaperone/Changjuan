import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "长卷",
  description: "老人原声采访到可信家庭故事",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
