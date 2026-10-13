import pdfplumber
import re
import json
import glob
from pathlib import Path
from tohutil import write_a_json

# parse the pdf into its chapter & exercise structures
# save as json


# skip unwanted pdf items
def cleanup_lines(text):
    output = []
    for raw in text.splitlines():

        #whitespace
        s = " ".join(raw.split()).strip()
        if not s:
            continue

        #booktitle
        if s == "Skynjun sérhljóða og samhljóða":
            continue

        #pagenum
        if re.fullmatch(r"\d+", s):
            continue

        #xnote
        if s.startswith("1 V er skammstöfun"):
            continue

        output.append(s)
    return output


# parse 2 colum IPA headers for x marks
def parse_header_cols(line):
    line_items = re.findall(r"\[([^\]]+)\]", line)
    if len(line_items) != 2: # not this linetype
        return None

    target_sounds = []
    for sound in line_items:
        # repair minor irregular format
        sound = re.sub(r"\s+", "", sound)
        sound = sound.replace("(:)", "")
        sound = sound.replace(":", "")
        if sound == "I":
            sound = "ɪ"
        target_sounds.append(sound)

    return {
        "target_sounds": target_sounds,
        "length": "langt" if any( x in line for x in (":","(:)")) else "stutt",
        "raw": line_items,
    }



# parse student exercises, p1-46
def parse_exercises(textar):

    kaflar = []
    this_k = None
    this_æ = None
    this_ææ = None

    for síða in textar:
        for line in cleanup_lines(síða):

            # is this a new chapter? it says kafli
            chh = re.match( r"^(\d+)\.\s*kafli(?:[.\s–-]+(.*))?$", line)
            if chh:
                chn = int(chh.group(1))
                cht = (chh.group(2) or "").strip()
                this_k = {
                    "number": chn,
                    "title": cht,
                    "description_lines": [],
                    "exercises": []
                }
                # add new chapter to db & open new exercises
                kaflar.append(this_k)
                this_æ = None
                this_ææ = None
                continue

            # is this a new exercise-set? it says æfing
            aef = re.match(r"^(\d+)\.\s*æfing:\s*(.*)$",line)
            if aef:
                aen = int(aef.group(1))
                aei = aef.group(2).strip()
               ################################## #if this_k is None:
                #    raise ValueError(
                #        f"Found exercise outside a chapter: {line}"
                #    ) # ---> ok, this didn't happen for the current pdf.
                this_æ = {
                    "number": aen,
                    "title": aei,
                    "sub_exercises": []
                }
                this_k["exercises"].append(
                    this_æ
                )
                this_ææ = None
                continue

            # is this a new sub-exercise set? the column-header-parser returns it
            header = parse_header_cols(line)
            if header is not None and this_æ is not None:
                this_ææ = {
                    "length": header["length"],
                    "target_sounds": header["target_sounds"],
                    "words": []
                }
                this_æ["sub_exercises"].append(this_ææ)
                continue

            # if we already a current chapter but dont have an exercise open yet
            #   the current place must be in a chapter description
            if (this_k is not None and this_æ is None):
                this_k["description_lines"].append(line)
                continue

            # if we get here then the line is a single word's line
            #  only info wanted from this half of the book is the blank-printed wordform
            if this_ææ is not None and "__" in line:
                first_token = line.split()[0]
                this_ææ["words"].append({
                    "blank": first_token
                })

    for kafli in kaflar:
        kafli["summary"] = " ".join(kafli.pop("description_lines")).strip()
    return kaflar


#parse answer key info
def parse_key(textar):

    kaflar = []
    this_k = None
    this_æ = None
    this_ææ = None

    for síða in textar:
       for line in cleanup_lines(síða):

            # is this a new chapter? it says kafli
            chh = re.match(r"^(\d+)\.\s*kafli\s*[–-]\s*svör$",line)
            if chh:
                chn = int(chh.group(1))
                this_k = {
                    "number": chn,
                    "exercises": []
                }
                kaflar.append(this_k)
                this_æ = None
                this_ææ = None
                continue

            # new exercise-set? says æfing
            aef = re.match(r"^(\d+)\.\s*æfing:\s*(.*)$",line)
            if aef:
                aen = int(aef.group(1))
                aei = aef.group(2).strip()
                this_æ = {
                    "number": aen,
                    "title": aei,
                    "sub_exercises": []
                }
                this_k["exercises"].append(this_æ)
                this_ææ = None
                continue


            # subset column header?
            header = parse_header_cols(line)
            if header is not None and this_æ is not None:
                this_ææ = {
                    "length": header["length"],
                    "target_sounds": header["target_sounds"],
                    "rows": []
                }
                this_æ["sub_exercises"].append(this_ææ)
                continue

            if this_ææ is None:
                continue
            tokens = line.split()
            if len(tokens) < 4:
                continue

            # if we get here it should be a row of answers for a single word
            word = tokens[0]
            final_word = tokens[-1] # identical to word, in the answer key
            soundcheck_cols = tokens[1:-1]
            finding_x = [i for i, token in enumerate(soundcheck_cols)
                if re.search(r"x", token, flags=re.IGNORECASE) ]
            #if len(finding_x) != 1:
            #    continue
            assert len(finding_x) == 1
            target_index = finding_x[0]
            if target_index not in (0, 1):
                raise ValueError(
                    f"Unexpected X position in answer row: {line}"
                )

            this_ææ["rows"].append({
                "word": word,
                "target_sound": this_ææ[
                    "target_sounds"
                ][target_index]
            })

    return kaflar



