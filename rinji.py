"""
rinji.py

Package

Created by kinami on 2024-09-20
"""
from datetime import datetime

import spotipy
import typer
from dotenv import load_dotenv
from questionary import select, Choice, checkbox, confirm
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth


def connect(spotify_client_id: str, spotify_client_secret: str, spotify_redirect_uri: str, spotify_scope: str):
    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=spotify_client_id,
            client_secret=spotify_client_secret,
            redirect_uri=spotify_redirect_uri,
            scope=spotify_scope
        )
    )


def get_artist_id(sp: Spotify, artist: str):
    """https://open.spotify.com/artist/38WbKH6oKAZskBhqDFA8Uj"""
    if artist.startswith('https://open.spotify.com/artist/'):
        artist_id = artist.split('/')[-1].split('?')[0]
    else:
        results = sp.search(q=f'artist:{artist}', type='artist')['artists']['items']
        if len(results) == 0:
            print("Can't find that artist")
            exit()
        elif len(results) == 1:
            if confirm(f"Is '{results[0]['name']}' ({results[0]["external_urls"]["spotify"]}) the artist you are looking for? ").ask():
                return results[0]['id']
            else:
                print('Then be more specific')
        else:
            return select(
                "Which artist?",
                choices=[
                    Choice(title=f'{item["name"]} ({item["external_urls"]["spotify"]})', value=item['id'])
                    for item in results
                ]
            ).ask()
    return artist_id


def get_albums(sp, artist_id):
    """Get songs"""
    albums = sp.artist_albums(artist_id, limit=50, country='ES')['items']

    impure = [
        any(artist['id'] != artist_id for artist in album['artists']) or album['album_group'] == 'compilation'
        for album in albums
    ]

    sel_impure = checkbox(
        "These albums do not seem to be pure, please select the ones you want to include",
        choices=[
            Choice(title=f'{album["name"]} ({album["external_urls"]["spotify"]})', value=i)
            for i, album in enumerate(albums) if impure[i]
        ]
    ).ask() if impure else []

    print('Getting albums...')
    albums_clean = sorted([
        {
            'name': album['name'],
            'date': datetime.strptime(album['release_date'], '%Y-%m-%d').date(),
            'tracks': [
                {
                    'id': track['id'],
                    'name': track['name'],
                    'track_number': track['track_number'],
                    'album': album['name'],
                    'date': datetime.strptime(album['release_date'], '%Y-%m-%d').date()
                }
                for track in sp.album_tracks(album['id'])['items']
            ],
            'type': 'EP' if album['album_type'] == 'single' and album['total_tracks'] >= 6 else album['album_type'],
        }
        for i, album in enumerate(albums) if not impure[i] or i in sel_impure
    ], key=lambda x: x['date'])

    return albums_clean


def compile_songlist(sp, albums):
    """Compile songlist"""
    print('Compiling songlist...')
    songlist = []
    nameset = {song['name'] for album in albums for song in album['tracks']}

    for album in albums:
        if album['type'] == 'album':
            songlist.extend(album['tracks'])
            albums.remove(album)

    for album in sorted(albums, key=lambda x: 1 if x['type'] == 'EP' else 2):
        track_names = [song['name'] for song in songlist]
        if album['tracks'][0]['name'] in track_names:
            pos = track_names.index(album['tracks'][0]['name'])
            songlist.pop(pos)
            for song in album['tracks']:
                songlist.insert(pos, song)
                pos += 1
        else:
            pos = next((i for i, song in enumerate(songlist) if song['date'] > album['date']), None)
            if pos is not None:
                for song in album['tracks']:
                    songlist.insert(pos, song)
                    pos += 1
            else:
                songlist.extend(album['tracks'])

    for song in songlist:
        for s in songlist:
            if song['name'] == s['name'] and song != s:
                songlist.remove(s)

    assert len(songlist) == len(nameset), 'Songs were lost in the process!'

    return songlist


def add_to_playlist(spotify, songs, playlist_id):
    """Add songs to playlist"""
    print(f'Adding {len(songs)} songs to the playlist...')
    songs_split = [songs[i:i + 100] for i in range(0, len(songs), 100)]
    for songs in songs_split:
        spotify.playlist_add_items(
            playlist_id=playlist_id,
            items=[song['id'] for song in songs]
        )


def main(
        artist: str = typer.Argument(..., help='Artist name or link'),
        spotify_client_id: str = typer.Option(..., prompt=True, help='Spotify client ID', envvar='RINJI_CLIENT_ID'),
        spotify_client_secret: str = typer.Option(..., prompt=True, help='Spotify client secret',
                                                  envvar='RINJI_CLIENT_SECRET'),
        spotify_redirect_uri: str = typer.Option(..., prompt=True, help='Spotify redirect URI',
                                                 envvar='RINJI_REDIRECT_URI'),
        spotify_scope: str = typer.Option(..., prompt=True, help='Spotify scope', envvar='RINJI_SCOPE'),
        main_playlist_id: str = typer.Option(..., prompt=True, help='Main playlist ID',
                                             envvar='RINJI_MAIN_PLAYLIST_ID'),
        tmp_playlist_id: str = typer.Option(..., prompt=True, help='Temporary playlist ID',
                                            envvar='RINJI_TEMP_PLAYLIST_ID'),
        reverse: bool = typer.Option(False, "-r", help='Reverse the order of the songs'),
        dry_run: bool = typer.Option(False, "-d", help='Dry run')
):
    sp = connect(spotify_client_id, spotify_client_secret, spotify_redirect_uri, spotify_scope)
    artist_id = get_artist_id(sp, artist)
    albums = get_albums(sp, artist_id)
    songs = compile_songlist(sp, albums)
    if reverse:
        songs = songs[::-1]
    if dry_run:
        print('Songs would have been added in this order:')
        for i, song in enumerate(songs, 1):
            print(f'{i}. {song["name"]} - {song["album"]}')
    else:
        add_to_playlist(sp, songs, tmp_playlist_id)


if __name__ == '__main__':
    load_dotenv()
    typer.run(main)
