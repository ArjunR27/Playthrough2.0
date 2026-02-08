export type SharedWallItem = {
    album_id: string;
    album_name?: string | null;
    artist_name?: string | null;
    album_image?: string | null;
};

export type SharedWall = {
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

type SharedWallsCache = {
    walls: SharedWall[];
    updatedAt: number;
};

type SharedWallDetailEntry = {
    wall: SharedWall["wall"];
    items: SharedWallItem[];
    updatedAt: number;
};

type SharedWallDetailStore = Record<string, SharedWallDetailEntry>;

const SHARED_WALLS_CACHE_KEY = "playthrough.sharedWalls.v1";
const SHARED_WALL_DETAIL_CACHE_KEY = "playthrough.sharedWalls.detail.v1";
const SHARED_WALL_CACHE_TTL_MS = 1000 * 60 * 15;

function isFresh(updatedAt: number) {
    if (!updatedAt) {
        return false;
    }
    return Date.now() - updatedAt < SHARED_WALL_CACHE_TTL_MS;
}

function safeParse<T>(raw: string | null): T | null {
    if (!raw) {
        return null;
    }
    try {
        return JSON.parse(raw) as T;
    } catch {
        return null;
    }
}

function safeRead(key: string): string | null {
    if (typeof window === "undefined") {
        return null;
    }
    try {
        return window.localStorage.getItem(key);
    } catch {
        return null;
    }
}

export function loadSharedWallsCache(): (SharedWallsCache & { isFresh: boolean }) | null {
    if (typeof window === "undefined") {
        return null;
    }
    const parsed = safeParse<SharedWallsCache>(safeRead(SHARED_WALLS_CACHE_KEY));
    if (!parsed || !Array.isArray(parsed.walls)) {
        return null;
    }
    const updatedAt = typeof parsed.updatedAt === "number" ? parsed.updatedAt : 0;
    return {
        walls: parsed.walls,
        updatedAt,
        isFresh: isFresh(updatedAt),
    };
}

export function saveSharedWallsCache(walls: SharedWall[]) {
    if (typeof window === "undefined") {
        return;
    }
    try {
        const payload: SharedWallsCache = {
            walls,
            updatedAt: Date.now(),
        };
        window.localStorage.setItem(SHARED_WALLS_CACHE_KEY, JSON.stringify(payload));
        primeSharedWallDetails(walls, payload.updatedAt);
    } catch {
        // Ignore cache write failures.
    }
}

function readSharedWallDetailStore(): SharedWallDetailStore {
    if (typeof window === "undefined") {
        return {};
    }
    const parsed = safeParse<SharedWallDetailStore>(safeRead(SHARED_WALL_DETAIL_CACHE_KEY));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        return {};
    }
    return parsed;
}

function writeSharedWallDetailStore(store: SharedWallDetailStore) {
    if (typeof window === "undefined") {
        return;
    }
    try {
        window.localStorage.setItem(SHARED_WALL_DETAIL_CACHE_KEY, JSON.stringify(store));
    } catch {
        // Ignore cache write failures.
    }
}

export function primeSharedWallDetails(walls: SharedWall[], updatedAt?: number) {
    if (typeof window === "undefined") {
        return;
    }
    const store = readSharedWallDetailStore();
    const timestamp = typeof updatedAt === "number" ? updatedAt : Date.now();
    walls.forEach((entry) => {
        if (!entry?.wall?.wall_id) {
            return;
        }
        store[entry.wall.wall_id] = {
            wall: entry.wall,
            items: Array.isArray(entry.items) ? entry.items : [],
            updatedAt: timestamp,
        };
    });
    writeSharedWallDetailStore(store);
}

export function saveSharedWallDetail(wall: SharedWall) {
    if (typeof window === "undefined") {
        return;
    }
    if (!wall?.wall?.wall_id) {
        return;
    }
    const store = readSharedWallDetailStore();
    store[wall.wall.wall_id] = {
        wall: wall.wall,
        items: Array.isArray(wall.items) ? wall.items : [],
        updatedAt: Date.now(),
    };
    writeSharedWallDetailStore(store);
}

export function loadSharedWallDetail(
    wallId: string
): (SharedWallDetailEntry & { isFresh: boolean }) | null {
    if (typeof window === "undefined") {
        return null;
    }
    const store = readSharedWallDetailStore();
    const entry = store[wallId];
    if (entry) {
        return {
            ...entry,
            isFresh: isFresh(entry.updatedAt),
        };
    }

    const listCache = loadSharedWallsCache();
    const fallback = listCache?.walls?.find((item) => item?.wall?.wall_id === wallId);
    if (!fallback) {
        return null;
    }
    const fallbackEntry: SharedWallDetailEntry = {
        wall: fallback.wall,
        items: Array.isArray(fallback.items) ? fallback.items : [],
        updatedAt: listCache?.updatedAt ?? Date.now(),
    };
    const nextStore = readSharedWallDetailStore();
    nextStore[wallId] = fallbackEntry;
    writeSharedWallDetailStore(nextStore);
    return {
        ...fallbackEntry,
        isFresh: isFresh(fallbackEntry.updatedAt),
    };
}
