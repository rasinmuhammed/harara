import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Harara style guide",
  robots: { index: false, follow: false },
};

export default function StyleguideLayout({ children }: { children: React.ReactNode }) {
  return children;
}
