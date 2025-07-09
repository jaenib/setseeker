# setshazzer

Takes DJ sets and returns track IDs, possible future function fetching the tracks.



# setup

Run fileshazzer.py initially to setup the folders until it tells you to add MP3 files to the 'sets' folder.

Alternatively create a folder called 'sets' in the same folder where you put fileshazzer.py.


# run

Put MP3s into 'sets' folder.

  Optionally find segment_length variable at the top of fileshazzer.py and change it.
  
  Default 30s go up if your set consists of longer tracks / your tracklists get more than 4 instances of the same id / things are taking too long.

Run fileshazzer.py again to process them, results will be in the 'tracklists' folder.

  If the code seems stuck be patient, its shazam api limiting calls, it will continue.


