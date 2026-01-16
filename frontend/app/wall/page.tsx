"use client"

import { useState, useEffect } from 'react';
import Image from 'next/image';

type Album = {
    album_id: string;
    album_name: string;
    artist: string;
    listened: number;
    total: number;
    percentage: number;
    album_image?: string | null;
    album_image_height?: number | null;
    album_image_width?: number | null;
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
            />
        </div>
    )
}


export default function WallPage() {
    const [albums, setAlbums] = useState<Album[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchTracking() {
            try {
                const res = await fetch("http://127.0.0.1:3000/tracking", {
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
                    throw new Error('Failed to fetch tracking data');
                }

                const data = await res.json();
                // Sort by percentage (descending - highest completion first)
                const sorted = data.sort((a: Album, b: Album) => b.percentage - a.percentage);
                setAlbums(sorted);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'An error occurred');
            } finally {
                setLoading(false);
            }
        }

        fetchTracking();
    }, []);

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
                    Album Completion Wall
                </h1>
                
                {albums.length === 0 ? (
                    <div className="text-center text-white/70 text-lg">
                        No albums tracked yet. Start listening to see your progress!
                    </div>
                ) : (
                    <div className="grid grid-cols-3 gap-6">
                        {albums.map((album) => (
                            <div
                                key={album.album_id}
                                className="bg-white/10 backdrop-blur-lg rounded-xl shadow-xl p-6 hover:bg-white/20 transition-all duration-200"
                            >
                                <div className="flex flex-col items-center">
                                    {/* Album Image - Fixed size for all albums */}
                                    <div className="w-[300px] h-[300px] rounded-lg mb-4 overflow-hidden bg-gray-700 flex items-center justify-center">
                                        {album.album_image ? (
                                            <AlbumCover url={album.album_image} />
                                        ) : (
                                            <div className="text-center">
                                                <div className="text-white/30 text-6xl mb-2">🎵</div>
                                                <span className="text-white/40 text-sm">{album.album_image}</span>
                                            </div>
                                        )}
                                    </div>
                                    
                                    <h2 className="text-xl font-bold text-white mb-2 text-center">
                                        {album.album_name}
                                    </h2>
                                    
                                    <p className="text-white/70 mb-4 text-center">
                                        {album.artist}
                                    </p>
                                    
                                    <div className="w-full">
                                        <div className="flex justify-between text-sm text-white/80 mb-2">
                                            <span>{album.listened} / {album.total} tracks</span>
                                            <span>{Math.round(album.percentage * 100)}%</span>
                                        </div>
                                        
                                        <div className="w-full bg-gray-700 rounded-full h-3 overflow-hidden">
                                            <div
                                                className="bg-[#1DB954] h-full rounded-full transition-all duration-300"
                                                style={{ width: `${album.percentage * 100}%` }}
                                            />
                                        </div>
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