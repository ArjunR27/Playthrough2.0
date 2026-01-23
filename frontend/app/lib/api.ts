const DEFAULT_API_BASE = "http://127.0.0.1:3000";

export const API_BASE = (
    process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE
).replace(/\/+$/, "");
