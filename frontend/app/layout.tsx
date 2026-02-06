import "./globals.css";
import Navbar from "./components/Navbar";
import { AuthProvider } from "./contexts/AuthContext";
import { Bebas_Neue, Sora } from "next/font/google";

const displayFont = Bebas_Neue({
  subsets: ["latin"],
  weight: ["400"],
  variable: "--font-display",
});

const bodyFont = Sora({
  subsets: ["latin"],
  weight: ["300", "400", "600"],
  variable: "--font-body",
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${displayFont.variable} ${bodyFont.variable}`}>
      <body className="font-body">
        <AuthProvider>
          <Navbar />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
