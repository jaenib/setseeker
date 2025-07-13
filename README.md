# setseeker

fileshazzer.py - Takes DJ sets (or any MP3) splitting them into shazamable segments. Returns a list of timestamped track IDs in plain text.

seekspawner.py - Seeks and downloads the tracks on soulseek using slsk-batchdl command line tool.



# setup

execute setup.sh from command line as: <code> ./setup.sh </code>


# run

Put MP3s into 'sets' folder.

run all:

  execute launcher.sh from command line as: <code> ./launcher.sh </code>


or run fileshazzer.py to process them, results will be in the 'tracklists' folder.

  If the code seems stuck be patient, its shazam api limiting calls, it will continue.

  Bad results? 

   find segment_length variable at the top of fileshazzer.py and change it.
  
   Default 30s go up if your set consists of longer tracks / your tracklists get more than 4 instances of the same id / things are taking too long.


# example result

Final Tracklist:<br>
[00:01:00] Umek - Center of Gravity<br>
[00:13:30] Sade - Like Tattoo<br>
[00:21:00] Zimmie Gix - Absolute Chill<br>
[00:21:30] Andrea Frisina & Irregular Synth - Dub City<br>
[00:22:00] Alan Fitzpatrick - Brian's Proper Dun One<br>
[00:23:30] R.A.W. - Unbe (Erick 'More' Mix)<br>
[00:24:00] Terrace - Magic O<br>
[00:25:00] Folamour - Ça Va Aller<br>
[00:25:30] Folamour - Ça Va Aller<br>
[00:26:00] Bellini - Samba de Janeiro (Vanity Frontroom Remix)<br>
[00:33:30] Topic & A7S - Breaking Me (HUGEL Remix)<br>
[00:37:00] Distant Sun - Machine lernt<br>
[00:37:30] Armin van Buuren - Communication Part 3<br>
[00:38:00] Distant Sun - Machine lernt<br>
[00:38:30] New Layer - Nocturno (feat. Javiera Gonzalez)<br>
[00:42:30] DEADWALKMAN - Rhythm 11<br>
[00:46:00] Armin van Buuren - Shivers (feat. Susana) [Rising Star Mix]<br>
[01:00:00] Da Hool - Meet Her at the Loveparade<br>
[01:01:30] Rank 1 - Airwave (Radio Vocal Edit)<br>
[01:04:00] ATB - 9 P.M. (Till I Come)<br>
[01:04:30] Rank 1 - Airwave (Radio Vocal Edit)<br>
[01:05:00] Rank 1 - Airwave (Radio Vocal Edit)<br>
[01:05:30] Industrial Sound - Melodic Dreamscape, Pt.6<br>
[01:06:00] The Roc Project - Never (Filterheadz Love Tina Remix)<br>
[01:06:30] The Roc Project - Never (Filterheadz Love Tina Remix)<br>
[01:07:00] The Roc Project - Never (Filterheadz Love Tina Remix)<br>
[01:07:30] The Roc Project - Never (Filterheadz Love Tina Remix)<br>
[01:08:00] The Roc Project - Never (Filterheadz Love Tina Remix)<br>
[01:08:30] Nicole Moudaber - Rise Up (feat. London Community Gospel Choir) [Alev Tav Extended Mix]<br>
[01:09:00] The Roc Project - Never (Filterheadz Love Tina Remix)<br>
[01:09:30] The Roc Project - Never (Filterheadz Love Tina Remix)<br>
[01:11:00] Alex Dolby - Sintesi<br>
[01:12:30] The Roc Project - Never (Filterheadz Love Tina Remix)<br>
[01:13:00] The Roc Project - Never (Filterheadz Love Tina Remix)<br>
[01:14:00] Industrial Sound - Melodic Dreamscape, Pt.6


