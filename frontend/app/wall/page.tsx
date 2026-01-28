"use client"

import { useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import useSWR from 'swr';
import { API_BASE } from '../lib/api';
import { authedFetcher, type FetcherError } from '../lib/swr';

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

type Track = {
    track_id: string;
    track_name: string;
    track_number: number;
    is_listened: boolean;
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


export default function WallPage() {
    const [selectedAlbum, setSelectedAlbum] = useState<Album | null>(null);
    const [tracks, setTracks] = useState<Track[]>([]);
    const [isTracksLoading, setIsTracksLoading] = useState(false);
    const [tracksError, setTracksError] = useState<string | null>(null);

    const { data, error, isLoading } = useSWR<Album[], FetcherError>(
        `${API_BASE}/tracking`,
        authedFetcher,
        {
            refreshInterval: 1800000,
            revalidateOnFocus: true,
        }
    );

    useEffect(() => {
        if (error?.status === 401) {
            const loginUrl =
                (error.info as { login_url?: string } | undefined)?.login_url ?? `${API_BASE}/`;
            window.location.href = loginUrl;
        }
    }, [error]);

    const albums = useMemo(() => {
        if (!data) {
            return [];
        }
        return [...data].sort((a, b) => b.percentage - a.percentage);
    }, [data]);

    const handleAlbumClick = async (album: Album) => {
        setIsTracksLoading(true);
        setTracksError(null);
        setTracks([]);
        // Don't set selectedAlbum yet - wait until tracks are fetched

        try {
            const res = await fetch(`${API_BASE}/album-tracks?album_id=${album.album_id}`, {
                cache: "no-store",
                credentials: "include",
            });

            if (res.status === 401) {
                const body = await res.json().catch(() => ({}));
                const loginUrl = body?.login_url ?? `${API_BASE}/`;
                window.location.href = loginUrl;
                return;
            }

            if (!res.ok) {
                throw new Error('Failed to fetch album tracks');
            }

            const data = await res.json();
            setTracks(data);
            // Only set selectedAlbum after tracks are successfully fetched
            setSelectedAlbum(album);
        } catch (err) {
            setTracksError(err instanceof Error ? err.message : 'An error occurred');
            // Still show modal even on error so user can see the error message
            setSelectedAlbum(album);
        } finally {
            setIsTracksLoading(false);
        }
    };

    const closeModal = () => {
        setSelectedAlbum(null);
        setTracks([]);
        setTracksError(null);
        setIsTracksLoading(false);
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
                <div className="text-red-500">Error: {error.message || 'Failed to load data'}</div>
            </div>
        );
    }

    return (
        <div className="min-h-screen p-8 bg-gradient-to-br from-[#191414] to-[#1DB954]">
            <div className="max-w-7xl mx-auto">
                <h1 className="font-display text-4xl font-bold text-white mb-8 text-center">
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
                                onClick={() => handleAlbumClick(album)}
                                className="bg-white/10 backdrop-blur-lg rounded-xl shadow-xl p-6 hover:bg-white/20 transition-all duration-200 cursor-pointer"
                            >
                                <div className="flex flex-col items-center">
                                    {/* Album Image - Fixed size for all albums */}
                                    <div className="w-[200px] h-[200px] rounded-lg mb-4 overflow-hidden bg-gray-700 flex items-center justify-center">
                                        {album.album_image ? (
                                            <AlbumCover url={album.album_image} />
                                        ) : (
                                            <div className="text-center">
                                                <div className="text-white/30 text-6xl mb-2">🎵</div>
                                                <span className="text-white/40 text-sm">{album.album_image}</span>
                                            </div>
                                        )}
                                    </div>
                                    
                                    <h2 className="font-display text-xl font-bold text-white mb-2 text-center">
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

            {/* Modal - Only show after tracks are fetched (or error) */}
            {selectedAlbum && !isTracksLoading && (
                <div
                    className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4"
                    onClick={closeModal}
                >
                    <div
                        className="bg-gradient-to-br from-[#191414] to-[#1DB954] rounded-2xl shadow-2xl max-w-2xl w-full max-h-[85vh] overflow-hidden flex flex-col"
                        onClick={(e) => e.stopPropagation()}
                    >
                        {/* Modal Header */}
                        <div className="relative p-6 border-b border-white/20">
                            <button
                                onClick={closeModal}
                                className="absolute top-4 right-4 text-white/70 hover:text-white transition-colors text-2xl font-bold w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10"
                            >
                                ×
                            </button>
                            
                            <div className="flex items-start gap-6 pr-10">
                                {/* Album Image */}
                                <div className="w-32 h-32 rounded-lg overflow-hidden bg-gray-700 flex-shrink-0">
                                    {selectedAlbum.album_image ? (
                                        <Image
                                            src={selectedAlbum.album_image}
                                            alt={selectedAlbum.album_name}
                                            width={128}
                                            height={128}
                                            className="object-cover w-full h-full"
                                        />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center">
                                            <div className="text-white/30 text-4xl">🎵</div>
                                        </div>
                                    )}
                                </div>
                                
                                {/* Album Info */}
                                <div className="flex-1 min-w-0">
                                    <h2 className="font-display text-2xl font-bold text-white mb-2">
                                        {selectedAlbum.album_name}
                                    </h2>
                                    <p className="text-white/70 mb-3">
                                        {selectedAlbum.artist}
                                    </p>
                                    <div className="text-sm text-white/80">
                                        <span>{selectedAlbum.listened} / {selectedAlbum.total} tracks listened</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Tracks List */}
                        <div className="flex-1 overflow-y-auto p-6">
                            {tracksError ? (
                                <div className="text-center text-red-400 py-8">
                                    Error: {tracksError}
                                </div>
                            ) : tracks.length === 0 ? (
                                <div className="text-center text-white/70 py-8">
                                    No tracks found
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    {tracks.map((track) => (
                                        <div
                                            key={track.track_id}
                                            className={`flex items-center gap-4 p-3 rounded-lg transition-colors ${
                                                track.is_listened
                                                    ? 'bg-[#1DB954]/20 hover:bg-[#1DB954]/30'
                                                    : 'bg-white/5 hover:bg-white/10'
                                            }`}
                                        >
                                            <div className="w-8 text-center text-white/60 text-sm">
                                                {track.track_number}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className={`text-white ${
                                                    track.is_listened ? 'font-medium' : 'text-white/80'
                                                }`}>
                                                    {track.track_name}
                                                </div>
                                            </div>
                                            {track.is_listened && (
                                                <div className="text-[#1DB954] text-xl flex-shrink-0">
                                                    ✓
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
            
            {/* Loading overlay - show while fetching tracks */}
            {isTracksLoading && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
                    <div className="text-white text-xl">Loading tracks...</div>
                </div>
            )}
        </div>
    );
}
