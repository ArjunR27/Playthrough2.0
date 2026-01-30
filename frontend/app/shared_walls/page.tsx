"use client"

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import Image from "next/image";
import Link from "next/link";
import { Bebas_Neue, Sora } from "next/font/google";
import { API_BASE } from "../lib/api";

const displayFont = Bebas_Neue({
    subsets: ["latin"],
    weight: ["400"],
});

const bodyFont = Sora({
    subsets: ["latin"],
    weight: ["300", "400", "600"],
});

type SharedWallItem = {
    album_id: string;
    album_name?: string | null;
    artist_name?: string | null;
    album_image?: string | null;
};

type SharedWall = {
    wall: {
        wall_id: string;
        owner_id: string;
        owner_display_name?: string | null;
        title?: string | null;
        created_at?: string | null;
        is_owner?: boolean;
    };
    items: SharedWallItem[];
};

const wallTheme = {
    "--wall-wood-1": "#2f1d12",
    "--wall-wood-2": "#25160d",
    "--wall-wood-edge": "#4a2f1c",
    "--wall-gold": "#f5d7a0",
    "--wall-cream": "#f4e6cf",
} as CSSProperties;

export default function SharedWallsPage() {
    const [walls, setWalls] = useState<SharedWall[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const redirectToLogin = async (res: Response) => {
        const body = await res.json().catch(() => ({}));
        const loginUrl = body?.login_url ?? `${API_BASE}/`;
        window.location.href = loginUrl;
    };

    useEffect(() => {
        async function fetchSharedWalls() {
            let didRedirect = false;
            try {
                const res = await fetch(`${API_BASE}/api/walls?all=true`, {
                    cache: "no-store",
                    credentials: "include",
                });

                if (res.status === 401) {
                    await redirectToLogin(res);
                    didRedirect = true;
                    return;
                }

                if (!res.ok) {
                    throw new Error("Failed to fetch shared walls");
                }

                const data = await res.json();
                const nextWalls = Array.isArray(data?.walls) ? data.walls : [];
                setWalls(nextWalls);
            } catch (err) {
                setError(err instanceof Error ? err.message : "An error occurred");
            } finally {
                if (didRedirect) {
                    return;
                }
                setLoading(false);
            }
        }

        fetchSharedWalls();
    }, []);

    const visibleWalls = useMemo(() => {
        return walls
            .filter((entry) => !entry?.wall?.is_owner)
            .sort((a, b) => {
                const nameA = a?.wall?.owner_display_name || a?.wall?.owner_id || "";
                const nameB = b?.wall?.owner_display_name || b?.wall?.owner_id || "";
                return nameA.localeCompare(nameB);
            });
    }, [walls]);

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#0c0906] via-[#1f140d] to-[#0f0b08]">
                <div className={`${bodyFont.className} text-white text-xl`}>Loading...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#0c0906] via-[#1f140d] to-[#0f0b08]">
                <div className={`${bodyFont.className} text-red-300 text-lg`}>Error: {error}</div>
            </div>
        );
    }

    return (
        <div
            className={`min-h-screen bg-gradient-to-br from-[#0c0906] via-[#1c120b] to-[#0f0b08] ${bodyFont.className}`}
            style={wallTheme}
        >
            <div className="max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
                <div className="flex flex-col sm:flex-row sm:items-end gap-4 mb-6">
                    <div>
                        <div className={`${displayFont.className} text-3xl sm:text-4xl tracking-[0.25em] text-white`}>
                            Shared Walls
                        </div>
                        <div className="text-xs text-white/50 uppercase tracking-[0.25em]">
                            View-only wall gallery
                        </div>
                    </div>
                    <div className="sm:ml-auto flex items-center gap-3">
                        <Link
                            href="/wall"
                            className="text-[11px] uppercase tracking-widest px-4 py-2 rounded-full border border-white/20 text-white/70 hover:border-white/40 hover:text-white transition-colors"
                        >
                            My Wall
                        </Link>
                    </div>
                </div>

                {visibleWalls.length === 0 ? (
                    <div className="text-white/70 text-sm bg-black/30 rounded-2xl px-6 py-4">
                        No shared walls yet.
                    </div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {visibleWalls.map((entry) => {
                            const wall = entry.wall;
                            const items = entry.items ?? [];
                            const displayName = wall.owner_display_name || wall.owner_id;
                            return (
                                <div
                                    key={wall.wall_id}
                                    className="rounded-2xl border border-white/10 bg-black/30 p-4 shadow-[0_12px_40px_rgba(0,0,0,0.45)]"
                                >
                                    <div className="flex items-start justify-between gap-3 mb-3">
                                        <div className="min-w-0">
                                            <div className={`${displayFont.className} text-base tracking-[0.2em] text-white truncate`}>
                                                {displayName}
                                            </div>
                                            {wall.title ? (
                                                <div className="text-xs text-white/60 truncate">{wall.title}</div>
                                            ) : null}
                                        </div>
                                        <div className="text-[10px] text-white/50 uppercase tracking-[0.2em]">
                                            {items.length} albums
                                        </div>
                                    </div>

                                    {items.length === 0 ? (
                                        <div className="text-white/40 text-xs bg-black/20 rounded-xl px-3 py-2">
                                            Empty wall
                                        </div>
                                    ) : (
                                        <>
                                            <div className="grid grid-cols-4 gap-2">
                                                {items.slice(0, 16).map((item) => (
                                                    <div
                                                        key={`${wall.wall_id}-${item.album_id}`}
                                                        className="relative w-14 h-14 rounded-full bg-gradient-to-br from-[#111] via-[#1a1a1a] to-[#050505] border border-white/10 overflow-hidden"
                                                    >
                                                        {item.album_image ? (
                                                            <Image
                                                                src={item.album_image}
                                                                alt={item.album_name || "album"}
                                                                fill
                                                                sizes="56px"
                                                                className="object-cover"
                                                            />
                                                        ) : (
                                                            <div className="w-full h-full flex items-center justify-center text-white/30 text-xs">
                                                                note
                                                            </div>
                                                        )}
                                                        <div
                                                            className="absolute left-1/2 top-1/2 w-1.5 h-1.5 rounded-full -translate-x-1/2 -translate-y-1/2"
                                                            style={{ backgroundColor: "var(--wall-gold)" }}
                                                        />
                                                    </div>
                                                ))}
                                            </div>
                                            {items.length > 16 ? (
                                                <div className="mt-3 text-[11px] text-white/50 uppercase tracking-[0.2em]">
                                                    +{items.length - 16} more
                                                </div>
                                            ) : null}
                                        </>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}