# so anyway basically none of the error casese here actually.... happen.... it turns out.
def validate_pdf(exercise_chapters,answer_chapters):
  if len(exercise_chapters) != len(answer_chapters):
    raise ValueError(f"{len(exercise_chapters)} ≠ {len(answer_chapters)}")

  for ex_chapter, ans_chapter in zip(exercise_chapters,answer_chapters):
    if ex_chapter["number"] != ans_chapter["number"]:
        raise ValueError("Kaflar: " f"{ex_chapter['number']} ≠ " f"{ans_chapter['number']}")
    if len(ex_chapter["exercises"]) != len(ans_chapter["exercises"]):
        raise ValueError(f"Æfingar, "f"{ex_chapter['number']}.kafli")

    for ex, ans in zip(ex_chapter["exercises"],ans_chapter["exercises"]):
        if ex["number"] != ans["number"]:
            raise ValueError(
                f"{ex_chapter['number']}.kafli, afing "
                f"{ex['number']} ≠ {ans['number']}"
            )
        if len(ex["sub_exercises"]) != 2:
            raise ValueError(
                f"fann ekki (bara) langar & stuttar útgáfur - "
                f"kafli {ex_chapter['number']}, "
                f"æfing {ex['number']}"
            )
        if len(ans["sub_exercises"]) != 2:
            raise ValueError(
                f"fann ekki (bara) langar & stuttar útgáfur - "
                f"kafli {ans_chapter['number']}, "
                f"æfing {ans['number']}, svör"
            )

        for ex_sub, ans_sub in zip(
            ex["sub_exercises"],
            ans["sub_exercises"]
        ):
            if len(ex_sub["words"]) != 6:
                raise ValueError(
                    f"Það voru ekki (bara) 6 orð: "
                    f"kafli {ex_chapter['number']}, "
                    f"æfing {ex['number']}, "
                    f"{ex_sub['length']}; "
                    f"fann {len(ex_sub['words'])} orð"
                )
            if len(ans_sub["rows"]) != 6:
                raise ValueError(
                    f"Það voru ekki (bara) 6 svör:"
                    f"kafli {ans_chapter['number']}, "
                    f"æfing {ans['number']}, "
                    f"{ans_sub['length']}; "
                    f"fann {len(ans_sub['rows'])} orð"
                )
            # Target sounds should agree.
            if ex_sub["target_sounds"] != ans_sub[
                "target_sounds"
            ]:
                raise ValueError(
                    f"eitthvað fór vitlaust"
                    f"kafli {ex_chapter['number']}, "
                    f"æfing {ex['number']}, "
                    f"{ex_sub['length']}"
                )

  print("allt í lagi")


# combine info from the half with the exercises,
# and the half with the answers
def merge_bookhalfs(exercise_chapters, answer_chapters):
  merged_chapters = []
  for ex_chapter, ans_chapter in zip(exercise_chapters,answer_chapters):
      merged_exercises = []
      for ex, ans in zip(ex_chapter["exercises"],ans_chapter["exercises"]):
          merged_sub_exercises = []
          for ex_sub, ans_sub in zip(ex["sub_exercises"],ans["sub_exercises"]):
              merged_words = []
              for blank_row, answer_row in zip(ex_sub["words"],ans_sub["rows"]):
                  merged_words.append({
                    "spurning": blank_row["blank"],
                    "orð": answer_row["word"],
                    "svar": answer_row["target_sound"]
                    })
              merged_sub_exercises.append({
                "lengd": ex_sub["length"],
                "hljóð": ex_sub["target_sounds"],
                "dæmi": merged_words
                })
          merged_exercises.append({
            "n_æf": ex["number"],
            "hljóðskynjun": ex["title"],
            "æfingar": merged_sub_exercises
            })
      merged_chapters.append({
        "n_kaf": ex_chapter["number"],
        "nafn": ex_chapter["title"],
        "lýsing": ex_chapter["summary"],
        "kafli": merged_exercises
        })

  return merged_chapters


def extract_pdf(pdf_path, json_path):
  with pdfplumber.open(pdf_path) as pdf:
    if len(pdf.pages) != 87:
        print(
            f"WExpected 87 pages, found {len(pdf.pages)}, did you upload the right book?"
        )
    page_texts = [page.extract_text() or "" for page in pdf.pages]

  exercise_chapters = parse_exercises(page_texts[:46])
  answer_chapters = parse_key(page_texts[46:])
  validate_pdf(exercise_chapters,answer_chapters)

  all_exercises = merge_bookhalfs(exercise_chapters,answer_chapters)
  jdict = {"bók": all_exercises}
  bokp = write_a_json(jdict, json_path)
  return jdict, bokp



if __name__ == "__main__":

    JSON_PATH = "/content/skynjun_serhljoda_samhljoda__HF.json"

    PDF_PATH = glob.glob("/content/Skynjun*.pdf")

    if PDF_PATH:
        PDF_PATH = Path(PDF_PATH[0])
        print("Bók", PDF_PATH)
    else:
        raise Exception("Hladdu upp Skynjun sérhljóða og samhljóða kaflar 1-10.pdf")
    _, jp = extract_pdf(PDF_PATH, JSON_PATH)
    print('saved json to ', jp)
