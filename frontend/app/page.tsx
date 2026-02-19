"use client"

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { API_BASE } from './lib/api';
import { useAuth } from './contexts/AuthContext';

export default function HomePage() {
    const [authError, setAuthError] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [isHelpOpen, setIsHelpOpen] = useState(false); 
    const router = useRouter();
    const { isAuthenticated } = useAuth();

    useEffect(() => {
        if (isAuthenticated === true) {
            router.push('/wall');
        }
    }, [isAuthenticated, router]);

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
    if (isAuthenticated === null) {
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
                    <button
                        onClick = {() => setIsHelpOpen(true)}
                        className="inline-flex items-center justify-center text-[11px] sm:text-xs uppercase tracking-widest px-6 py-3 rounded-full border border-[#0b2b1e] bg-[#0b2b1e] text-[#d9f5e6] hover:bg-[#0f3a28] hover:border-[#0f3a28] transition-colors">
                        Instructions
                    </button> 

                    <button
                    onClick={startSpotifyLogin}
                    disabled={isSubmitting}
                    className="inline-flex items-center gap-2 justify-center text-[11px] sm:text-xs uppercase tracking-widest px-6 py-3 rounded-full border border-[#f5d7a0]/70 text-[#f5d7a0] hover:border-[#f5d7a0] hover:text-[#f5d7a0] transition-colors disabled:opacity-60"
                    >
                    Continue with Spotify
                    <span className="rounded-full border border-[#f5d7a0]/50 px-2 py-[2px] text-[9px] tracking-widest">
                        INVITE ONLY
                    </span>
                    </button>


                    <div className="flex flex-col items-center gap-6">
                        <button
                            onClick={startLastfmLogin}
                            disabled={isSubmitting}
                            className="inline-flex items-center gap-2 justify-center text-[11px] sm:text-xs uppercase tracking-widest px-6 py-3 rounded-full border border-red-300/40 text-red-200 hover:border-red-200 hover:text-red-100 transition-colors disabled:opacity-60"
                        >
                        Continue with Last.fm
                        <span className="rounded-full border border-[#f5d7a0]/50 px-2 py-[2px] text-[9px] tracking-widest">
                            OPEN TO ALL
                        </span>
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


            {isHelpOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
                    <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#101010] text-white shadow-2xl">
                        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
                            <h2 className="text-sm uppercase tracking-widest text-white/80">
                                Last.fm Setup
                            </h2>
                            <button
                                onClick={() => setIsHelpOpen(false)}
                                className="text-xs uppercase tracking-widest text-white/70 hover:text-white transition-colors"
                            >
                                Close
                            </button>
                        </div>
                            <div className="px-6 py-5 text-left text-[15px] leading-relaxed text-white/90">
                            <p className="mb-4 text-sm uppercase tracking-widest text-white/70">
                                Quick setup
                            </p>

                            <ol className="space-y-3">
                                <li className="flex gap-3">
                                <span className="mt-[2px] inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/20 text-[10px] text-white/80">
                                    1
                                </span>
                                <span>Create a Last.fm account if you don’t have one.</span>
                                </li>

                                <li className="flex gap-3">
                                <span className="mt-[2px] inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/20 text-[10px] text-white/80">
                                    2
                                </span>
                                <span>
                                    Connect your platform in
                                    <a
                                    href="https://www.last.fm/about/trackmymusic"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="ml-1 underline decoration-white/40 underline-offset-4 hover:text-white"
                                    >
                                    Track My Music
                                    </a>.
                                </span>
                                </li>

                                <li className="flex gap-3">
                                <span className="mt-[2px] inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/20 text-[10px] text-white/80">
                                    3
                                </span>
                                <span>Authorize Last.fm so it can scrobble your plays.</span>
                                </li>

                                <li className="flex gap-3">
                                <span className="mt-[2px] inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/20 text-[10px] text-white/80">
                                    4
                                </span>
                                <span>Listen to a few songs.</span>
                                </li>

                                <li className="flex gap-3">
                                <span className="mt-[2px] inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/20 text-[10px] text-white/80">
                                    5
                                </span>
                                <span>Your Recents page updates instantly.</span>
                                </li>

                                <li className="flex gap-3">
                                <span className="mt-[2px] inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/20 text-[10px] text-white/80">
                                    6
                                </span>
                                <span>The Completions page updates about every 20 minutes.</span>
                                </li>
                            </ol>

                            <p className="mt-4 text-xs text-white/60">
                                P.S. Backfilling existing Last.fm history is coming soon.
                            </p>
                            </div>

                    </div>
                </div>
            )}



        </div>
    );
}
