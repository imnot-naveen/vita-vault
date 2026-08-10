import json
import re
import os

IN_PATH = "data/clean/all_docs.jsonl"
OUT_PATH = "data/chunks/chunks.jsonl"

FIRMWARE_RE = re.compile(r"\b3\.\d{2}\b")
ERROR_RE = re.compile(r"\bC\d-\d{5}-\d\b|\b0x[0-9A-Fa-f]{6,8}\b")
HARDWARE_TERMS = ["PCH-1000", "PCH-1100", "PCH-2000", "SD2Vita", "PSVSD", "MicroSD adapter"]
PLUGIN_TERMS = ["YAMT", "NoNpDrm", "StorageMgr", "AutoPlugin", "Adrenaline", "VitaShell",
                "PKGj", "VitaDeploy", "HENkaku", "molecularShell", "rePatch"]

def extract_tags(text):
    tags = {}
    fw = FIRMWARE_RE.findall(text)
    if fw:
        tags["firmware"] = fw[0]
    err = ERROR_RE.findall(text)
    if err:
        tags["error_code"] = err[0]
    hw = [h for h in HARDWARE_TERMS if h.lower() in text.lower()]
    if hw:
        tags["hardware"] = hw[0]
    pl = [p for p in PLUGIN_TERMS if p.lower() in text.lower()]
    if pl:
        tags["plugin"] = pl[0]
    return tags

def chunk_text(text, max_words=400, overlap=50):
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i:i + max_words]
        chunks.append(" ".join(chunk_words))
        if i + max_words >= len(words):
            break
        i += max_words - overlap  # keep some overlap so context isn't cut mid-idea
    return chunks

def run():
    os.makedirs("data/chunks", exist_ok=True)
    count = 0
    with open(IN_PATH, encoding="utf-8") as fin, open(OUT_PATH, "w", encoding="utf-8") as fout:
        for line in fin:
            doc = json.loads(line)
            pieces = chunk_text(doc["body"])
            for idx, piece in enumerate(pieces):
                tags = extract_tags(piece)
                record = {
                    "chunk_id": f"{doc['id']}_c{idx}",
                    "doc_id": doc["id"],
                    "source": doc["source"],
                    "title": doc["title"],
                    "url": doc["url"],
                    "date": doc.get("date"),
                    "chunk": piece,
                    **tags,
                }
                fout.write(json.dumps(record) + "\n")
                count += 1
    print(f"Wrote {count} chunks to {OUT_PATH}")

if __name__ == "__main__":
    run()