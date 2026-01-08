import { cookies } from "next/headers"; 
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

async function getRecents(): Promise<Recent []> {
    const cookieStore = cookies();
    const cookieHeader = (await cookieStore).getAll().map((c) => `${c.name}=${c.value}`).join(";");

    const res = await fetch("http://127.0.0.1:3000/recents", { 
        headers: { cookie: cookieHeader },
        cache: "no-store"
    });

    if (!res.ok) {
        throw new Error(`Failed ${res.status} ${res.statusText}`);
    }
    else {
        return (await res.json()) as Recent[]; 
    }
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

export default async function RecentlyListenedPage() {
    const recents = await getRecents(); 
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