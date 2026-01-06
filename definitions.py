from pathlib import Path

def load_definitions(path: str) -> dict[str, str]:
    """
    Load term→definition pairs from a tab-delimited file.
    Returns a dict with lowercase keys.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    out = {}
    for line in lines:
        if not line.strip():
            continue
        if "<TAB>" in line:
            term, definition = line.split("<TAB>", 1)
        elif "\t" in line:
            term, definition = line.split("\t", 1)
        else:
            continue  # skip malformed lines
        out[term.strip().lower()] = definition.strip()
    return out

# Load both definition files
WORD_DEFS = load_definitions("definitions.txt")
PHRASE_DEFS = load_definitions("phrase_definitions.txt")
