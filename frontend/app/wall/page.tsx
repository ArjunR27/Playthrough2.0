"use client"

import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import Image from "next/image";
import Link from "next/link";
import { API_BASE } from "../lib/api";

type Album = {
    album_id: string;
    album_name: string;
    artist: string;
    listened: number;
    total: number;
    percentage: number;
    album_image?: string | null;
};

type WallItem = {
    album_id: string;
    x: number;
    y: number;
};

type DragState = {
    album_id: string;
    offsetX: number;
    offsetY: number;
    width: number;
    height: number;
};

const WALL_PADDING = 24;
const TEXT_BLOCK_HEIGHT = 40;
const WALL_TRACKING_CACHE_KEY = "playthrough.wall.tracking.v1";
const WALL_SAVED_CACHE_KEY = "playthrough.wall.saved.v1";

type TrackingCache = {
    albums: Album[];
    updatedAt: number;
};

type WallCache = {
    wallId: string | null;
    albumIds: string[];
    updatedAt: number;
};

function loadTrackingCache(): Album[] {
    if (typeof window === "undefined") {
        return [];
    }
    try {
        const raw = window.localStorage.getItem(WALL_TRACKING_CACHE_KEY);
        if (!raw) {
            return [];
        }
        const parsed = JSON.parse(raw) as Partial<TrackingCache>;
        if (!Array.isArray(parsed?.albums)) {
            return [];
        }
        return parsed.albums;
    } catch {
        return [];
    }
}

function loadWallCache(): WallCache | null {
    if (typeof window === "undefined") {
        return null;
    }
    try {
        const raw = window.localStorage.getItem(WALL_SAVED_CACHE_KEY);
        if (!raw) {
            return null;
        }
        const parsed = JSON.parse(raw) as Partial<WallCache>;
        if (!Array.isArray(parsed?.albumIds)) {
            return null;
        }
        return {
            wallId: typeof parsed.wallId === "string" ? parsed.wallId : null,
            albumIds: parsed.albumIds,
            updatedAt: typeof parsed.updatedAt === "number" ? parsed.updatedAt : 0,
        };
    } catch {
        return null;
    }
}

function saveTrackingCache(albums: Album[]) {
    if (typeof window === "undefined") {
        return;
    }
    try {
        const payload: TrackingCache = {
            albums,
            updatedAt: Date.now(),
        };
        window.localStorage.setItem(WALL_TRACKING_CACHE_KEY, JSON.stringify(payload));
    } catch {
        // Ignore cache write failures.
    }
}

function saveWallCache(wallId: string | null, albumIds: string[]) {
    if (typeof window === "undefined") {
        return;
    }
    try {
        const payload: WallCache = {
            wallId,
            albumIds,
            updatedAt: Date.now(),
        };
        window.localStorage.setItem(WALL_SAVED_CACHE_KEY, JSON.stringify(payload));
    } catch {
        // Ignore cache write failures.
    }
}

function clamp(value: number, min: number, max: number) {
    return Math.min(Math.max(value, min), max);
}

function getLayoutMetrics() {
    const baseSize = typeof window === "undefined"
        ? 150
        : window.matchMedia("(min-width: 768px)").matches
            ? 175
            : window.matchMedia("(min-width: 640px)").matches
                ? 150
                : 140;

    return {
        cardSize: baseSize,
        rowHeight: baseSize + TEXT_BLOCK_HEIGHT,
        padding: WALL_PADDING,
    };
}

function layoutWallItems(items: WallItem[], wallWidth: number) {
    const { cardSize, rowHeight, padding } = getLayoutMetrics();
    const safeWidth = Math.max(0, wallWidth);
    const columns = Math.max(1, Math.floor((safeWidth - padding) / (cardSize + padding)));

    return items.map((item, index) => ({
        ...item,
        x: padding + (index % columns) * (cardSize + padding),
        y: padding + Math.floor(index / columns) * (rowHeight + padding),
    }));
}

function needsReflow(items: WallItem[], wallWidth: number) {
    const { cardSize } = getLayoutMetrics();
    const maxX = Math.max(0, wallWidth - cardSize);
    return items.some((item) => item.x > maxX || item.x < 0);
}

