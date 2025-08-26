from sclib import SoundcloudAPI, Track, Playlist

soundcloud_url = ""

def main(soundcloud_url):
    # do not pass a Soundcloud client ID that did not come from this library, but you can save a client_id that this lib found and reuse it
    api = SoundcloudAPI()  
    track = api.resolve(soundcloud_url)
    print(f"Attempting to download: {track.title}, Artist: {track.artist}"
)

    assert type(track) is Track

    filename = f'sets/{track.artist} - {track.title}.mp3'

    with open(filename, 'wb+') as file:
        track.write_mp3_to(file)
        print(f"Downloaded: {filename}")

if __name__ == "__main__":
    main(soundcloud_url)
