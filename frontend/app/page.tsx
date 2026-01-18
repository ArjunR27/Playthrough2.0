"use client"

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function HomePage() {
    const [isChecking, setIsChecking] = useState(true);
    const router = useRouter();

    useEffect(() => {
        async function checkAuth() {
            try {
                const res = await fetch("http://127.0.0.1:3000/tracking", {
                    cache: "no-store",
                    credentials: "include",
                });

                if (res.status === 401) {
                    // Not logged in, show marketing page
                    setIsChecking(false);
                    return;
                }

                if (res.ok) {
                    // Logged in, redirect to dashboard
                    router.push('/dashboard');
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
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#191414] to-[#1DB954]">
                <div className="text-white text-xl">Loading...</div>
            </div>
        );
    }

    // Show marketing page if not logged in
    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#191414] to-[#1DB954]">
            <div className="max-w-4xl mx-auto text-center px-8">
                <h1 className="text-6xl font-bold text-white mb-6">
                    Playthrough
                </h1>
                <p className="text-xl text-white/80 mb-12">
                    Track your album listening progress and discover your music journey
                </p>
                <a
                    href="http://127.0.0.1:3000/"
                    className="inline-block bg-white text-[#191414] font-semibold px-8 py-4 rounded-full hover:bg-white/90 transition-all duration-200 text-lg shadow-lg"
                >
                    Track now
                </a>
            </div>
        </div>
    );
}