const wallTheme = {
    "--wall-wood-1": "#2f1d12",
    "--wall-wood-2": "#25160d",
    "--wall-wood-edge": "#4a2f1c",
    "--wall-gold": "#f5d7a0",
    "--wall-cream": "#f4e6cf",
} as CSSProperties;

export default function DashboardPage() {
    const [cachedAlbums] = useState(() => loadTrackingCache());
    const [cachedWall] = useState(() => loadWallCache());
    const [albums, setAlbums] = useState<Album[]>(cachedAlbums);
    const [trackingLoading, setTrackingLoading] = useState(cachedAlbums.length === 0);
    const [error, setError] = useState<string | null>(null);
    const [layoutReady, setLayoutReady] = useState(false);
    const [wallId, setWallId] = useState<string | null>(cachedWall?.wallId ?? null);
    const [wallItems, setWallItems] = useState<WallItem[]>([]);
    const [draggingId, setDraggingId] = useState<string | null>(null);
    const [isDrawerOpen, setIsDrawerOpen] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [savedAlbumIds, setSavedAlbumIds] = useState<string[]>(cachedWall?.albumIds ?? []);
    const [baselineReady, setBaselineReady] = useState(false);
    const [albumSearch, setAlbumSearch] = useState("");
    const wallRef = useRef<HTMLDivElement | null>(null);
    const dragRef = useRef<DragState | null>(null);
    const didLoadServerRef = useRef(false);

    useEffect(() => {
        setLayoutReady(true);
    }, []);

    const redirectToLogin = async (res: Response) => {
        const body = await res.json().catch(() => ({}));
        const loginUrl = body?.login_url ?? `${API_BASE}/`;
        window.location.href = loginUrl;
    };

    const persistWallId = (nextWallId: string) => {
        setWallId(nextWallId);
    };

    useEffect(() => {
        async function fetchTracking() {
            let didRedirect = false;
            try {
                const res = await fetch(`${API_BASE}/tracking`, {
                    cache: "no-store",
                    credentials: "include",
                });

                if (res.status === 401) {
                    await redirectToLogin(res);
                    didRedirect = true;
                    return;
                }

                if (!res.ok) {
                    throw new Error("Failed to fetch tracking data");
                }

                const data = await res.json();
                setAlbums(data);
                saveTrackingCache(data);
            } catch (err) {
                setError(err instanceof Error ? err.message : "An error occurred");
            } finally {
                if (didRedirect) {
                    return;
                }
                setTrackingLoading(false);
            }
        }

        fetchTracking();
    }, []);

    const eligibleAlbums = useMemo(() => {
        return [...albums]
            .filter((album) => album.percentage >= 0.999 || album.listened >= album.total)
            .sort((a, b) => a.album_name.localeCompare(b.album_name));
    }, [albums]);

    const filteredEligibleAlbums = useMemo(() => {
        const query = albumSearch.trim().toLowerCase();
        if (!query) {
            return eligibleAlbums;
        }
        return eligibleAlbums.filter((album) => {
            const name = album.album_name.toLowerCase();
            const artist = album.artist.toLowerCase();
            return name.includes(query) || artist.includes(query);
        });
    }, [albumSearch, eligibleAlbums]);

    const eligibleAlbumIds = useMemo(() => {
        return new Set(eligibleAlbums.map((album) => album.album_id));
    }, [eligibleAlbums]);

    const albumsById = useMemo(() => {
        const map = new Map<string, Album>();
        albums.forEach((album) => map.set(album.album_id, album));
        return map;
    }, [albums]);

    useEffect(() => {
        if (!layoutReady || trackingLoading) {
            return;
        }
        setWallItems((prev) => prev.filter((item) => eligibleAlbumIds.has(item.album_id)));
    }, [layoutReady, trackingLoading, eligibleAlbumIds]);

    useEffect(() => {
        if (!layoutReady) {
            return;
        }
        setWallItems((prev) => {
            const wallWidth = wallRef.current?.clientWidth ?? 640;
            if (prev.length === 0) {
                if (!cachedWall?.albumIds?.length) {
                    return prev;
                }
                const seedItems = cachedWall.albumIds.map((album_id) => ({ album_id, x: 0, y: 0 }));
                return layoutWallItems(seedItems, wallWidth);
            }
            const hasLayout = prev.some((item) => item.x !== 0 || item.y !== 0);
            if (hasLayout) {
                return prev;
            }
            return layoutWallItems(prev, wallWidth);
        });
    }, [layoutReady, cachedWall]);

    useEffect(() => {
        if (!layoutReady || didLoadServerRef.current) {
            return;
        }
        didLoadServerRef.current = true;

        const loadServerWall = async () => {
            let didRedirect = false;
            try {
                const res = await fetch(`${API_BASE}/api/walls`, {
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
                const wall = data?.wall;
                const items = Array.isArray(data?.items) ? data.items : [];
                const nextWallId = wall?.wall_id ?? null;
                persistWallId(nextWallId);
                const nextSaved = items
                    .map((item: { album_id?: string | null }) => item.album_id)
                    .filter(Boolean) as string[];
                setSavedAlbumIds(nextSaved);
                saveWallCache(nextWallId, nextSaved);
                setBaselineReady(true);

                if (nextSaved.length > 0) {
                    const seedItems = nextSaved.map((album_id) => ({ album_id, x: 0, y: 0 }));
                    const wallWidth = wallRef.current?.clientWidth ?? 640;
                    setWallItems(layoutWallItems(seedItems, wallWidth));
                } else {
                    setWallItems([]);
                }
            } catch (err) {
                if (didRedirect) {
                    return;
                }
                console.error(err);
                setSavedAlbumIds(wallItems.map((item) => item.album_id));
                setBaselineReady(true);
            }
        };

        loadServerWall();
    }, [layoutReady, redirectToLogin, wallItems]);

    useEffect(() => {
        function handlePointerMove(event: PointerEvent) {
            const dragState = dragRef.current;
            const wall = wallRef.current;
            if (!dragState || !wall) {
                return;
            }
            const wallRect = wall.getBoundingClientRect();
            const nextX = event.clientX - wallRect.left - dragState.offsetX;
            const nextY = event.clientY - wallRect.top - dragState.offsetY;
            const maxX = wallRect.width - dragState.width;
            const maxY = wallRect.height - dragState.height;

            setWallItems((prev) =>
                prev.map((item) =>
                    item.album_id === dragState.album_id
                        ? {
                              ...item,
                              x: clamp(nextX, 0, Math.max(0, maxX)),
                              y: clamp(nextY, 0, Math.max(0, maxY)),
                          }
                        : item
                )
            );
        }

        function handlePointerUp() {
            if (dragRef.current) {
                dragRef.current = null;
                setDraggingId(null);
            }
        }

        window.addEventListener("pointermove", handlePointerMove);
        window.addEventListener("pointerup", handlePointerUp);
        window.addEventListener("pointercancel", handlePointerUp);

        return () => {
            window.removeEventListener("pointermove", handlePointerMove);
            window.removeEventListener("pointerup", handlePointerUp);
            window.removeEventListener("pointercancel", handlePointerUp);
        };
    }, []);

    useEffect(() => {
        if (!layoutReady) {
            return;
        }
        const wall = wallRef.current;
        if (!wall) {
            return;
        }

        const ensureLayoutFits = (width: number) => {
            if (width <= 0) {
                return;
            }
            setWallItems((prev) => {
                if (prev.length === 0) {
                    return prev;
                }
                if (!needsReflow(prev, width)) {
                    return prev;
                }
                return layoutWallItems(prev, width);
            });
        };

        let lastWidth = wall.clientWidth;
        ensureLayoutFits(lastWidth);

        const observer = new ResizeObserver(() => {
            if (draggingId) {
                return;
            }
            const nextWidth = wall.clientWidth;
            if (nextWidth === lastWidth) {
                return;
            }
            lastWidth = nextWidth;
            setWallItems((prev) => {
                if (prev.length === 0) {
                    return prev;
                }
                return layoutWallItems(prev, nextWidth);
            });
        });

        observer.observe(wall);

        return () => {
            observer.disconnect();
        };
    }, [layoutReady, draggingId]);

    const wallIds = useMemo(() => new Set(wallItems.map((item) => item.album_id)), [wallItems]);
    const savedAlbumIdSet = useMemo(() => new Set(savedAlbumIds), [savedAlbumIds]);
    const hasUnsavedChanges = useMemo(() => {
        if (!baselineReady) {
            return false;
        }
        if (wallIds.size !== savedAlbumIdSet.size) {
            return true;
        }
        for (const albumId of wallIds) {
            if (!savedAlbumIdSet.has(albumId)) {
                return true;
            }
        }
        return false;
    }, [wallIds, savedAlbumIdSet]);
    const wallContentHeight = useMemo(() => {
        if (wallItems.length === 0) {
            return null;
        }
        const { rowHeight, padding } = getLayoutMetrics();
        let maxY = 0;
        for (const item of wallItems) {
            if (item.y > maxY) {
                maxY = item.y;
            }
        }
        return Math.ceil(maxY + rowHeight + padding);
    }, [wallItems]);

    const handleAddToWall = (album: Album) => {
        if (wallIds.has(album.album_id)) {
            return;
        }
        if (saveError) {
            setSaveError(null);
        }
        setWallItems((prev) => {
            if (prev.some((item) => item.album_id === album.album_id)) {
                return prev;
            }
            const wall = wallRef.current;
            const { cardSize, rowHeight, padding } = getLayoutMetrics();
            const wallWidth = wall?.clientWidth ?? 640;
            const columns = Math.max(1, Math.floor((wallWidth - padding) / (cardSize + padding)));
            const index = prev.length;
            const x = padding + (index % columns) * (cardSize + padding);
            const y = padding + Math.floor(index / columns) * (rowHeight + padding);

            return [...prev, { album_id: album.album_id, x, y }];
        });
    };

    const handleRemoveFromWall = (albumId: string) => {
        if (saveError) {
            setSaveError(null);
        }
        setWallItems((prev) => prev.filter((item) => item.album_id !== albumId));
    };

    const handleClearWall = () => {
        if (wallItems.length === 0) {
            return;
        }
        if (saveError) {
            setSaveError(null);
        }
        setWallItems([]);
    };

    const handleSaveWall = async () => {
        if (isSaving || !hasUnsavedChanges) {
            return;
        }
        setIsSaving(true);
        setSaveError(null);
        const albumIds = Array.from(new Set(wallItems.map((item) => item.album_id)));
        let activeWallId = wallId;
        const currentAlbumSet = new Set(albumIds);
        const hasRemoved = savedAlbumIds.some((albumId) => !currentAlbumSet.has(albumId));

        try {
            if (albumIds.length === 0) {
                if (activeWallId) {
                    const res = await fetch(`${API_BASE}/api/walls/items`, {
                        method: "DELETE",
                        headers: { "Content-Type": "application/json" },
                        credentials: "include",
                        body: JSON.stringify({ wall_id: activeWallId }),
                    });

                    if (res.status === 401) {
                        await redirectToLogin(res);
                        return;
                    }

                    if (res.status === 404) {
                        persistWallId(null);
                        setSavedAlbumIds([]);
                        saveWallCache(null, []);
                        return;
                    }

                    if (!res.ok) {
                        throw new Error("Failed to clear wall");
                    }
                }

                setSavedAlbumIds([]);
                saveWallCache(activeWallId, []);
                return;
            }

            if (activeWallId && hasRemoved) {
                const res = await fetch(`${API_BASE}/api/walls/items`, {
                    method: "DELETE",
                    headers: { "Content-Type": "application/json" },
                    credentials: "include",
                    body: JSON.stringify({ wall_id: activeWallId }),
                });

                if (res.status === 401) {
                    await redirectToLogin(res);
                    return;
                }

                if (res.status === 404) {
                    persistWallId(null);
                    activeWallId = null;
                } else if (!res.ok) {
                    throw new Error("Failed to reset wall before saving");
                }
            }

            const sendSave = (targetWallId: string | null) =>
                fetch(`${API_BASE}/api/walls/items`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    credentials: "include",
                    body: JSON.stringify({
                        album_ids: albumIds,
                        wall_id: targetWallId ?? undefined,
                    }),
                });

            let res = await sendSave(activeWallId);

            if (res.status === 401) {
                await redirectToLogin(res);
                return;
            }

            if (res.status === 404 && activeWallId) {
                persistWallId(null);
                activeWallId = null;
                res = await sendSave(null);

                if (res.status === 401) {
                    await redirectToLogin(res);
                    return;
                }
            }

            if (!res.ok) {
                const detail = await res.json().catch(() => ({}));
                console.error("Save wall failed", detail);
                throw new Error("Failed to save wall");
            }

            const body = await res.json().catch(() => ({}));
            const nextWallId = body?.wall_id ?? activeWallId ?? null;
            if (body?.wall_id) {
                persistWallId(body.wall_id);
            }
            setSavedAlbumIds(albumIds);
            saveWallCache(nextWallId, albumIds);
        } catch (err) {
            console.error(err);
            setSaveError(err instanceof Error ? err.message : "Failed to save wall");
        } finally {
            setIsSaving(false);
        }
    };

    const handlePointerDown = (albumId: string) => (event: ReactPointerEvent<HTMLDivElement>) => {
        if (event.button !== 0) {
            return;
        }
        const wall = wallRef.current;
        if (!wall) {
            return;
        }
        const target = event.currentTarget;
        const targetRect = target.getBoundingClientRect();

        dragRef.current = {
            album_id: albumId,
            offsetX: event.clientX - targetRect.left,
            offsetY: event.clientY - targetRect.top,
            width: targetRect.width,
            height: targetRect.height,
        };
        setDraggingId(albumId);
        target.setPointerCapture(event.pointerId);
    };

    const loading = trackingLoading;

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-[#1D1411] to-[#0F0B09]">
                <div className="font-body text-white text-xl">Loading...</div>
            </div>
        );
    }

    if (error) {
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
            <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-6">
                <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
                    <button
                        type="button"
                        onClick={handleSaveWall}
                        disabled={isSaving || !hasUnsavedChanges}
                        className={`w-full sm:w-auto text-[11px] sm:text-xs uppercase tracking-widest px-3 py-2 rounded-full border transition-colors ${
                            isSaving
                                ? "border-white/20 text-white/50 cursor-wait"
                                : hasUnsavedChanges
                                    ? "border-[#f5d7a0]/70 text-[#f5d7a0] hover:border-[#f5d7a0] hover:text-[#f5d7a0]"
                                    : "border-white/10 text-white/40 cursor-default"
                        }`}
                    >
                        {isSaving ? "Saving..." : hasUnsavedChanges ? "Save Wall" : "Saved"}
                    </button>
                    <button
                        type="button"
                        onClick={handleClearWall}
                        className="w-full sm:w-auto text-[11px] sm:text-xs uppercase tracking-widest px-3 py-2 rounded-full border border-white/20 text-white/70 hover:border-white/40 hover:text-white transition-colors"
                    >
                        Clear Wall
                    </button>

                    <Link
                        href="/shared_walls"
                        className="w-full sm:w-auto text-[11px] sm:text-xs uppercase tracking-widest px-3 py-2 rounded-full border border-white/15 text-white/60 hover:border-white/40 hover:text-white transition-colors text-center"
                    >
                        Shared Walls
                    </Link>

                    <button
                        type="button"
                        onClick={() => setIsDrawerOpen((open) => !open)}
                        className="w-full sm:w-auto sm:ml-auto inline-flex items-center justify-between sm:justify-start gap-3 rounded-full border border-white/15 bg-black/30 px-4 py-2 text-white/80 hover:text-white hover:border-white/40 transition-colors"
                    >
                        <span className="flex flex-col gap-1">
                            <span className="h-0.5 w-4 rounded-full bg-white/70" />
                            <span className="h-0.5 w-6 rounded-full bg-white/70" />
                            <span className="h-0.5 w-3 rounded-full bg-white/70" />
                        </span>
                        <span className="font-display text-lg tracking-[0.2em] uppercase">
                            Albums
                        </span>
                        <span className="text-xs text-white/50">{eligibleAlbums.length}</span>
                    </button>
                </div>
                {saveError ? (
                    <div className="mb-4 text-xs text-red-200 bg-red-900/30 border border-red-300/20 rounded-2xl px-4 py-2">
                        {saveError}
                    </div>
                ) : null}

                <div
                    className="relative w-full h-[70vh] sm:h-[80vh] min-h-[360px] sm:min-h-[520px] rounded-[24px] sm:rounded-[36px] border shadow-[0_30px_80px_rgba(0,0,0,0.55)] overflow-y-auto overflow-x-hidden select-none"
                    style={{ borderColor: "var(--wall-wood-edge)" }}
                >
                    <div
                        ref={wallRef}
                        className="relative w-full min-h-full"
                        style={{
                            height: wallContentHeight ?? undefined,
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

                        {wallItems.length === 0 ? (
                            <div className="absolute inset-0 flex items-center justify-center">
                                <div className="text-white/70 text-sm bg-black/30 rounded-full px-6 py-3">
                                    Add completed albums to start building your wall.
                                </div>
                            </div>
                        ) : (
                            wallItems.map((item) => {
                                const album = albumsById.get(item.album_id);
                                if (!album) {
                                    return null;
                                }
                                const isDragging = draggingId === item.album_id;
                                return (
                                    <div
                                        key={item.album_id}
                                        className={`absolute group cursor-grab active:cursor-grabbing ${
                                            isDragging ? "z-30" : "z-10"
                                        }`}
                                        style={{
                                            left: item.x,
                                            top: item.y,
                                            touchAction: "none",
                                        }}
                                        onPointerDown={handlePointerDown(item.album_id)}
                                    >
                                        <div className="flex flex-col items-center">
                                            <div className="relative w-[140px] h-[140px] sm:w-[150px] sm:h-[150px] md:w-[175px] md:h-[175px]">
                                                <div className="absolute inset-0 rounded-full bg-gradient-to-br from-[#111] via-[#1a1a1a] to-[#050505] shadow-[0_10px_25px_rgba(0,0,0,0.55)]" />
                                                <div className="absolute inset-2 rounded-full border border-white/10" />
                                                <div className="absolute inset-5 rounded-full border border-white/5" />
                                                <div className="absolute inset-[26%] rounded-full overflow-hidden border border-white/10 bg-black/50">
                                                    {album.album_image ? (
                                                        <Image
                                                            src={album.album_image}
                                                            alt={album.album_name}
                                                            fill
                                                            sizes="120px"
                                                            className="object-cover"
                                                        />
                                                    ) : (
                                                        <div className="w-full h-full flex items-center justify-center text-white/40 text-lg">note</div>
                                                    )}
                                                </div>
                                                <div
                                                    className="absolute left-1/2 top-1/2 w-2 h-2 rounded-full -translate-x-1/2 -translate-y-1/2 shadow-[0_0_6px_rgba(0,0,0,0.6)]"
                                                    style={{ backgroundColor: "var(--wall-gold)" }}
                                                />
                                                <button
                                                    type="button"
                                                    onClick={(event) => {
                                                        event.stopPropagation();
                                                        handleRemoveFromWall(item.album_id);
                                                    }}
                                                    className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-black/60 border border-white/20 text-white/70 text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                                                >
                                                    x
                                                </button>
                                            </div>
                                            <div className="mt-2 text-center">
                                                <div className="text-[11px] uppercase tracking-[0.2em] text-white/80">
                                                    {album.album_name}
                                                </div>
                                                <div className="text-[10px] uppercase tracking-[0.25em]" style={{ color: "var(--wall-gold)" }}>
                                                    {album.artist}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })
                        )}
                    </div>
                </div>
            </div>

            <div
                className={`fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity z-40 ${
                    isDrawerOpen ? "opacity-100" : "opacity-0 pointer-events-none"
                }`}
                onClick={() => setIsDrawerOpen(false)}
            />

            <aside
                className={`fixed right-0 top-0 h-full w-full sm:w-[360px] bg-[#17110E]/95 border-l border-white/10 shadow-2xl z-50 transform transition-transform duration-300 ${
                    isDrawerOpen ? "translate-x-0" : "translate-x-full pointer-events-none"
                }`}
            >
                <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
                    <div>
                        <div className="font-display text-xl tracking-[0.25em] text-white">
                            Completed
                        </div>
                        <div className="text-xs text-white/50 uppercase tracking-[0.2em]">
                            Drag on wall after adding
                        </div>
                    </div>
                    <button
                        type="button"
                        onClick={() => setIsDrawerOpen(false)}
                        className="h-8 w-8 rounded-full border border-white/15 text-white/70 hover:text-white hover:border-white/40 transition-colors"
                    >
                        x
                    </button>
                </div>

                <div className="px-5 py-4">
                    <div className="mb-4">
                        <label htmlFor="completed-search" className="sr-only">
                            Search completed albums
                        </label>
                        <input
                            id="completed-search"
                            type="search"
                            value={albumSearch}
                            onChange={(event) => setAlbumSearch(event.target.value)}
                            placeholder="Search albums or artists"
                            className="w-full rounded-full border border-white/15 bg-black/30 px-4 py-2 text-sm text-white placeholder:text-white/40 focus:outline-none focus:border-white/40"
                        />
                    </div>
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-sm text-white/80">Albums ready</span>
                        <span className="text-xs text-white/50">
                            {albumSearch.trim()
                                ? `${filteredEligibleAlbums.length} / ${eligibleAlbums.length}`
                                : eligibleAlbums.length}
                        </span>
                    </div>

                    {eligibleAlbums.length === 0 ? (
                        <div className="text-white/60 text-sm bg-black/30 rounded-2xl p-4">
                            No completed albums yet.
                        </div>
                    ) : filteredEligibleAlbums.length === 0 ? (
                        <div className="text-white/60 text-sm bg-black/30 rounded-2xl p-4">
                            No matches for "{albumSearch.trim()}".
                        </div>
                    ) : (
                        <div className="space-y-3 max-h-[65vh] sm:max-h-[72vh] overflow-y-auto pr-1">
                            {filteredEligibleAlbums.map((album) => {
                                const isAdded = wallIds.has(album.album_id);
                                return (
                                    <div
                                        key={album.album_id}
                                        className="flex items-center gap-3 rounded-2xl bg-black/30 hover:bg-black/40 transition-colors p-2.5 sm:p-3"
                                    >
                                        <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-xl overflow-hidden bg-white/10 flex items-center justify-center">
                                            {album.album_image ? (
                                                <Image
                                                    src={album.album_image}
                                                    alt={album.album_name}
                                                    width={48}
                                                    height={48}
                                                    className="object-cover w-full h-full"
                                                />
                                            ) : (
                                                <span className="text-white/30 text-lg">note</span>
                                            )}
                                        </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-white text-sm font-semibold truncate">{album.album_name}</div>
                                        <div className="text-white/60 text-xs truncate">{album.artist}</div>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() =>
                                            isAdded ? handleRemoveFromWall(album.album_id) : handleAddToWall(album)
                                        }
                                        className={`text-xs uppercase tracking-widest px-3 py-1 rounded-full border transition-colors ${
                                            isAdded
                                                ? "border-white/30 text-white/70 hover:border-white/60 hover:text-white"
                                                : "border-[#f5d7a0]/60 text-[#f5d7a0] hover:bg-[#f5d7a0]/10"
                                        }`}
                                    >
                                        {isAdded ? "Remove" : "Add"}
                                    </button>
                                </div>
                            );
                        })}
                        </div>
                    )}
                </div>
            </aside>
        </div>
    );
}
