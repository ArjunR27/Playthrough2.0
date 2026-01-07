export interface Album {
    album_id: string,
    album_name: string,
    artist_name: string,
    total_tracks: number,
    listened: number,
}

export interface Track {
    track_id: string, 
    track_name: string,
    track_number: number,
    album_name: string,
    album_id: string,
}

export interface User {
    user_id: string,
    display_name: string,
}