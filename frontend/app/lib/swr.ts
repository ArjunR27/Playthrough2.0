export type FetcherError = Error & {
    status?: number;
    info?: unknown;
};

export async function authedFetcher<T>(url: string): Promise<T> {
    const res = await fetch(url, {
        cache: "no-store",
        credentials: "include",
    });

    if (res.status === 401) {
        const info = await res.json().catch(() => ({}));
        const error: FetcherError = new Error("unauthorized");
        error.status = 401;
        error.info = info;
        throw error;
    }

    if (!res.ok) {
        const info = await res.json().catch(() => null);
        const error: FetcherError = new Error("request_failed");
        error.status = res.status;
        error.info = info;
        throw error;
    }

    return res.json() as Promise<T>;
}
