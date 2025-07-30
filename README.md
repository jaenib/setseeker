# setseeker

fileshazzer.py - Takes DJ sets (or any MP3) splitting them into shazamable segments. Returns a list of timestamped track IDs in plain text.

seekspawner.py - Seeks and downloads the tracks on soulseek using slsk-batchdl command line tool. Soulseek login required.



# setup

execute setup.sh from command line: 

<code> chmod +x setup.sh </code> then <code> ./setup.sh </code>

<br>what it does:

&nbsp; -- creates a new virtual environment with a fresh python installation that is independent from the main environment

&nbsp; -- installs all required python modules there

&nbsp; -- creates the folders

&nbsp; -- there is prompt to enter your soulseek credentials so it can store them encrypted, so the main module can later use them to access soulseek

this step is skippable and you can store them later or enter them every time. 





# run

Put MP3s into 'sets' folder.


<run all:

&nbsp; - execute launcher.sh from command line as: <code> chmod +x launcher.sh </code> and <code> ./launcher.sh </code> <br>

<br>activate that virtual environment with 

<code> source shaz_venv/bin/activate  </code>


<br>altternatively run fileshazzer.py for trackID only, results will be in the 'tracklists' folder.

&nbsp; - If the code seems stuck be patient, its shazam api limiting calls, it will continue.<br>

&nbsp;  Bad results? 

&nbsp;&nbsp; - find segment_length variable at the top of fileshazzer.py and change it.
  
&nbsp;&nbsp; - Default 30s go up if your tracklists get more than 4 instances of the same id / things are taking too long.
   

<br>or run <code>python3.11 seekspawner.py </code> for download only

&nbsp; - needs a previous run of fileshazzer that yielded a tracklist or a manually added tracklist.txt (that matches the formatting below)

  

# example  tracklist result

Final Tracklist:<br>
[00:01:00] Umek - Center of Gravity<br>
[00:13:30] Sade - Like Tattoo<br>
[00:21:00] Zimmie Gix - Absolute Chill<br>
[00:21:30] Andrea Frisina & Irregular Synth - Dub City<br>
[00:22:00] Alan Fitzpatrick - Brian's Proper Dun One<br>
[00:23:30] R.A.W. - Unbe (Erick 'More' Mix)<br>
[00:24:00] Terrace - Magic O<br>
...etc

