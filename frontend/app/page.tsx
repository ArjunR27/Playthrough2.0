"use client"

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { API_BASE } from './lib/api';

export default function HomePage() {
    const [isChecking, setIsChecking] = useState(true);
    const router = useRouter();

    useEffect(() => {
        async function checkAuth() {
            try {
                const res = await fetch(`${API_BASE}/tracking`, {
                    cache: "no-store",
                    credentials: "include",
                });

                if (res.status === 401) {
                    // Not logged in, show marketing page
                    setIsChecking(false);
                    return;
                }

                if (res.ok) {
                    // Logged in, redirect to wall
                    router.push('/wall');
                    return;
                }

                // If there's an error, show marketing page
                setIsChecking(false);
            } catch (err) {
                // On error, show marketing page
                setIsChecking(false);
            }
        }

        checkAuth();
    }, [router]);

    // Show loading state while checking auth
    if (isChecking) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-[#1D1411] to-[#0F0B09]">
                <div className="text-white text-xl">Loading...</div>
            </div>
        );
    }

    // Show marketing page if not logged in
    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-[#1D1411] to-[#0F0B09]">
            <div className="max-w-4xl mx-auto text-center px-8">
                <h1 className="font-display text-5xl sm:text-6xl tracking-[0.12em] uppercase text-white mb-6">
                    Playthrough
                </h1>
                <p className="text-lg sm:text-xl text-white/70 mb-12">
                    Track your album listening progress and discover your music journey
                </p>
                <a
                    href={`${API_BASE}/`}
                    className="inline-flex items-center justify-center text-[11px] sm:text-xs uppercase tracking-widest px-6 py-3 rounded-full border border-[#f5d7a0]/70 text-[#f5d7a0] hover:border-[#f5d7a0] hover:text-[#f5d7a0] transition-colors"
                >
                    Track now
                </a>
            </div>
        </div>
    );
}
