"use client"

import { useEffect } from 'react';
import Image from 'next/image';
import useSWR from 'swr';
import { API_BASE } from '../lib/api';
import { authedFetcher, type FetcherError } from '../lib/swr';

type Recent = {
    track_name: string;
    artists: string[],
    album_name: string,
    album_type: string,
    album_id: string,
    album_image: string,
    album_image_height: number | null,
    album_image_width: number | null,
    played_at: string
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

function formatPlayedAt(playedAt: string): string {
    const date = new Date(playedAt);
    if (Number.isNaN(date.getTime())) {
        return playedAt;
    }
    return date.toLocaleString();
}

export default function RecentlyListenedPage() {
    const { data, error, isLoading } = useSWR<Recent[], FetcherError>(
        `${API_BASE}/recents`,
        authedFetcher,
        {
            refreshInterval: 120000,
            keepPreviousData: true,
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

    const recents = data ?? [];

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
                <h1 className="font-display text-3xl sm:text-4xl tracking-[0.12em] uppercase text-white mb-6 sm:mb-8 text-center">
                    Recents
                </h1>

                {recents.length === 0 ? (
                    <div className="text-center text-white/70 text-lg">
                        No recent listens yet. Play something to see it here.
                    </div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
                        {recents.map((song) => (
                            <div
                                key={song.track_name + song.played_at}
                                className="bg-white/10 backdrop-blur-lg rounded-xl shadow-xl p-4 sm:p-6 hover:bg-white/20 transition-all duration-200"
                            >
                                <div className="flex flex-col items-center">
                                    <div className="w-[140px] h-[140px] sm:w-[180px] sm:h-[180px] lg:w-[200px] lg:h-[200px] rounded-lg mb-4 overflow-hidden bg-gray-700 flex items-center justify-center">
                                        {song.album_image ? (
                                            <AlbumCover url={song.album_image} />
                                        ) : (
                                            <div className="text-center">
                                                <div className="text-white/30 text-2xl mb-2">No cover</div>
                                                <span className="text-white/40 text-sm">Missing artwork</span>
                                            </div>
                                        )}
                                    </div>

                                    <h2 className="font-display text-xl sm:text-2xl font-bold text-white mb-2 text-center">
                                        {song.track_name}
                                    </h2>

                                    <p className="text-white/70 text-sm sm:text-base mb-2 text-center">
                                        {song.artists.join(', ')}
                                    </p>

                                    <p className="text-white/60 text-sm sm:text-base mb-4 text-center">
                                        {song.album_name}
                                    </p>

                                    <div className="text-white/70 text-xs sm:text-sm text-center">
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
