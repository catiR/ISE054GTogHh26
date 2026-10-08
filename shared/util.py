import io, base64
import numpy as np
import os
import re
import json
import glob
import random
import pdfplumber
import difflib
import subprocess
import tempfile
import librosa
import whisperx
import uuid
import librosa
import matplotlib.pyplot as plt
import ipywidgets as widgets
from pathlib import Path
from IPython.display import display, Audio, Javascript
from pydub import AudioSegment
from google.colab import output

# TODO

# shared whisper asr
# ctc forced alignment

# reasonable pitch tracking

# image displays -
# spectrograms, pitch/energy, word bounds drawn on

# colab audio player
# colab audio recorder (+ play-backer)
# or stop using colab because this seems genuinely awful
