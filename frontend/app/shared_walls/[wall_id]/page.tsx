"use client"

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { API_BASE } from "../../lib/api";
import {
    loadSharedWallDetail,
    saveSharedWallDetail,
    type SharedWallItem,
    type SharedWall,
} from "../cache";

const wallTheme = {
    "--wall-wood-1": "#2f1d12",
    "--wall-wood-2": "#25160d",
    "--wall-wood-edge": "#4a2f1c",
    "--wall-gold": "#f5d7a0",
    "--wall-cream": "#f4e6cf",
} as CSSProperties;

export default function SharedWallDetailPage() {
    const params = useParams();
    const wallId = useMemo(() => {
        const raw = params?.wall_id;
        if (Array.isArray(raw)) {
            return raw[0];
        }
        return raw;
    }, [params]);

    const [wall, setWall] = useState<SharedWall["wall"] | null>(null);
    const [items, setItems] = useState<SharedWallItem[]>([]);
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
        const resolvedWallId = wallId;
        if (!resolvedWallId) {
            setLoading(true);
            setError(null);
            return;
        }

        const wallIdValue = resolvedWallId;
        hadCacheRef.current = false;
        setError(null);

        const cached = loadSharedWallDetail(wallIdValue);
        if (cached?.wall) {
            hadCacheRef.current = true;
            setWall(cached.wall);
            setItems(cached.items ?? []);
            setLoading(false);
            setCacheNotice(cached.isFresh ? null : "Refreshing cached wall...");
        } else {
            setWall(null);
            setItems([]);
            setLoading(true);
            setCacheNotice(null);
        }

        async function fetchWall() {
            let didRedirect = false;
            try {
                const res = await fetch(`${API_BASE}/api/walls?wall_id=${encodeURIComponent(wallIdValue)}`, {
                    cache: "no-store",
                    credentials: "include",
                });

                if (res.status === 401) {
                    await redirectToLogin(res);
                    didRedirect = true;
                    return;
                }

                if (!res.ok) {
                    throw new Error("Failed to load wall");
                }

                const data = await res.json().catch(() => ({}));
                const nextWall = data?.wall ?? null;
                const nextItems = Array.isArray(data?.items) ? data.items : [];

                if (!nextWall?.wall_id) {
                    setWall(null);
                    setItems([]);
                    setError("Wall not found.");
                    setCacheNotice(null);
                    return;
                }

                setWall(nextWall);
                setItems(nextItems);
                saveSharedWallDetail({ wall: nextWall, items: nextItems });
                setCacheNotice(null);
            } catch (err) {
                if (!hadCacheRef.current) {
                    setError(err instanceof Error ? err.message : "An error occurred");
                } else {
                    setCacheNotice("Unable to refresh. Showing cached wall.");
                }
            } finally {
                if (didRedirect) {
                    return;
                }
                setLoading(false);
            }
        }

        fetchWall();
    }, [wallId]);

    const displayName = wall?.owner_display_name || wall?.owner_id || "Shared wall";
    const wallTitle = wall?.title || "Album wall";

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-[#1D1411] to-[#0F0B09]">
                <div className="font-body text-white text-xl">Loading...</div>
            </div>
        );
    }

    if (error && items.length === 0) {
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
            <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-5 sm:py-6">
                <div className="flex flex-col sm:flex-row sm:items-center gap-4 mb-5">
                    <div>
                        <div className="font-display text-3xl sm:text-4xl tracking-[0.2em] text-white">
                            {displayName}
                        </div>
                        <div className="text-xs text-white/50 uppercase tracking-[0.25em]">
                            {wallTitle}
                        </div>
                    </div>
                    <div className="sm:ml-auto flex items-center gap-3">
                        <div className="text-[10px] text-white/50 uppercase tracking-[0.2em]">
                            {items.length} albums
                        </div>
                        <Link
                            href="/shared_walls"
                            className="text-[11px] uppercase tracking-widest px-4 py-2 rounded-full border border-white/20 text-white/70 hover:border-white/40 hover:text-white transition-colors"
                        >
                            Back
                        </Link>
                        <Link
                            href="/wall"
                            className="text-[11px] uppercase tracking-widest px-4 py-2 rounded-full border border-white/10 text-white/60 hover:border-white/40 hover:text-white transition-colors"
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

                <div
                    className="relative w-full h-[70vh] sm:h-[80vh] min-h-[360px] sm:min-h-[520px] rounded-[24px] sm:rounded-[36px] border shadow-[0_30px_80px_rgba(0,0,0,0.55)] overflow-y-auto overflow-x-hidden"
                    style={{ borderColor: "var(--wall-wood-edge)" }}
                >
                    <div
                        className="relative w-full min-h-full px-6 py-8"
                        style={{
                            backgroundImage:
                                "linear-gradient(180deg, rgba(255,255,255,0.05), rgba(0,0,0,0.45)), repeating-linear-gradient(90deg, var(--wall-wood-1) 0px, var(--wall-wood-1) 32px, var(--wall-wood-2) 32px, var(--wall-wood-2) 64px)",
                        }}
                    >
                        <div
                            className="absolute inset-0 opacity-60 pointer-events-none"
                            style={{
                                backgroundImage:
                                    "radial-gradient(circle at 15% 25%, rgba(255,255,255,0.08), transparent 35%), radial-gradient(circle at 80% 70%, rgba(0,0,0,0.35), transparent 45%)",
                            }}
                        />

                        {items.length === 0 ? (
                            <div className="absolute inset-0 flex items-center justify-center">
                                <div className="text-white/70 text-sm bg-black/30 rounded-full px-6 py-3">
                                    This wall is empty.
                                </div>
                            </div>
                        ) : (
                            <div
                                className="relative grid gap-10 justify-items-center"
                                style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}
                            >
                                {items.map((item) => {
                                    const albumName = item.album_name || "Unknown album";
                                    const artistName = item.artist_name || "Unknown artist";
                                    return (
                                        <div
                                            key={item.album_id}
                                            className="flex flex-col items-center text-center max-w-[220px]"
                                        >
                                            <div className="relative w-[140px] h-[140px] sm:w-[150px] sm:h-[150px] md:w-[175px] md:h-[175px]">
                                                <div className="absolute inset-0 rounded-full bg-gradient-to-br from-[#111] via-[#1a1a1a] to-[#050505] shadow-[0_10px_25px_rgba(0,0,0,0.55)]" />
                                                <div className="absolute inset-2 rounded-full border border-white/10" />
                                                <div className="absolute inset-5 rounded-full border border-white/5" />
                                                <div className="absolute inset-[26%] rounded-full overflow-hidden border border-white/10 bg-black/50">
                                                    {item.album_image ? (
                                                        <Image
                                                            src={item.album_image}
                                                            alt={albumName}
                                                            fill
                                                            sizes="120px"
                                                            unoptimized
                                                            className="object-cover"
                                                        />
                                                    ) : (
                                                        <div className="w-full h-full flex items-center justify-center text-white/40 text-lg">
                                                            note
                                                        </div>
                                                    )}
                                                </div>
                                                <div
                                                    className="absolute left-1/2 top-1/2 w-2 h-2 rounded-full -translate-x-1/2 -translate-y-1/2 shadow-[0_0_6px_rgba(0,0,0,0.6)]"
                                                    style={{ backgroundColor: "var(--wall-gold)" }}
                                                />
                                            </div>
                                            <div className="mt-2">
                                                <div className="text-[11px] uppercase tracking-[0.2em] text-white/80">
                                                    {albumName}
                                                </div>
                                                <div
                                                    className="text-[10px] uppercase tracking-[0.25em]"
                                                    style={{ color: "var(--wall-gold)" }}
                                                >
                                                    {artistName}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
