"use client"

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import Image from "next/image";
import Link from "next/link";
import { API_BASE } from "../lib/api";
import {
    loadSharedWallsCache,
    primeSharedWallDetails,
    saveSharedWallDetail,
    saveSharedWallsCache,
    type SharedWall,
} from "./cache";

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
    const [cacheNotice, setCacheNotice] = useState<string | null>(null);
    const hadCacheRef = useRef(false);

    const redirectToLogin = async (res: Response) => {
        const body = await res.json().catch(() => ({}));
        const loginUrl = body?.login_url ?? `${API_BASE}/`;
        window.location.href = loginUrl;
    };

    useEffect(() => {
        const cached = loadSharedWallsCache();
        if (cached?.walls?.length) {
            hadCacheRef.current = true;
            setWalls(cached.walls);
            setLoading(false);
            setCacheNotice(cached.isFresh ? null : "Refreshing cached walls...");
            primeSharedWallDetails(cached.walls, cached.updatedAt);
        } else {
            setLoading(true);
        }
    }, []);

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
                saveSharedWallsCache(nextWalls);
                setCacheNotice(null);
            } catch (err) {
                if (!hadCacheRef.current) {
                    setError(err instanceof Error ? err.message : "An error occurred");
                } else {
                    setCacheNotice("Unable to refresh. Showing cached walls.");
                }
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
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-[#1D1411] to-[#0F0B09]">
                <div className="font-body text-white text-xl">Loading...</div>
            </div>
        );
    }

    if (error && walls.length === 0) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-[#1D1411] to-[#0F0B09]">
                <div className="font-body text-red-300 text-lg">Error: {error}</div>
            </div>
        );
    }

    return (
        <div
            className="min-h-screen bg-gradient-to-b from-[#1D1411] to-[#0F0B09] font-body"
            style={wallTheme}
        >
            <div className="max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
                <div className="flex flex-col sm:flex-row sm:items-end gap-4 mb-6">
                    <div>
                        <div className="font-display text-3xl sm:text-4xl tracking-[0.12em] text-white">
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

                {cacheNotice ? (
                    <div className="mb-4 text-[11px] uppercase tracking-[0.2em] text-white/50">
                        {cacheNotice}
                    </div>
                ) : null}

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
                                <Link
                                    key={wall.wall_id}
                                    href={`/shared_walls/${wall.wall_id}`}
                                    onClick={() => saveSharedWallDetail(entry)}
                                    className="group block rounded-2xl border border-white/10 bg-black/30 p-3 shadow-[0_12px_40px_rgba(0,0,0,0.45)] hover:border-white/30 hover:bg-black/40 transition-colors min-h-[240px] flex flex-col"
                                >
                                    <div className="flex items-start justify-between gap-3 mb-3">
                                        <div className="min-w-0">
                                            <div className="font-display text-base tracking-[0.2em] text-white truncate">
                                                {displayName}
                                            </div>
                                            <div className="text-xs text-white/60 truncate h-4">
                                                {wall.title ?? ""}
                                            </div>
                                        </div>
                                        <div className="text-[10px] text-white/50 uppercase tracking-[0.2em]">
                                            {items.length} albums
                                        </div>
                                    </div>

                                    <div className="flex-1">
                                        {items.length === 0 ? (
                                            <div className="text-white/40 text-xs bg-black/20 rounded-xl px-3 py-2">
                                                Empty wall
                                            </div>
                                        ) : (
                                            <>
                                                <div className="grid grid-cols-4 gap-2">
                                                    {items.slice(0, 8).map((item) => (
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
                                                <div className="mt-3 text-[11px] text-white/50 uppercase tracking-[0.2em] h-4">
                                                    {items.length > 8 ? `+${items.length - 8} more` : ""}
                                                </div>
                                            </>
                                        )}
                                    </div>

                                    <div className="mt-auto pt0 text-[10px] uppercase tracking-[0.3em] text-white/40 group-hover:text-white/70 transition-colors">
                                        View Wall
                                    </div>
                                </Link>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}
