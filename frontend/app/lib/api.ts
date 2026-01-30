const DEFAULT_API_BASE = "http://127.0.0.1:3000";

if (
    process.env.NODE_ENV === "production" &&
    !process.env.NEXT_PUBLIC_API_BASE_URL
) {
    throw new Error(
        "NEXT_PUBLIC_API_BASE_URL is required in production to avoid localhost fallback."
    );
}

export const API_BASE = (
    process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE
).replace(/\/+$/, "");
