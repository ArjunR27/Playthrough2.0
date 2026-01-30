"use client"

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { API_BASE, withReturnTo } from '../lib/api';

type User = {
    id: string;
    display_name: string | null;
}

type AuthContextType = {
    isAuthenticated: boolean | null; // null = checking, true/false = known state
    user: User | null;
    login: () => Promise<void>;
    checkAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
    const [user, setUser] = useState<User | null>(null);

    const checkAuth = async () => {
        // Don't check auth proactively - let API calls handle it
        // This function is kept for compatibility but does nothing
        return;
    };

    const login = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                credentials: 'include',
            });
            const data = await res.json();
            const loginUrl = data?.login_url ?? `${API_BASE}/`;
            const returnTo = window.location.href;
            window.location.href = withReturnTo(loginUrl, returnTo);
        } catch (err) {
            console.error('Login failed:', err);
        }
    };

    useEffect(() => {
        // Don't check auth on mount - let API calls handle it naturally
        // Only handle auth callback from URL params if needed
        const params = new URLSearchParams(window.location.search);
        if (params.get('auth') === 'success') {
            // Clean up URL
            window.history.replaceState({}, '', window.location.pathname);
        }
    }, []);

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
