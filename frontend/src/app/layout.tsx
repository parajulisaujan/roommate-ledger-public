import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "RoommateLedger — Personal & shared finances",
  description: "Private spending. Shared household costs. Clear balances.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
