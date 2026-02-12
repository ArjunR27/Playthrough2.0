"use client"

import { useEffect } from 'react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { API_BASE } from '../lib/api';
import { authedFetcher, type FetcherError } from '../lib/swr';

type ProfileData = {
    provider: "spotify" | "lastfm";
    id: string;
    display_name: string | null;
    email?: string | null;
    images: Array<{ url: string; height: number | null; width: number | null }>;
    followers?: number;
    external_urls?: { spotify?: string; lastfm?: string };
    country?: string | null;
    product?: string | null;
    playcount?: number | string | null;
    registered_at?: string | null;
}

export default function ProfilePage() {
    const router = useRouter();

    const { data, error, isLoading } = useSWR<ProfileData, FetcherError>(
        `${API_BASE}/profile`,
        authedFetcher,
        {
            refreshInterval: 0,
            revalidateOnFocus: false,
            revalidateIfStale: false,
        }
    );

    useEffect(() => {
        if (error?.status === 401) {
            const loginUrl =
                (error.info as { login_url?: string } | undefined)?.login_url ?? `${API_BASE}/`;
            window.location.href = loginUrl;
        }
    }, [error]);

    const profile = data ?? null;

    const handleSignOut = async () => {
        try {
            const res = await fetch(`${API_BASE}/logout`, {
                method: "POST",
                credentials: "include",
            });

            // Dispatch event to notify navbar of logout
            window.dispatchEvent(new Event('auth-change'));

            if (res.ok) {
                // Redirect to home page after successful logout
                router.push('/');
            } else {
                // Even if logout fails, redirect to home
                router.push('/');
            }
        } catch (err) {
            // Dispatch event even on error
            window.dispatchEvent(new Event('auth-change'));
            // On error, still redirect to home
            router.push('/');
        }
    };

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#191414] to-[#1DB954]">
                <div className="text-white text-xl">Loading...</div>
            </div>
        );
    }

    if (error && error.status !== 401) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#191414] to-[#1DB954]">
                <div className="text-red-300">Error: {error.message || 'Failed to load data'}</div>
            </div>
        );
    }

    if (!profile) {
        return null;
    }

    const profileImage = profile.images && profile.images.length > 0 ? profile.images[0].url : null;
    const isSpotify = profile.provider === "spotify";

    return (
        <div className="min-h-screen p-4 sm:p-6 lg:p-8 bg-gradient-to-br from-[#191414] to-[#1DB954]">
            <div className="max-w-4xl mx-auto">
                <h1 className="font-display text-3xl sm:text-4xl tracking-[0.12em] uppercase text-white mb-6 sm:mb-8 text-center">
                    Profile
                </h1>
                
                <div className="bg-black/30 backdrop-blur-lg rounded-2xl border border-white/10 shadow-[0_18px_50px_rgba(0,0,0,0.45)] p-6 sm:p-8">
                    <div className="flex flex-col md:flex-row items-center md:items-start gap-8">
                        {/* Profile Image */}
                        <div className="flex-shrink-0">
                            {profileImage ? (
                                <div className="w-32 h-32 sm:w-40 sm:h-40 md:w-48 md:h-48 rounded-full overflow-hidden border-4 border-white/20">
                                    <Image
                                        src={profileImage}
                                        alt="Profile"
                                        width={192}
                                        height={192}
                                        className="object-cover w-full h-full"
                                    />
                                </div>
                            ) : (
                                <div className="w-32 h-32 sm:w-40 sm:h-40 md:w-48 md:h-48 rounded-full bg-black/40 flex items-center justify-center border-4 border-white/20">
                                    <span className="text-white/50 text-6xl">👤</span>
                                </div>
                            )}
                        </div>

                        {/* Profile Information */}
                        <div className="flex-1 text-center md:text-left">
                            <h2 className="font-display text-2xl sm:text-3xl font-bold text-white mb-2">
                                {profile.display_name || 'No name'}
                            </h2>
                            
                                {isSpotify && profile.email && (
                                    <p className="text-white/70 mb-4">{profile.email}</p>
                                )}

                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6">
                                <div className="bg-black/30 rounded-lg p-4">
                                    <p className="text-white/60 text-sm mb-1">User ID</p>
                                    <p className="text-white font-semibold">{profile.id}</p>
                                </div>

                                {isSpotify && profile.followers !== undefined && (
                                    <div className="bg-black/30 rounded-lg p-4">
                                        <p className="text-white/60 text-sm mb-1">Followers</p>
                                        <p className="text-white font-semibold">{profile.followers.toLocaleString()}</p>
                                    </div>
                                )}

                                {!isSpotify && profile.playcount !== undefined && (
                                    <div className="bg-black/30 rounded-lg p-4">
                                        <p className="text-white/60 text-sm mb-1">Playcount</p>
                                        <p className="text-white font-semibold">{profile.playcount}</p>
                                    </div>
                                )}

                                {profile.country && (
                                    <div className="bg-black/30 rounded-lg p-4">
                                        <p className="text-white/60 text-sm mb-1">Country</p>
                                        <p className="text-white font-semibold">{profile.country}</p>
                                    </div>
                                )}

                                {isSpotify && profile.product && (
                                    <div className="bg-black/30 rounded-lg p-4">
                                        <p className="text-white/60 text-sm mb-1">Subscription</p>
                                        <p className="text-white font-semibold capitalize">{profile.product}</p>
                                    </div>
                                )}
                            </div>

                            <div className="mt-6 flex flex-col sm:flex-row gap-4 justify-center md:justify-start">
                                {profile.external_urls?.spotify && (
                                    <a
                                        href={profile.external_urls.spotify}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center justify-center text-[11px] sm:text-xs uppercase tracking-widest px-5 py-2.5 sm:px-6 sm:py-3 rounded-full border border-[#1DB954]/60 text-[#1DB954] hover:border-[#1DB954] hover:text-[#1ed760] transition-colors text-center"
                                    >
                                        View on Spotify
                                    </a>
                                )}
                                {profile.external_urls?.lastfm && (
                                    <a
                                        href={profile.external_urls.lastfm}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center justify-center text-[11px] sm:text-xs uppercase tracking-widest px-5 py-2.5 sm:px-6 sm:py-3 rounded-full border border-red-300/40 text-red-200 hover:border-red-200 hover:text-red-100 transition-colors text-center"
                                    >
                                        View on Last.fm
                                    </a>
                                )}
                                <button
                                    onClick={handleSignOut}
                                    className="inline-flex items-center justify-center text-[11px] sm:text-xs uppercase tracking-widest px-5 py-2.5 sm:px-6 sm:py-3 rounded-full border border-red-300/40 text-red-200 hover:border-red-200 hover:text-red-100 transition-colors"
                                >
                                    Sign Out
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
