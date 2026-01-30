"use client"

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '../contexts/AuthContext';

export default function Navbar() {
    const pathname = usePathname();
    const { isAuthenticated } = useAuth();

    // Don't show navbar if not authenticated
    if (isAuthenticated !== true) {
        return null;
    }

    // Show loading state while checking (or show navbar if authenticated)
    const navLinks = [
        { href: '/wall', label: 'Wall' },
        { href: '/completions', label: 'Completions' },
        { href: '/recents', label: 'Recents' },
        { href: '/profile', label: 'Profile' },
    ];

    return (
        <nav className="bg-gradient-to-br from-[#191414] to-[#1DB954] border-b border-white/20">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 sm:py-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <Link href="/wall" className="font-display text-xl sm:text-2xl font-bold text-white">
                        Playthrough
                    </Link>
                    <div className="flex flex-wrap justify-center sm:justify-end gap-2 sm:gap-4 font-display w-full sm:w-auto">
                        {navLinks.map((link) => (
                            <Link
                                key={link.href}
                                href={link.href}
                                className={`px-3 py-1.5 sm:px-4 sm:py-2 text-sm sm:text-base rounded-lg whitespace-nowrap transition-all duration-200 ${
                                    pathname === link.href
                                        ? 'bg-white/20 text-white font-semibold'
                                        : 'text-white/70 hover:text-white hover:bg-white/10'
                                }`}
                            >
                                {link.label}
                            </Link>
                        ))}
                    </div>
                </div>
            </div>
        </nav>
    );
}
