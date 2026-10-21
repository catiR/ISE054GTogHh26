### 1. `> python bookparse.py` (krefst "Skynjun sérhljóða og samhljóða kaflar 1-10.pdf") --> `skynjun_shsh__HF.json`

### 2. wma, 44,1khz wav -> 16khz mono wav: e.g. `ffmpeg -y -i Skynjun\ 9.wav -ac 1 -ar 16000 -f wav content/9_kafli.wav`

### 3. `> python bookalign.py` --> `skynjun_shsh_AlignDict__HF.json`

#### Note. Due to the specific forced alignment output as well as clear pauses between words in these recordings, large padding such as 0.5 seconds is recommended to add to these timestamps before segmenting audio into words.