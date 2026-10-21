import whisperx
import difflib
import re, glob, json, os
from pathlib import Path

from tohutil import write_a_json, standardise_audio, load_falign_models


# force alignment for the 6 chapters audio files -
#  tries some heuristics to repair data when possible
# saves the alignment data in json


# there's one audio file per chapter
# get a flattened copy of metadata for each word in it
def get_transcript_items(book, chapter):
	items = []
	for kafli in book["bók"]:
		if kafli["n_kaf"] != chapter:
			continue
		for hs in kafli["kafli"]:
			hs_id = hs["hljóðskynjun"]
			for læf in hs["æfingar"]:
				lengd_id = læf["lengd"]
				sounds = læf["hljóð"]  # e.g. ["a", "i"]
				for i, dæmi in enumerate(læf["dæmi"]):
					item = dict(dæmi)
					item["hljóðskynjun"] = hs_id
					item["lengd"] = lengd_id
					item["hljóð"] = sounds
					item["n_kaf"] = kafli["n_kaf"]
					item["n_æf"] = hs["n_æf"]
					item["n_dæm"] = i + 1 #index from 1 bc evertyhing else already does
					item["_ref"] = dæmi
					items.append(item)
	if items:
		return items
	else:
		raise ValueError(f"Vantar kafli {chapter}")


# sometimes asr squishes 2 words into 1, unsquish before forced alignment
def asr_matcher(token, gold_pieces, min_avg_ratio = 0.55):
	n, k = len(token), len(gold_pieces)
	if k == 0 or n == 0:
		return None
	NEG = -1.0
	# dp[i][j] = (score, split_start_positions) best splitting token[:i]
	# into j pieces matching gold_pieces[:j]
	dp = [[(NEG, None)] * (k + 1) for _ in range(n + 1)]
	dp[0][0] = (0.0, [])
	for i in range(1, n + 1):
		for j in range(1, min(k, i) + 1):
			best = (NEG, None)
			for p in range(j - 1, i):
				prev_score, prev_splits = dp[p][j - 1]
				if prev_score < 0:
					continue
				piece = token[p:i]
				ratio = difflib.SequenceMatcher(None, piece, gold_pieces[j - 1]).ratio()
				score = prev_score + ratio
				if score > best[0]:
					best = (score, prev_splits + [p])
			dp[i][j] = best
	final_score, splits = dp[n][k]
	if splits is None:
		return None
	avg = final_score / k
	if avg < min_avg_ratio:
		return None
	bounds = splits + [n]
	pieces = [token[bounds[m]:bounds[m + 1]] for m in range(k)]
	return pieces, avg



_ICE_CHARS = "a-záðéíóúýþæö"
_clean = lambda w: re.sub(f"[^{_ICE_CHARS}]", "", w.lower())

def unsquish_asr(asr_segments, gold_words, min_avg_ratio = 0.55,max_extra_words = 3):
	gold_norm = [_clean(w) for w in gold_words]

	flat = []
	seg_word_lists = []
	for si, seg in enumerate(asr_segments):
		words = seg["text"].split()
		seg_word_lists.append(words)
		for wi, w in enumerate(words):
			flat.append({"text": w, "clean": _clean(w), "seg": si, "pos": wi})

	flat_clean = [f["clean"] for f in flat]
	sm = difflib.SequenceMatcher(None, flat_clean, gold_norm, autojunk=False)

	repairs = {}
	n_repairs = 0
	for tag, i1, i2, j1, j2 in sm.get_opcodes():
		if tag != "replace" or (i2 - i1) == (j2 - j1):
			continue

		block = flat[i1:i2]
		gold_block = gold_norm[j1:j2]
		gold_orig = gold_words[j1:j2]
		k = len(gold_block)
		n = len(block)

		best = None  # (avg, sub_list)
		for start in range(n):
			max_len = min(n - start, k + max_extra_words)
			for length in range(1, max_len + 1):
				sub = block[start:start + length]
				if len({f["seg"] for f in sub}) != 1:
					continue  # window must sit inside a single whisper segment
				concat = "".join(f["clean"] for f in sub)
				split = asr_matcher(concat, gold_block, min_avg_ratio=0.0)
				if split is None:
					continue
				_, avg = split
				if best is None or avg > best[0]:
					best = (avg, sub)

		if best is None:
			continue
		avg, sub = best
		if avg < min_avg_ratio:
			print(f"[segmentation-repair] REJECTED best-window avg={avg:.2f}: "
				  f"'{' '.join(f['text'] for f in sub)}' vs {gold_orig}")
			continue

		seg_idx = sub[0]["seg"]
		start_pos, end_pos = sub[0]["pos"], sub[-1]["pos"] + 1
		repairs.setdefault(seg_idx, []).append((start_pos, end_pos, gold_orig))
		n_repairs += 1
		print(f"[segmentation-repair] '{' '.join(f['text'] for f in sub)}' "
			  f"-> '{' '.join(gold_orig)}' (avg char-similarity {avg:.2f})")

	if n_repairs:
		print(f"[segmentation-repair] applied {n_repairs} fix(es) before forced alignment")

	new_segments = []
	for si, seg in enumerate(asr_segments):
		words = seg_word_lists[si]
		for start_pos, end_pos, replacement in sorted(
			repairs.get(si, []), key=lambda x: x[0], reverse=True
		):
			words[start_pos:end_pos] = replacement
		new_seg = dict(seg)
		new_seg["text"] = " ".join(words)
		new_segments.append(new_seg)

	return new_segments


