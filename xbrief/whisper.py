"""Whisper large-v3 (MLX) on one audio file, run as its own process so MLX frees its memory when it ends:
`python -m xbrief.whisper <audio> <out.json>`. The language is Whisper's own guess. The weights are the Hugging
Face cache's, shared with the Telegram voice notes."""

import json
import sys

MODEL = "mlx-community/whisper-large-v3-mlx"


def main(audio: str, out: str) -> None:
    import mlx_whisper

    r = mlx_whisper.transcribe(audio, path_or_hf_repo=MODEL, condition_on_previous_text=False)
    doc = {"language": r.get("language"), "text": " ".join(r["text"].split()),
           "segments": [[round(s["start"], 1), s["text"].strip()] for s in r["segments"]]}
    with open(out, "w") as f:
        json.dump(doc, f, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
