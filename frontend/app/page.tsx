"use client"

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { API_BASE } from './lib/api';

export default function HomePage() {
    const [isChecking, setIsChecking] = useState(true);
    const [authError, setAuthError] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
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
            } catch {
                // On error, show marketing page
                setIsChecking(false);
            }
        }

        checkAuth();
    }, [router]);

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        if (params.get('auth') === 'error') {
            setAuthError("Last.fm authentication failed. Please try again.");
        }
    }, []);

    const startSpotifyLogin = async () => {
        setAuthError(null);
        setIsSubmitting(true);
        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({ provider: "spotify" }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data?.login_url) {
                throw new Error(data?.error || "login_failed");
            }
            window.location.href = data.login_url;
        } catch {
            setAuthError("Failed to start Spotify login. Please try again.");
            setIsSubmitting(false);
        }
    };

    const startLastfmLogin = async () => {
        setAuthError(null);
        setIsSubmitting(true);
        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({ provider: "lastfm" }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data?.login_url) {
                throw new Error(data?.error || "login_failed");
            }
            window.location.href = data.login_url;
        } catch {
            setAuthError("Failed to start Last.fm login. Please try again.");
            setIsSubmitting(false);
        }
    };

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
                <h1 className="font-display text-5xl sm:text-6xl tracking-[0.12em] uppercase text-white mb-6">
                    Playthrough
                </h1>
                <p className="text-lg sm:text-xl text-white/70 mb-12">
                    Track your album listening progress and discover your music journey
                </p>
                <div className="flex flex-col items-center gap-6">
                    <p style={{color: "#d63a4a"}}> Spotify Login: Limited Access</p>
                    <button
                        onClick={startSpotifyLogin}
                        disabled={isSubmitting}
                        className="inline-flex items-center justify-center text-[11px] sm:text-xs uppercase tracking-widest px-6 py-3 rounded-full border border-[#f5d7a0]/70 text-[#f5d7a0] hover:border-[#f5d7a0] hover:text-[#f5d7a0] transition-colors disabled:opacity-60"
                    >
                        Continue with Spotify
                    </button>

                    <div className="flex flex-col items-center gap-6">
                        <button
                            onClick={startLastfmLogin}
                            disabled={isSubmitting}
                            className="inline-flex items-center justify-center text-[11px] sm:text-xs uppercase tracking-widest px-6 py-3 rounded-full border border-red-300/40 text-red-200 hover:border-red-200 hover:text-red-100 transition-colors disabled:opacity-60"
                        >
                            Continue with Last.fm
                        </button>
                        <a
                            href="https://www.last.fm/join"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs uppercase tracking-widest text-white/70 hover:text-white transition-colors text-center"
                        >
                            Create a Last.fm account
                        </a>
                    </div>

                    {authError && (
                        <p className="text-sm text-red-200">{authError}</p>
                    )}
                </div>
            </div>
        </div>
    );
}
