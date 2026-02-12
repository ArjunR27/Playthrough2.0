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
    track_id?: string;
    track_name: string;
    track_number: number;
    is_listened: boolean;
}

type URLProp = {
    url: string
}

function AlbumCover({ url }: URLProp): React.ReactElement {
    return (
        <div className="w-full h-full">
            <Image
                src={ url }
                alt="Album Cover"
                width={200}
                height={200}
                className="object-cover w-full h-full"
            />
        </div>
    )
}


export default function WallPage() {
    const [selectedAlbum, setSelectedAlbum] = useState<Album | null>(null);
    const [tracks, setTracks] = useState<Track[]>([]);
    const [isTracksLoading, setIsTracksLoading] = useState(false);
    const [tracksError, setTracksError] = useState<string | null>(null);
    const [showUnfinished, setShowUnfinished] = useState(false);
    const [albumSearch, setAlbumSearch] = useState("");

    const trackingUrl = useMemo(() => {
        return showUnfinished
            ? `${API_BASE}/tracking?filter=unfinished`
            : `${API_BASE}/tracking`;
    }, [showUnfinished]);

    const { data, error, isLoading } = useSWR<Album[], FetcherError>(
        trackingUrl,
        authedFetcher,
        {
            refreshInterval: 120000,
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

    const filteredAlbums = useMemo(() => {
        const query = albumSearch.trim().toLowerCase();
        if (!query) {
            return albums;
        }
        return albums.filter((album) => {
            const name = album.album_name.toLowerCase();
            const artist = album.artist.toLowerCase();
            return name.includes(query) || artist.includes(query);
        });
    }, [albums, albumSearch]);

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
                <div className="text-red-300">Error: {error.message || 'Failed to load data'}</div>
            </div>
        );
    }

    return (
        <div className="min-h-screen p-4 sm:p-6 lg:p-8 bg-gradient-to-br from-[#191414] to-[#1DB954]">
            <div className="max-w-7xl mx-auto">
                <div className="flex flex-col items-center gap-3 mb-6 sm:mb-8">
                    <h1 className="font-display text-3xl sm:text-4xl tracking-[0.12em] uppercase text-white text-center">
                        Completions
                    </h1>
                    <button
                        type="button"
                        onClick={() => setShowUnfinished((prev) => !prev)}
                        aria-pressed={showUnfinished}
                        className={`inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-[11px] sm:text-xs uppercase tracking-widest transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[#17110E] ${
                            showUnfinished
                                ? "bg-white text-[#191414] shadow-lg"
                                : "bg-[#1DB954] text-[#0b1b12] shadow-lg shadow-black/30 hover:bg-[#2bd66a] hover:shadow-xl"
                        }`}
                    >
                        <span className="text-base">⏳</span>
                        Find Unfinished Albums
                    </button>
                    <div className="w-full max-w-xl">
                        <label htmlFor="completion-search" className="sr-only">
                            Search albums or artists
                        </label>
                        <input
                            id="completion-search"
                            type="search"
                            value={albumSearch}
                            onChange={(event) => setAlbumSearch(event.target.value)}
                            placeholder="Search albums or artists"
                            className="w-full rounded-full border border-white/20 bg-black/20 px-4 py-2 text-sm sm:text-base text-white placeholder:text-white/40 focus:outline-none focus:border-white/40"
                        />
                    </div>
                </div>
                
                {albums.length === 0 ? (
                    <div className="text-center text-white/70 text-lg">
                        No albums tracked yet. Start listening to see your progress!
                    </div>
                ) : filteredAlbums.length === 0 ? (
                    <div className="text-center text-white/70 text-lg">
                        No matches for "{albumSearch.trim()}".
                    </div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
                        {filteredAlbums.map((album) => (
                            <div
                                key={album.album_id}
                                onClick={() => handleAlbumClick(album)}
                                className="bg-white/10 backdrop-blur-lg rounded-xl shadow-xl p-4 sm:p-6 hover:bg-white/20 transition-all duration-200 cursor-pointer"
                            >
                                <div className="flex flex-col items-center">
                                    {/* Album Image - Fixed size for all albums */}
                                    <div className="w-[140px] h-[140px] sm:w-[180px] sm:h-[180px] lg:w-[200px] lg:h-[200px] rounded-lg mb-4 overflow-hidden bg-gray-700 flex items-center justify-center">
                                        {album.album_image ? (
                                            <AlbumCover url={album.album_image} />
                                        ) : (
                                            <div className="text-center">
                                                <div className="text-white/30 text-6xl mb-2">🎵</div>
                                                <span className="text-white/40 text-sm">{album.album_image}</span>
                                            </div>
                                        )}
                                    </div>
                                    
                                    <h2 className="font-display text-xl sm:text-2xl font-bold text-white mb-2 text-center">
                                        {album.album_name}
                                    </h2>
                                    
                                    <p className="text-white/70 text-sm sm:text-base mb-4 text-center">
                                        {album.artist}
                                    </p>
                                    
                                    <div className="w-full">
                                        <div className="flex justify-between text-xs sm:text-sm text-white/80 mb-2">
                                            <span>{album.listened} / {album.total} tracks</span>
                                            <span>{Math.round(album.percentage * 100)}%</span>
                                        </div>
                                        
                                        <div className="w-full bg-gray-700 rounded-full h-2.5 sm:h-3 overflow-hidden">
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
                        className="bg-gradient-to-br from-[#191414] to-[#1DB954] rounded-2xl shadow-2xl max-w-[95vw] sm:max-w-2xl w-full max-h-[85vh] overflow-hidden flex flex-col"
                        onClick={(e) => e.stopPropagation()}
                    >
                        {/* Modal Header */}
                        <div className="relative p-4 sm:p-6 border-b border-white/20">
                            <button
                                onClick={closeModal}
                                className="absolute top-3 right-3 sm:top-4 sm:right-4 text-white/70 hover:text-white transition-colors text-2xl font-bold w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10"
                            >
                                ×
                            </button>
                            
                            <div className="flex flex-col sm:flex-row items-start gap-4 sm:gap-6 pr-8 sm:pr-10">
                                {/* Album Image */}
                                <div className="w-24 h-24 sm:w-32 sm:h-32 rounded-lg overflow-hidden bg-black/40 flex-shrink-0">
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
                                    <h2 className="font-display text-xl sm:text-2xl font-bold text-white mb-2">
                                        {selectedAlbum.album_name}
                                    </h2>
                                    <p className="text-white/70 text-sm sm:text-base mb-3">
                                        {selectedAlbum.artist}
                                    </p>
                                    <div className="text-xs sm:text-sm text-white/80">
                                        <span>{selectedAlbum.listened} / {selectedAlbum.total} tracks listened</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Tracks List */}
                        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
                            {tracksError ? (
                                <div className="text-center text-red-300 py-8">
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
                                            key={track.track_id ?? `${selectedAlbum?.album_id ?? 'album'}-${track.track_number}`}
                                            className={`flex items-center gap-3 sm:gap-4 p-3 rounded-lg transition-colors ${
                                                track.is_listened
                                                    ? 'bg-[#1DB954]/20 hover:bg-[#1DB954]/30'
                                                    : 'bg-white/5 hover:bg-white/10'
                                            }`}
                                        >
                                            <div className="w-6 sm:w-8 text-center text-white/60 text-xs sm:text-sm">
                                                {track.track_number}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className={`text-sm sm:text-base text-white ${
                                                    track.is_listened ? 'font-medium' : 'text-white/80'
                                                }`}>
                                                    {track.track_name}
                                                </div>
                                            </div>
                                            {track.is_listened && (
                                                <div className="text-[#f4e6cf] text-xl flex-shrink-0">
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
