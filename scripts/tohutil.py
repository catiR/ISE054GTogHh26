import json
import subprocess
import tempfile


def write_a_json(jdict, outpath):
	with open(outpath,"w",encoding="utf-8") as handle:
		json.dump(jdict,handle,ensure_ascii=False,indent=2)
	return outpath


# a couple provided audios are WMA so
def standardise_audio(audio_path):
	tmp_path = tempfile.mktemp(suffix=".wav")
	cmd = [
		"ffmpeg", "-y", "-i", audio_path,
		"-ac", "1", "-ar", "16000",
		"-f", "wav", tmp_path,
		"-loglevel", "error",
	]
	subprocess.run(cmd, check=True)
	return tmp_path


# whisper for ASR, w2v2 for alignment to whisper's xcp
#  (will match it to the book transcript later)
def load_falign_models(whisper_model=None, align_model=None, device="cuda"):
	import whisperx # dont just import this anytime anyone imports utils
	whisper_spec = "language-and-voice-lab/whisper-large-icelandic-62640-steps-967h-ct2"
	ctc_spec = "language-and-voice-lab/wav2vec2-large-xlsr-53-icelandic-ep30-967h"
	ctype = "float16" if device == "cuda" else "int8"
	if whisper_model is None:
		whisper_model = whisperx.load_model(
			whisper_spec, device, language="is", compute_type=ctype
		)
	if align_model is None:
		align_model, align_meta = whisperx.load_align_model(
			language_code="is", device=device, model_name=ctc_spec
		)
	return [whisper_model, align_model, align_meta, device]



# TODO

# shared whisper asr
# ctc forced alignment

# reasonable pitch tracking

# image displays -
# spectrograms, pitch/energy, word bounds drawn on

# colab audio player
# colab audio recorder (+ play-backer)
# or stop using colab because this seems genuinely awful
