"use client"

import { useState, useEffect } from 'react';
import Image from 'next/image';

type Recent = {
    track_name: string;
    artists: string[],
    album_name: string,
    album_type: string,
    album_id: string,
    album_image: string,
    album_image_height: number, 
    album_image_width: number,
    played_at: string
}

type URLProp = {
    url: string
}

function AlbumCover({ url }: URLProp): React.ReactElement {
    return (
        <div>
            <Image
                src={ url }
                alt="Album Cover"
                width={200}
                height={200}
                className="object-cover"
            />
        </div>
    )
}

function formatPlayedAt(playedAt: string): string {
    const date = new Date(playedAt);
    if (Number.isNaN(date.getTime())) {
        return playedAt;
    }
    return date.toLocaleString();
}

export default function RecentlyListenedPage() {
    const [recents, setRecents] = useState<Recent[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null); 

    useEffect(() => {
        async function fetchRecents() {
            try {
                const res = await fetch("http://127.0.0.1:3000/recents", {
                    cache: "no-store",
                    credentials: "include", 
                }); 

                if (res.status === 401) {
                    const body = await res.json().catch(() => ({}));
                    const loginUrl = body?.login_url ?? "http://127.0.0.1:3000/";
                    // changes the current url to the login url because the user is not correctly authenticated with spotify
                    window.location.href = loginUrl;
                    return
                }

                if (!res.ok) {
                    throw new Error('Failed to fetch recents')
                }

                const data = await res.json();
                setRecents(data)
            } catch (err) {
                setError(err instanceof Error ? err.message : 'An error occured'); 
            } finally {
                setLoading(false); 
            }
        }

        fetchRecents(); 

    }, [])

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

    return (
        <div className="min-h-screen p-8 bg-gradient-to-br from-[#191414] to-[#1DB954]">
            <div className="max-w-7xl mx-auto">
                <h1 className="text-4xl font-bold text-white mb-8 text-center">
                    Recently Listened Songs
                </h1>

                {recents.length === 0 ? (
                    <div className="text-center text-white/70 text-lg">
                        No recent listens yet. Play something to see it here.
                    </div>
                ) : (
                    <div className="grid grid-cols-3 gap-6">
                        {recents.map((song) => (
                            <div
                                key={song.track_name + song.played_at}
                                className="bg-white/10 backdrop-blur-lg rounded-xl shadow-xl p-6 hover:bg-white/20 transition-all duration-200"
                            >
                                <div className="flex flex-col items-center">
                                    <div className="w-[200px] h-[200px] rounded-lg mb-4 overflow-hidden bg-gray-700 flex items-center justify-center">
                                        {song.album_image ? (
                                            <AlbumCover url={song.album_image} />
                                        ) : (
                                            <div className="text-center">
                                                <div className="text-white/30 text-2xl mb-2">No cover</div>
                                                <span className="text-white/40 text-sm">Missing artwork</span>
                                            </div>
                                        )}
                                    </div>

                                    <h2 className="text-xl font-bold text-white mb-2 text-center">
                                        {song.track_name}
                                    </h2>

                                    <p className="text-white/70 mb-2 text-center">
                                        {song.artists.join(', ')}
                                    </p>

                                    <p className="text-white/60 mb-4 text-center">
                                        {song.album_name}
                                    </p>

                                    <div className="text-white/70 text-sm text-center">
                                        Played {formatPlayedAt(song.played_at)}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    ); 
}
