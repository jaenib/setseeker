import os
import subprocess
import asyncio
from shazamio import Shazam

'''
source shaz_venv/bin/activate
python3.11 fileshazzer.py
'''

# Define directories
INPUT_DIR = "sets"  # Folder where your DJ sets are stored
SEGMENTS_DIR = "segments"
OUT_DIR = "tracklists"

# Ensure the segments directory exists
os.makedirs(SEGMENTS_DIR, exist_ok=True)

# Function to split audio into segments
def split_audio(input_file, segment_length):
    print(f"Splitting {input_file} into {segment_length}-second chunks...")
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    segment_pattern = os.path.join(SEGMENTS_DIR, f"{base_name}_%03d.mp3")

    ''' command = f"ffmpeg -i \"{input_file}\" -f segment -segment_time {segment_length} -c copy \"{segment_pattern}\"" '''
    ''' command = f'ffmpeg -i "{input_file}" -f segment -segment_time {segment_length} -ar 44100 -ac 2 -b:a 192k "{segment_pattern}"' '''

    ''' command = f"ffmpeg -i \"{input_file}\" -f segment -segment_time {segment_length}  -segment_format mp3 -codec:a libmp3lame -b:a 192k -ar 44100 -ac 2 \"{segment_pattern}\"" '''
    command = f"ffmpeg -i \"{input_file}\" -f segment -segment_time {segment_length} -segment_format mp3 -reset_timestamps 1 -map 0 -codec copy \"{segment_pattern}\""

    subprocess.run(command, shell=True, check=True)

# Function to recognize tracks with ShazamIO
async def recognize_tracks(segment_length):
    print("Recognizing tracks with Shazam...")
    shazam = Shazam()
    track_list = []

    for file in sorted(os.listdir(SEGMENTS_DIR)):
        if file.endswith(".mp3"):
            file_path = os.path.join(SEGMENTS_DIR, file)

            # Extract timestamp from filename (assuming _XXX.mp3 format)
            segment_index = int(file.split("_")[-1].split(".")[0])
            timestamp_seconds = segment_index * segment_length
            timestamp = f"{timestamp_seconds // 3600:02}:{(timestamp_seconds % 3600) // 60:02}:{timestamp_seconds % 60:02}"

            try:
                result = await shazam.recognize(file_path)
                if "track" in result:
                    title = result["track"]["title"]
                    artist = result["track"]["subtitle"]
                    track_list.append(f"[{timestamp}] {artist} - {title}")
                    print(f"Recognized: [{timestamp}] {artist} - {title}")
                else:
                    print(f"[{timestamp}] No match found for {file}")
            except Exception as e:
                print(f"Error processing {file}: {e}")

    return track_list

# Main function to process all sets in a folder4
async def main():
    sets = [f for f in os.listdir(INPUT_DIR) if f.endswith(".mp3")]
    segment_length = 30
    ''' segment_interval = 60 '''

    if not sets:
        print("No MP3 files found in the 'sets' folder.")
        return

    for set_file in sets:
        for file in os.listdir(SEGMENTS_DIR):
            if file.endswith(".mp3"):
                os.remove(os.path.join(SEGMENTS_DIR, file))

        input_path = os.path.join(INPUT_DIR, set_file)
        split_audio(input_path, segment_length)

        tracks = await recognize_tracks(segment_length)

        base_name = os.path.splitext(set_file)[0]
        output_dir = os.path.join(OUT_DIR, base_name)
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"{base_name}_tracklist_{segment_length}s.txt")

        with open(output_file, "w") as f:
            f.write("Final Tracklist:\n")
            for track in tracks:
                f.write(track + "\n")

        # Move the original mp3 file to the output directory
        os.rename(os.path.join(INPUT_DIR, set_file), os.path.join(output_dir, set_file))

    print("\nFinal Tracklist:")
    for track in tracks:
        print(track)

# Run the script
if __name__ == "__main__":
    asyncio.run(main())