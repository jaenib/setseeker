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


# example result

Final Tracklist:
[00:01:00] Umek - Center of Gravity<br>
[00:02:30] Steve Aoki - Double Helix<br>
[00:13:30] Sade - Like Tattoo<br>
[00:21:00] Zimmie Gix - Absolute Chill
[00:21:30] Andrea Frisina & Irregular Synth - Dub City
[00:22:00] Alan Fitzpatrick - Brian's Proper Dun One
[00:23:30] R.A.W. - Unbe (Erick 'More' Mix)
[00:24:00] Terrace - Magic O
[00:25:00] Folamour - Ça Va Aller
[00:25:30] Folamour - Ça Va Aller
[00:26:00] Bellini - Samba de Janeiro (Vanity Frontroom Remix)
[00:33:30] Topic & A7S - Breaking Me (HUGEL Remix)
[00:37:00] Distant Sun - Machine lernt
[00:37:30] Armin van Buuren - Communication Part 3
[00:38:00] Distant Sun - Machine lernt
[00:38:30] New Layer - Nocturno (feat. Javiera Gonzalez)
[00:42:30] DEADWALKMAN - Rhythm 11
[00:46:00] Armin van Buuren - Shivers (feat. Susana) [Rising Star Mix]
[01:00:00] Da Hool - Meet Her at the Loveparade
[01:01:30] Rank 1 - Airwave (Radio Vocal Edit)
[01:04:00] ATB - 9 P.M. (Till I Come)
[01:04:30] Rank 1 - Airwave (Radio Vocal Edit)
[01:05:00] Rank 1 - Airwave (Radio Vocal Edit)
[01:05:30] Industrial Sound - Melodic Dreamscape, Pt.6
[01:06:00] The Roc Project - Never (Filterheadz Love Tina Remix)
[01:06:30] The Roc Project - Never (Filterheadz Love Tina Remix)
[01:07:00] The Roc Project - Never (Filterheadz Love Tina Remix)
[01:07:30] The Roc Project - Never (Filterheadz Love Tina Remix)
[01:08:00] The Roc Project - Never (Filterheadz Love Tina Remix)
[01:08:30] Nicole Moudaber - Rise Up (feat. London Community Gospel Choir) [Alev Tav Extended Mix]
[01:09:00] The Roc Project - Never (Filterheadz Love Tina Remix)
[01:09:30] The Roc Project - Never (Filterheadz Love Tina Remix)
[01:11:00] Alex Dolby - Sintesi
[01:12:30] The Roc Project - Never (Filterheadz Love Tina Remix)
[01:13:00] The Roc Project - Never (Filterheadz Love Tina Remix)
[01:14:00] Industrial Sound - Melodic Dreamscape, Pt.6


