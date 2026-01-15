"use client"

import { useState, useEffect } from 'react';  
import Image from 'next/image'; 

type Recent = {
    track_name: string;
    artists: string[],
    album_name: string,
    album_type: string,
    album_id: string,
    album_image: string,
    album_image_height: number, 
    album_image_width: number,
    played_at: string
}

type HeaderProps = {
    title?: string;
}

type URLProp = {
    url: string
}

function Header({ title }: HeaderProps): React.ReactElement {
    return <h1> { title } </h1>; 
}

function AlbumCover({ url }: URLProp): React.ReactElement {
    return (
        <div>
            <Image
                src={ url }
                alt="Album Cover"
                width={200}
                height={200}
            />
        </div>
    )
}

export default function RecentlyListenedPage() {
    const [recents, setRecents] = useState<Recent[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null); 

    useEffect(() => {
        async function fetchRecents() {
            try {
                const res = await fetch("http://127.0.0.1:3000/recents", {
                    cache: "no-store",
                    credentials: "include", 
                }); 

                if (res.status === 401) {
                    const body = await res.json().catch(() => ({}));
                    const loginUrl = body?.login_url ?? "http://127.0.0.1:3000/";
                    // changes the current url to the login url because the user is not correctly authenticated with spotify
                    window.location.href = loginUrl;
                    return
                }

                if (!res.ok) {
                    throw new Error('Failed to fetch recents')
                }

                const data = await res.json();
                setRecents(data)
            } catch (err) {
                setError(err instanceof Error ? err.message : 'An error occured'); 
            } finally {
                setLoading(false); 
            }
        }

        fetchRecents(); 

    }, [])

    if (loading) return <div> Loading... </div>;
    if (error) return <div> Error... </div>; 

    return (
        <div>
            <Header title = 'Recently Listened Songs' />
            <ul>
                {recents.map((song) => (
                    <li key={ song.track_name + song.played_at}> Song: {song.track_name} 
                        <ul>
                            { song.artists.map((artist) => (
                                <li key={ artist } > Artist: { artist }</li>
                            ))}
                            <li> Album: { song.album_name }</li>
                            <AlbumCover url = { song.album_image } />
                        </ul>
                    </li> 
                ))}
            </ul>
        </div>
    ); 
}