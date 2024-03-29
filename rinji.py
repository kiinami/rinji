"""
rinji.py

Package 

Created by kinami on 2022-11-21
"""
import os
from datetime import datetime

import spotipy
from dotenv import load_dotenv
from questionary import select, text, Choice, checkbox
from spotipy.oauth2 import SpotifyOAuth


def connect():
    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=os.getenv('RINJI_CLIENT_ID'),
            client_secret=os.getenv('RINJI_CLIENT_SECRET'),
            redirect_uri=os.getenv('RINJI_REDIRECT_URI'),
            scope=os.getenv('RINJI_SCOPE')
        )
    )


def get_playlist_items(sp, playlist_id, tracks=False):
    """Get playlist items"""
    offset = 0
    items = []
    while True:
        response = sp.playlist_items(playlist_id, offset=offset)
        if tracks:
            items.extend(e['track'] for e in response['items'])
        else:
            items.extend(response['items'])
        if len(response['items']) == 0:
            break
        offset = offset + len(response['items'])
    return items


def check_for_listened(sp: spotipy.Spotify):
    """Check for listened songs"""
    main_items = get_playlist_items(sp, os.getenv('RINJI_MAIN_PLAYLIST_ID'), tracks=True)
    temp_items = get_playlist_items(sp, os.getenv('RINJI_TEMP_PLAYLIST_ID'), tracks=True)

    listened_artists = {(tt['artists'][0]['id'], tt['artists'][0]['name']) for tt in temp_items if tt in main_items}

    if listened_artists:
        selected = checkbox(
            'It seems that some artists in your temporary playlists are already added. Which do you want to remove?',
            choices=[
                Choice(e[1], e[0])
                for e in
                listened_artists
            ]
        ).ask()
        if selected:
            sp.playlist_remove_all_occurrences_of_items(
                playlist_id=os.getenv('RINJI_TEMP_PLAYLIST_ID'),
                items=[tt['id'] for tt in temp_items if tt['artists'][0]['id'] in selected]
            )

def get_artist_id(sp):
    """Get artist id"""
    artist_name = text('Artist name: ').ask()
    results = sp.search(q=f'artist:{artist_name}', type='artist')['artists']['items']
    if len(results) == 0:
        print("Can't find that artist")
        exit()
    elif len(results) == 1:
        return results[0]['id']
    else:
        return select(
            "Which artist?",
            choices=[
                Choice(title=f'{item["name"]} ({item["external_urls"]["spotify"]})', value=item['id'])
                for item in results
            ]
        ).ask()


def get_songs(sp, artist_id):
    """Get songs"""
    albums = sp.artist_albums(artist_id, limit=50, country='ES')['items']
    impure = [
        any([artist['id'] != artist_id for artist in album['artists']]) or
        album['album_group'] == 'compilation'
        for album in albums
    ]
    sel_impure = []
    if impure:
        sel_impure = checkbox(
            "These albums do not seem to be pure, please select the ones you want to include",
            choices=[
                Choice(title=f'{album["name"]} ({album["external_urls"]["spotify"]})', value=i)
                for i, album in enumerate(albums) if impure[i]
            ]
        ).ask()
    albums = [
        album
        for i, album in enumerate(albums) if not impure[i] or i in sel_impure
    ]
    albums_clean = {}
    for album in albums:
        albums_clean[album['id']] = {
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

    albums_clean = sorted(albums_clean.values(), key=lambda x: x['date'])

    return albums_clean


def reduce(albums):
    """Reduce songs"""
    reduced = []
    nameset = set([s['name'] for s in [song for album in albums for song in album['tracks']]])

    for album in albums:
        if album['type'] == 'album':
            reduced.extend(album['tracks'])
            albums.remove(album)

    for album in sorted(albums, key=lambda x: 1 if x['type'] == 'EP' else 2):
        if album['tracks'][0]['name'] in [song['name'] for song in reduced]:
            pos = [song['name'] for song in reduced].index(album['tracks'][0]['name'])
            reduced.pop(pos)
            for song in album['tracks']:
                reduced.insert(pos, song)
                pos += 1
        else:
            pos = [i for i, song in enumerate(reduced) if song['date'] > album['date']]
            if pos:
                pos = pos[0]
                for song in album['tracks']:
                    reduced.insert(pos, song)
                    pos += 1
            else:
                reduced.extend(album['tracks'])

    for song in reduced:
        for s in reduced:
            if song['name'] == s['name'] and song != s:
                reduced.remove(s)

    assert len(reduced) == len(nameset), 'Songs were lost in the process!'

    return reduced


def pretty_print(songs):
    """Pretty print"""
    for song in songs:
        print(f'{song["name"]} - {song["album"]}')


def add_to_playlist(spotify, songs):
    """Add songs to playlist"""
    print(f'Adding {len(songs)} songs...')
    songs_split = [songs[i:i + 100] for i in range(0, len(songs), 100)]
    for songs in songs_split:
        spotify.playlist_add_items(
            playlist_id=os.getenv('RINJI_TEMP_PLAYLIST_ID'),
            items=[song['id'] for song in songs]
        )


def main():
    """Main function"""
    spotify = connect()
    check_for_listened(spotify)
    artist_id = get_artist_id(spotify)
    albums = get_songs(spotify, artist_id)
    songs = reduce(albums)
    add_to_playlist(spotify, songs)


if __name__ == '__main__':
    load_dotenv()
    main()
    print('Done!')
