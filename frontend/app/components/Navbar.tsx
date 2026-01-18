"use client"

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Navbar() {
    const pathname = usePathname();
    const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);

    useEffect(() => {
        async function checkAuth() {
            try {
                const res = await fetch("http://127.0.0.1:3000/tracking", {
                    cache: "no-store",
                    credentials: "include",
                });

                setIsAuthenticated(res.status !== 401);
            } catch (err) {
                setIsAuthenticated(false);
            }
        }

        checkAuth();
        
        // Listen for auth change events (e.g., when user signs out)
        const handleAuthChange = () => {
            checkAuth();
        };
        
        window.addEventListener('auth-change', handleAuthChange);
        
        // Re-check when pathname changes
        const interval = setInterval(checkAuth, 1000);
        
        return () => {
            clearInterval(interval);
            window.removeEventListener('auth-change', handleAuthChange);
        };
    }, [pathname]);

    // Don't show navbar if not authenticated
    if (isAuthenticated === false) {
        return null;
    }

    // Show loading state while checking (or show navbar if authenticated)
    const navLinks = [
        { href: '/dashboard', label: 'Dashboard' },
        { href: '/wall', label: 'Wall' },
        { href: '/recents', label: 'Recents' },
        { href: '/profile', label: 'Profile' },
    ];

    return (
        <nav className="bg-white/10 backdrop-blur-lg border-b border-white/20">
            <div className="max-w-7xl mx-auto px-8 py-4">
                <div className="flex items-center justify-between">
                    <Link href="/dashboard" className="text-2xl font-bold text-white">
                        Playthrough
                    </Link>
                    <div className="flex gap-6">
                        {navLinks.map((link) => (
                            <Link
                                key={link.href}
                                href={link.href}
                                className={`px-4 py-2 rounded-lg transition-all duration-200 ${
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
