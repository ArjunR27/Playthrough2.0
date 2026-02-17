"use client"

import { createContext, useContext, useState, useEffect, ReactNode, useCallback, useRef } from 'react';
import { API_BASE } from '../lib/api';

type User = {
    id: string;
    display_name: string | null;
    provider: string;
}

type AuthContextType = {
    isAuthenticated: boolean | null; // null = checking, true/false = known state
    user: User | null;
    login: (provider?: "spotify" | "lastfm", username?: string) => Promise<void>;
    checkAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
    const [user, setUser] = useState<User | null>(null);
    const checkingRef = useRef<Promise<void> | null>(null);

    const checkAuth = useCallback(async () => {
        if (checkingRef.current) {
            await checkingRef.current;
            return;
        }

        const task = (async () => {
            try {
                const res = await fetch(`${API_BASE}/profile`, {
                    cache: "no-store",
                    credentials: "include",
                });

                if (res.status === 401) {
                    setIsAuthenticated(false);
                    setUser(null);
                    return;
                }

                if (!res.ok) {
                    throw new Error("request_failed");
                }

                const data = await res.json().catch(() => ({}));
                setIsAuthenticated(true);
                setUser({
                    id: data?.id ?? "",
                    display_name: data?.display_name ?? null,
                    provider: data?.provider ?? "unknown",
                });
            } catch {
                setIsAuthenticated(false);
                setUser(null);
            }
        })();

        checkingRef.current = task;
        try {
            await task;
        } finally {
            checkingRef.current = null;
        }
    }, []);

    const login = async (provider: "spotify" | "lastfm" = "spotify", username?: string) => {
        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: 'include',
                body: JSON.stringify({
                    provider,
                    username,
                }),
            });
            const data = await res.json();
            window.location.href = data.login_url;
        } catch (err) {
            console.error('Login failed:', err);
        }
    };

    useEffect(() => {
        // Run a single auth check on mount.
        checkAuth();

        const params = new URLSearchParams(window.location.search);
        if (params.get('auth') === 'success') {
            window.history.replaceState({}, '', window.location.pathname);
        }

        const handleAuthChange = () => {
            checkAuth();
        };

        window.addEventListener('auth-change', handleAuthChange);
        return () => {
            window.removeEventListener('auth-change', handleAuthChange);
        };
    }, [checkAuth]);

    return (
        <AuthContext.Provider value={{ isAuthenticated, user, login, checkAuth }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
