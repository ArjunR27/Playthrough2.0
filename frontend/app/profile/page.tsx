"use client"

import { useState, useEffect } from 'react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';

type ProfileData = {
    id: string;
    display_name: string | null;
    email: string | null;
    images: Array<{ url: string; height: number | null; width: number | null }>;
    followers: number;
    external_urls: { spotify?: string };
    country: string | null;
    product: string | null;
}

export default function ProfilePage() {
    const [profile, setProfile] = useState<ProfileData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();

    useEffect(() => {
        async function fetchProfile() {
            try {
                const res = await fetch("http://127.0.0.1:3000/profile", {
                    cache: "no-store",
                    credentials: "include",
                });

                if (res.status === 401) {
                    const body = await res.json().catch(() => ({}));
                    const loginUrl = body?.login_url ?? "http://127.0.0.1:3000/";
                    window.location.href = loginUrl;
                    return;
                }

                if (!res.ok) {
                    throw new Error('Failed to fetch profile data');
                }

                const data = await res.json();
                setProfile(data);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'An error occurred');
            } finally {
                setLoading(false);
            }
        }

        fetchProfile();
    }, []);

    const handleSignOut = async () => {
        try {
            const res = await fetch("http://127.0.0.1:3000/logout", {
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

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#191414] to-[#1DB954]">
                <div className="text-white text-xl">Loading...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#191414] to-[#1DB954]">
                <div className="text-red-500">Error: {error}</div>
            </div>
        );
    }

    if (!profile) {
        return null;
    }

    const profileImage = profile.images && profile.images.length > 0 ? profile.images[0].url : null;

    return (
        <div className="min-h-screen p-8 bg-gradient-to-br from-[#191414] to-[#1DB954]">
            <div className="max-w-4xl mx-auto">
                <h1 className="text-4xl font-bold text-white mb-8 text-center">
                    Profile
                </h1>
                
                <div className="bg-white/10 backdrop-blur-lg rounded-xl shadow-xl p-8">
                    <div className="flex flex-col md:flex-row items-center md:items-start gap-8">
                        {/* Profile Image */}
                        <div className="flex-shrink-0">
                            {profileImage ? (
                                <div className="w-48 h-48 rounded-full overflow-hidden border-4 border-white/20">
                                    <Image
                                        src={profileImage}
                                        alt="Profile"
                                        width={192}
                                        height={192}
                                        className="object-cover w-full h-full"
                                    />
                                </div>
                            ) : (
                                <div className="w-48 h-48 rounded-full bg-gray-700 flex items-center justify-center border-4 border-white/20">
                                    <span className="text-white/50 text-6xl">👤</span>
                                </div>
                            )}
                        </div>

                        {/* Profile Information */}
                        <div className="flex-1 text-center md:text-left">
                            <h2 className="text-3xl font-bold text-white mb-2">
                                {profile.display_name || 'No name'}
                            </h2>
                            
                            {profile.email && (
                                <p className="text-white/70 mb-4">{profile.email}</p>
                            )}

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
                                <div className="bg-white/5 rounded-lg p-4">
                                    <p className="text-white/60 text-sm mb-1">User ID</p>
                                    <p className="text-white font-semibold">{profile.id}</p>
                                </div>

                                <div className="bg-white/5 rounded-lg p-4">
                                    <p className="text-white/60 text-sm mb-1">Followers</p>
                                    <p className="text-white font-semibold">{profile.followers.toLocaleString()}</p>
                                </div>

                                {profile.country && (
                                    <div className="bg-white/5 rounded-lg p-4">
                                        <p className="text-white/60 text-sm mb-1">Country</p>
                                        <p className="text-white font-semibold">{profile.country}</p>
                                    </div>
                                )}

                                {profile.product && (
                                    <div className="bg-white/5 rounded-lg p-4">
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
                                        className="inline-block bg-[#1DB954] text-white font-semibold px-6 py-3 rounded-full hover:bg-[#1ed760] transition-all duration-200 text-center"
                                    >
                                        View on Spotify
                                    </a>
                                )}
                                <button
                                    onClick={handleSignOut}
                                    className="inline-block bg-red-600 text-white font-semibold px-6 py-3 rounded-full hover:bg-red-700 transition-all duration-200"
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