def align_chapter(audio_path,book_contents,falign_models,new_audio_parent="skynjun_shsh"):
	whisper_model, align_model, align_meta, device = falign_models
	wav_path = standardise_audio(audio_path)
	fuzzy_threshold=0.5

	# gets chapter # 1-10 for the patterns in current set of files...
	#chapter = int(re.search(r"skynjun\s+(\d+)", audio_path, re.I).group(1)) #original filenames
	chapter = int(re.search(r"(\d+)_kafli\.wav$", audio_path).group(1)) # renamed 16khz mono wavs

	transcript_tasks = get_transcript_items(book_contents,chapter)
	transcript_words = [d["orð"] for d in transcript_tasks]
	transcript_norm = [_clean(w) for w in transcript_words]

	try:
		asr = whisper_model.transcribe(wav_path, language="is")
		asr["segments"] = unsquish_asr(asr["segments"], transcript_words)
		aligned = whisperx.align(asr["segments"], align_model, align_meta, wav_path, device)
	finally:
		os.remove(wav_path)

	asr_words = aligned["word_segments"]  #{"word","start","end"}
	asr_norm = [_clean(w["word"]) for w in asr_words]


	# correspond the ordered exercises to the full asr output
	sm = difflib.SequenceMatcher(None, asr_norm, transcript_norm, autojunk=False)
	timings = [None] * len(transcript_words)   # {"start","end"} or None
	exact = [None] * len(transcript_words)	 # True / False / None

	# try to match and fuzzy/interpolate
	for tag, i1, i2, j1, j2 in sm.get_opcodes():
		if tag == "equal":
			for k in range(i2 - i1):
				w = asr_words[i1 + k]
				timings[j1 + k] = {"start": w["start"], "end": w["end"]}
				exact[j1 + k] = True
			continue

		# if something exists in book but not exact match found in asr...
		next_min = i1
		for j in range(j1, j2):
			gt_tok = transcript_norm[j]
			candidates = list(range(next_min, i2))
			best_idx, best_ratio = None, 0.0
			for c in candidates:
				r = difflib.SequenceMatcher(None, gt_tok, asr_norm[c]).ratio()
				if r > best_ratio:
					best_ratio, best_idx = r, c

			if best_idx is not None and best_ratio >= fuzzy_threshold:
				w = asr_words[best_idx]
				timings[j] = {"start": w["start"], "end": w["end"]}
				exact[j] = False
				next_min = best_idx + 1  # stay monotonic about it
				print(f"[near-match] chapter {chapter}: book word '{transcript_words[j]}' "
					  f"matched to ASR word '{asr_words[best_idx]['word'].strip()}' "
					  f"(similarity {best_ratio:.2f}) at {w['start']:.2f}-{w['end']:.2f}s")
			else:
				timings[j] = {"start": None, "end": None}
				exact[j] = None

	for j, task in enumerate(transcript_tasks):
		task["_ref"].update({
			"start": timings[j]["start"],
			"end": timings[j]["end"],
			"exact": exact[j],
			"original_target_sounds": task["hljóð"],
			"original_hljóðskynjun": task["hljóðskynjun"],
			"lengd": task["lengd"],
			"audio_path": str(Path(new_audio_parent) / Path(audio_path).name),
			"original_nkaf": task["n_kaf"],
			"original_næf": task["n_æf"],
			"original_ndæm": task["n_dæm"],
		})

	n_near = sum(1 for e in exact if e is False)
	n_missing = sum(1 for e in exact if e is None)
	if n_near or n_missing:
		print(f"[warn] chapter {chapter}: {n_near} near-matched, {n_missing} unmatched, "
			  f"out of {len(transcript_words)} words")

	return book_contents



if __name__ == "__main__":

	audios_paths= glob.glob("/content/*_kafli.[wW]*")
	book_json_path = "/content/skynjun_shsh__HF.json"
	align_json_path = "/content/skynjun_shsh_AlignDict__HF.json"

	fmodels = load_falign_models()
	with open(book_json_path, encoding="utf-8") as f:
		book_json = json.load(f)

	for af in audios_paths:
		align_chapter(af,book_json,fmodels)
	write_a_json(book_json,align_json_path)
