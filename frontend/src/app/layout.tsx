import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Providers from "@/components/providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "HYLIST — Intelligent Task Orchestration",
  description:
    "AI-powered task management with ML priority prediction and NLP auto-tagging. Built for high-performance engineering teams.",
  keywords: ["task management", "AI", "kanban", "ML", "productivity"],
  openGraph: {
    title: "HYLIST",
    description: "AI-powered task orchestration",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} h-full dark`}>
      <body className="h-full bg-slate-950 font-sans text-slate-100 antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
