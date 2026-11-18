"""Zafar Hasan's survey of Delhi's monuments (1916-1922), as a source this app can read.

Maulvi Zafar Hasan and the Archaeological Survey walked Delhi and wrote down every monument they
found, filed under the lane it stood in: more than 1,200 of them across four volumes, the famous and
the forgotten alike. For most of Delhi's older lanes it is the only description that was ever
written, which makes it the single richest thing we can give this app.

It is out of copyright and scanned on the Internet Archive, so we read its OCR text, split it back
into entries, and place each entry at its lane.

What this is honest about: the book gives lanes, not coordinates. An entry is placed where its lane
geocodes to, so it is street-level evidence, never a pin on a building. Entries carry the lane name
so the model can say "in Kucha Chelan" rather than implying it stands on this exact spot.
"""

import asyncio
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Optional

import httpx

logger = logging.getLogger(__name__)

UA = "NVM-app/1.0 (street history lookup; contact: dev@nvm.app)"
ARCHIVE = "https://archive.org"

# Volume 1 is the walled city, so its lanes may only be placed inside it. Without this, "Lal Kuan"
# matched the other Lal Kuan near Badarpur and "Kali Masjid" one in south Delhi, 15 km off.
WALLED_CITY = "77.2050,28.6300,77.2500,28.6720"

VOLUMES: dict[int, dict] = {
    1: {"archive_id": "in.gov.ignca.22805", "area": "Shahjahanabad", "year": 1916, "viewbox": WALLED_CITY},
    2: {"archive_id": "in.gov.ignca.12006", "area": "Delhi Zail", "year": 1919},
    3: {"archive_id": "in.ernet.dli.2015.69531", "area": "Mahrauli Zail", "year": 1922},
    4: {"archive_id": "in.ernet.dli.2015.69532", "area": "Outer zails", "year": 1922},
}
TITLE = "Zafar Hasan, List of Muhammadan and Hindu Monuments"

# Running headers, column titles and page furniture that look like lane headings but are not.
_NOISE = re.compile(
    r"^(?:[IVXLC\-. ]+|\d+|.*\bL?IST\s*O[FP]\b.*|.*MON[UOIEXTSKC]{3,}.*|REFERENCE|TRANSLATION|PLATE.*|INDEX|"
    r"CONTENTS|APPENDIX|PREFACE|INTRODUCTION|NOTE|NOTES|AND|THE|DELHI PROVINCE|CHAPTER.*|ERRATA|.*CATALOGUE.*|[A-Z]\s+[IVXL]{1,5})$",  # last: "W III", a stray letter and a page numeral
    re.I,
)
_HEADING = re.compile(r"^[A-Z][A-Z0-9'’‘\-.,& ]{2,45}$")

# Every field opens with a one- or two-character marker in brackets: (a) name ... (e) date ... (j)
# remarks ... (k) references. The scan misreads them freely - (b) as (4) or (6), (h) as (A), (a) and
# (e) both as («) - so fields are found by position as much as by letter.
_MARK = re.compile(r"\(\s*[^\s()]{1,2}\s*\)")
_A_MARK = re.compile(r"\(\s*[ao0@«ö]\s*\)")
_J_LETTERS = set("j;iJ")
_PERIOD_WORDS = re.compile(  # deliberately case-sensitive on A.D./A.H.: "Muhammad" must not read as a date
    r"mughal|pathan|afghan|tughl|lodi|sayyid|khalji|turki|suri\b|hindu|british|modern|unknown|century|\bA\.\s?D\b|\bA\.\s?H\b|\b1[0-9]{3}\b",
    re.I,
)
_JUNK_NAME = re.compile(r"^(?:unnamed|none|do|ditto|nil|n/?a|[^a-z]*)$", re.I)

# Lane names the scan garbles in predictable ways, and a few the modern map knows by another name.
_HEADING_FIXES = [
    (re.compile(r"(?<=[A-Z])1(?=[A-Z]|\b)"), "I"),   # HAVEL1 -> HAVELI
    (re.compile(r"II(?=[AEOU])"), "H"),              # KIIAN -> KHAN, CHIIATTA -> CHHATTA
    (re.compile(r"(?<=[A-Z])0(?=[A-Z])"), "O"),
]
# Names too common or too vague to place with confidence: "Ridge" is miles of hill, and there is more
# than one Muhammadpur. They stay out rather than land somewhere plausible but wrong.
UNPLACEABLE = {"RIDGE", "MUHAMMADPUR", "PARADE GROUND"}

LOCALITY_ALIASES = {
    "FORT": "Red Fort",
    "CHANDNI CHAUK": "Chandni Chowk",
    "DARIBA-KALAN": "Dariba Kalan",
    "BAZAR FATHPURI": "Fatehpuri",
    "BAZAR KHARI BAOLI": "Khari Baoli",
    "BAZAR LAL KUWAN": "Lal Kuan",
    "BAZAR SIRKI WALAN": "Sirkiwalan",
    "KINARI BAZAR": "Kinari Bazar",
    "KINABI BAZAR": "Kinari Bazar",
    "TXJGHLAQABAD": "Tughlakabad",
    "TUGHLAQABAD": "Tughlakabad",
    "BAS A I DARAPUE": "Basai Darapur",
    "QADAJW SHARIF": "Qadam Sharif",
    "CHIRAQH DELHI": "Chirag Delhi",
    "MAHRAULI": "Mehrauli",
    "MUBARAKPUR KOTLA": "Kotla Mubarakpur",
    "LADHA SARAI": "Lado Sarai",
    "PAHARGANJ": "Paharganj",
    # Lanes the 1916-22 survey names one way and today's map another. Each was checked by hand: the
    # map's match is the same lane or village, in the right part of Delhi, not just a similar name.
    "FAIZ BAZAR": "Netaji Subhash Marg",
    "MUHALLA CHITLI QABR": "Chitli Qabar",
    "MUHALLA SUIWALON-KA-HAUZ": "Suiwalan",
    "MUHALLA QABRUSTAN": "Mohalla Qabristan",
    "AJMER GATE": "Ajmeri Gate",
    "BAZAR NAYABANS": "Naya Bans",
    "MUHALLA BALLI MARAN": "Ballimaran",
    "KATRA NIL": "Katra Neel",
    "BAZAR PATH PUR I": "Fatehpuri",
    "KASHMIR GATE": "Kashmere Gate",
    "BARAH KHAMBA": "Barakhamba",  # the tomb by Nizamuddin; plain "Barah Khamba" landed 5 km off
    "ALIQANJ": "Aliganj",
    "RIKABGANJ": "Rakab Ganj",
    "RAJPUR CHHAWNI": "Rajpur Road",
    "QUDSIA GARDEN": "Qudsia Bagh",
    "ARAKPUR BAGH MOCIII": "Arakpur Bagh",
    "MADAN GARHI": "Madangir",
    "CHHATARPIR": "Chhatarpur",
    "KHIRKL": "Khirki",
    "KATWARI SARAI": "Katwaria Sarai",
    "ADMCHINI": "Adchini",
    "KILOKHRI": "Kilokri",
    "ZAMARRUDPUR": "Zamrudpur",
    "HAIDARPUR": "Haiderpur",
    "HASHTSAL": "Hastsal",
    "JANTI": "Jaunti",
    "NAGLI SAKRAOT": "Nangli Sakrawati",
    "JHARAUDA KALAN": "Jharoda Kalan",
}

# Lanes too small for the geocoder, placed by hand from the map listing named alongside. Each listing
# was checked to carry the lane's name and to sit in the right quarter of the walled city (or village).
LANE_COORDS: dict[str, tuple[float, float, str]] = {
    "KUNCHA-I-CHELAN": (28.6469, 77.2411, "Kucha Chelan, Daryaganj"),
    "CHHATTA LAL MIYAN": (28.6414, 77.2380, "Chatta Lal Miya, Daryaganj"),
    "KUNCHA-I-SADULLAH KHAN": (28.6442, 77.2392, "Masjid Saad Ullah Khan, Daryaganj"),
    "KUNCHA-I-FAULAD KHAN": (28.6459, 77.2360, "Kucha Faulad Khan"),
    "BULBULI KHAN A": (28.6463, 77.2316, "Bulbuli Khana"),
    "KALAN MASJID OR KALI MASJID": (28.6450, 77.2307, "Kalan Masjid"),
    "MUHALLA AQAB KALAN MASJID": (28.6450, 77.2307, "Kalan Masjid"),  # "behind the Kalan Masjid"
    "KATRA GOKAL SHAH": (28.6483, 77.2336, "Gali Katra Gokul Shah"),
    "MOCHION-KI-GALI": (28.6461, 77.2348, "Gali Mochiyan"),
    "IMLI MUHALLA": (28.6461, 77.2272, "Mohalla Imli"),
    "BAZAR SIRKI WALAN": (28.6518, 77.2237, "Sirkiwalan"),
    "MUHALLA ROD GARAN": (28.6520, 77.2219, "Rodgran"),
    "MUHALLA FARRASHKHANA": (28.6548, 77.2200, "Farash Khana"),
    "GALI DAKOTAN": (28.6434, 77.2333, "Gali Dakotan"),
    "MUHALLA XIYARYAN": (28.6497, 77.2271, "Mohalla Niyarian"),
    "GALI HAKIM BAQA": (28.6507, 77.2276, "Gali Hakim Baqa"),
    "CHI RAKHANA": (28.6527, 77.2298, "Chira Khana"),
    "MUHALLA KHAJUR KI MASJID": (28.6447, 77.2365, "Khajoor Wali Masjid, Daryaganj"),
    "KAURI T A PUL": (28.6593, 77.2363, "Kauria Bridge"),
    "MUUALLA KUNCHA GHASIRAMA": (28.6573, 77.2243, "Kucha Ghasiram"),
    "BHOJLA PAHARI": (28.6457, 77.2326, "Pahadi Bhojla"),
    "CHATTA SHAHJI": (28.6518, 77.2311, "Chata Shahji Ka"),
    "NAQQAR KHAN A ROAD": (28.6560, 77.2409, "Naubat Khana, Red Fort"),
    "KHWAJA BAQI BILLAH": (28.6538, 77.2156, "Dargah Khwaja Baqi Billah"),
    "QADAJW SHARIF": (28.6501, 77.2121, "Dargah Qadam Sharif"),
    "JOGABAI": (28.5694, 77.2811, "Jogabai Extension"),
}

# Today's name for lanes placed by hand, where it differs from the survey's.
LOCALITY_ALIASES |= {
    "KUNCHA-I-CHELAN": "Kucha Chelan",
    "KUNCHA-I-FAULAD KHAN": "Kucha Faulad Khan",
    "MUHALLA ROD GARAN": "Rodgran",
    "MUHALLA FARRASHKHANA": "Farash Khana",
    "MUHALLA XIYARYAN": "Mohalla Niyarian",
    "KAURI T A PUL": "Kauria Pul",
    "MUUALLA KUNCHA GHASIRAMA": "Kucha Ghasiram",
    "BHOJLA PAHARI": "Pahadi Bhojla",
    "NAQQAR KHAN A ROAD": "the Naubat Khana, Red Fort",
}

# How the survey itself spelt a lane, where the scan garbled the heading. Shown to readers as the
# 1916 name, so it must be the book's spelling, not today's.
LANE_SPELLING_1916 = {
    "FORT": "the Fort",
    "DARIBA-KALAN": "Dariba Kalan",
    "BAZAR PATH PUR I": "Bazar Fathpuri",
    "ALIQANJ": "Aliganj",
    "ARAKPUR BAGH MOCIII": "Arakpur Bagh Mochi",
    "CHHATARPIR": "Chhatarpur",
    "KHIRKL": "Khirki",
    "ADMCHINI": "Adhchini",
    "TXJGHLAQABAD": "Tughlaqabad",
    "BAS A I DARAPUE": "Basai Darapur",
    "QADAJW SHARIF": "Qadam Sharif",
    "CHIRAQH DELHI": "Chiragh Delhi",
    "CHHATTA PARTAB SINGH OR GALI PIPAL WALI": "Chhatta Partab Singh",
    "EGERTON ROAD OR NAI SARAK": "Egerton Road (Nai Sarak)",
    "BULBULI KHAN A": "Bulbuli Khana",
    "KALAN MASJID OR KALI MASJID": "the Kalan Masjid",
    "MUHALLA XIYARYAN": "Muhalla Niyaryan",
    "MUHALLA ROD GARAN": "Muhalla Rodgaran",
    "CHI RAKHANA": "Chirakhana",
    "KAURI T A PUL": "Kauriya Pul",
    "MUUALLA KUNCHA GHASIRAMA": "Muhalla Kuncha Ghasiram",
    "NAQQAR KHAN A ROAD": "Naqqar Khana Road",
    "QADAJW SHARIF": "Qadam Sharif",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower().replace("chauk", "chowk").replace("muhalla", "mohalla"))


def lane_names(locality: str) -> tuple[str, Optional[str]]:
    """(the lane's name in the survey, today's name if it is different)."""
    then = LANE_SPELLING_1916.get(locality.upper()) or re.sub(r"\s{2,}", " ", locality.title())
    then = re.sub(r"-(I|Ki|Ka|Ke)-", lambda m: f"-{m.group(1).lower()}-", then)  # Kuncha-i-Chelan, Mochion-ki-Gali
    now = LOCALITY_ALIASES.get(locality.upper())
    if not now or _norm(now) in _norm(then) or _norm(then) in _norm(now):
        return then, None
    return then, now


def _clean(s: str) -> str:
    s = re.sub(r"[ \t]*\n[ \t]*", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\btho\b", "the", s)
    return s.strip(" .,;:-—")


def _fix_heading(line: str) -> str:
    line = line.strip().rstrip(".,;:- ").strip()
    for pat, rep in _HEADING_FIXES:
        line = pat.sub(rep, line)
    return re.sub(r"\s{2,}", " ", line)


def _is_page_header(line: str) -> bool:
    """'LIST OF MONUMENTS' tops every page and the scan mangles it every time: 'U5T OF', 'UPT OF
    MOXDIEXT8', 'LIST 07 UONTMINTS, 37'. Compare by shape rather than spelling."""
    words = re.sub(r"[^A-Z0-9 ]", " ", line.upper()).split()
    if not words:
        return False
    if any(len(w) >= 7 and SequenceMatcher(None, w, "MONUMENTS").ratio() >= 0.45 for w in words):
        return True
    # "U5T OF", "UPT OF ...", "LIST 07 ...": a short first word, then something that was "OF"
    if 2 <= len(words) <= 5 and 3 <= len(words[0]) <= 5 and words[1] in {"OF", "OP", "OT", "O7", "07", "OS", "0F", "OI", "QF"}:
        return True
    return False


def _looks_like_heading(line: str) -> bool:
    line = line.strip().rstrip(".").strip()
    if not (4 <= len(line) <= 45) or not _HEADING.match(line) or _NOISE.match(line) or _is_page_header(line):
        return False
    letters = sum(c.isalpha() for c in line)
    if letters < 4 or letters < len(line) * 0.6:
        return False
    fixed = _fix_heading(line)
    if re.search(r"\d", fixed) or re.search(r"(.)\1{3,}", fixed):  # ITTTTT5T 5HTHV
        return False
    tokens = fixed.replace("-", " ").split()
    # "I-V I" and similar page-number debris: mostly one- and two-letter fragments
    return sum(len(t) <= 2 for t in tokens) <= len(tokens) / 2


def _entry_start(line: str) -> Optional[int]:
    """Where an entry's name begins on this line, or None if the line does not open an entry.

    The scan writes "No. 12." a dozen ways - "No.(30.", "Wo. 42.", "No 14i", "89.", "No. Ill" - so
    the test is: an (a)-type marker near the start of the line, after something that looks like an
    entry number. A bare "(a)" counts too; a bare "(o)" or "(«)" does not, because those are just as
    often a later field misread.
    """
    m = _A_MARK.search(line[:24])
    if not m:
        return None
    prefix = line[: m.start()]
    if prefix.strip() == "":
        return m.start() if line[m.start():].replace(" ", "").startswith("(a)") else None
    if re.search(r"\d", prefix) or re.search(r"[NWX]\s*[o0O]", prefix):
        return m.start()
    return None


def _book_number(line: str) -> Optional[int]:
    digits = re.findall(r"\d{1,3}", line[:20])
    return int(digits[0]) if digits else None


_INLINE_HEADER = re.compile(r"\d{0,4}\s*\b[LUIT1]?[IST5T]{2,3}\s+O[FPT]\s+M\S{5,12}\.?", re.I)
# A missed entry opening, run on inside the previous one: "No. 231. uO Grave of ...". Only a number
# followed straight away by a marker-like scrap and a capitalised word counts - "near No. 230" in a
# description must not cut it short.
_NEXT_ENTRY = re.compile(r"\b(?:No|N0|Wo|Ko|Ho)[.,*]?\s*\d{1,3}\s*[.,]\s*\(?\s*\S{1,2}\s*\)?\s+[A-Z][a-z]")
_YEAR_SCAN = str.maketrans({"G": "6", "S": "8", "O": "0", "o": "0", "l": "1", "I": "1"})


def _fix_years(text: str) -> str:
    """1G39 -> 1639, 164S -> 1648: four-character tokens that are mostly digits."""
    def fix(m: re.Match) -> str:
        tok = m.group(0)
        return tok.translate(_YEAR_SCAN) if sum(c.isdigit() for c in tok) >= 2 else tok
    return re.sub(r"\b[0-9GSOolI]{4}\b", fix, text)


def _fields(body: str) -> tuple[str, str, str]:
    """(name, period, description) from one entry's text."""
    body = _INLINE_HEADER.sub(" ", body)
    nxt = _NEXT_ENTRY.search(body, 30)
    if nxt:
        body = body[: nxt.start()]
    marks = list(_MARK.finditer(body))
    segs = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        inner = re.sub(r"[\s()]", "", m.group(0))
        segs.append((inner, _clean(body[m.end() : end])))
    if not segs:
        return "", "", ""
    name = segs[0][1]
    period = ""
    for _inner, text in segs[2:7]:
        if text and len(text) <= 90 and _PERIOD_WORDS.search(text):
            period = re.sub(r"^[mh]\.?\s*(?:\S{1,2}\s*\)\s*)?", "", text).strip()  # residue of the (d) field and a broken "(e)"
            period = re.split(r"\s*(?:[{}]|\bNone\b|\bLIST\b|\(\s*[f/]\s*\))", period)[0].strip(" .,")
            period = _fix_years(period)
            break
    desc = ""
    for inner, text in segs[5:]:
        if inner in _J_LETTERS and len(text) >= 40:
            desc = text
            break
    if not desc:  # no readable (j): take the longest prose-like field after the date
        prose = [t for _i, t in segs[5:] if len(t) >= 60 and sum(c.isalpha() for c in t) >= len(t) * 0.7]
        desc = max(prose, key=len) if prose else ""
    # A broken (j) marker leaves "Unnecessary. 0)" or "Good* (A)" at the front; trim to the first sentence start.
    desc = re.sub(r"^[^()]{0,24}\)\s*", "", desc)
    desc = _fix_years(desc)
    desc = _readable_sentences(desc)
    return name[:160], period[:90], desc[:1500]


def _bad_token(w: str) -> bool:
    w = w.strip(".,;:'’‘\"“”()-–—!?")
    if not w:
        return False
    return bool(
        re.search(r"[{}^|*#@~<>\\\[\]«»]", w)
        or re.search(r"[a-z][A-Z]", w)
        or (re.search(r"[A-Za-z]\d|\d[A-Za-z]", w) and not re.fullmatch(r"\d+(st|nd|rd|th)", w))
        or re.search(r"[!/]", w[1:-1] if len(w) > 2 else "")
    )


def _readable_sentences(text: str) -> str:
    """Keep the sentences that read as English; drop the ones the scan turned to debris (Persian
    inscriptions in particular come out as symbol soup)."""
    keep = []
    for sent in re.split(r"(?<=[.;])\s+(?=[A-Z(])", text):
        toks = sent.split()
        if not toks:
            continue
        if sum(_bad_token(t) for t in toks) <= max(1, len(toks) * 0.08):
            keep.append(sent)
    out = " ".join(keep).strip()
    out = re.sub(r"\s*>\s*[A-Z][A-Z .'-]*$", "", out)  # the next lane's heading glued on the end
    return out if _readable_prose(out) else ""


def _readable_prose(text: str) -> bool:
    """A description is worth passing on only if most of it reads as words."""
    tokens = text.split()
    if len(re.findall(r"[A-Za-z]{2,}", text)) < 8:
        return False
    bad = 0
    for tok in tokens:
        w = tok.strip(".,;:'’‘\"“”()-–—!?")
        if not w:
            continue
        if re.search(r"[{}^|*#@~<>\\\[\]]", w):           # scan debris
            bad += 1
        elif re.search(r"[a-z][A-Z]", w):                   # wGidi
            bad += 1
        elif re.search(r"[A-Za-z]\d|\d[A-Za-z]", w) and not re.fullmatch(r"\d+(st|nd|rd|th)", w):  # liean, 1G48
            bad += 1
        elif re.search(r"[!/]", w[1:-1] if len(w) > 2 else ""):  # cons!ructed, f/'l
            bad += 1
    return bad <= max(1, len(tokens) * 0.06)


def _worth_keeping(entry: dict) -> bool:
    name = entry.get("name", "")
    desc = entry.get("description", "")
    # "Mosque (unnamed)" names nothing: it has to earn its place with a description, like an empty name.
    named = bool(name) and not _UNNAMED.search(name) and not _JUNK_NAME.match(name.strip()) and _readable(name) and sum(c.isalpha() for c in name) >= 4
    informative = len(desc) >= 60 and sum(c.isalpha() for c in desc) >= 40
    return named or informative


_UNNAMED = re.compile(r"\b(?:unnamed|nameless|unknown|anonymous)\b", re.I)
_KINDS = ("mosque", "tomb", "grave", "gateway", "gate", "temple", "well", "baoli", "tank", "bridge", "wall",
          "palace", "pavilion", "dargah", "idgah", "garden", "serai", "sarai", "minar", "house", "haveli", "dome")


def _readable(text: str) -> bool:
    """False for scan debris like 'T* mb', 'Ho Itf', 'MW*' or 'fjord warn' - text no reader should see."""
    if re.search(r"[*?#@%^<>{}|\\\]\[~]", text):
        return False
    words = re.findall(r"[^\s,.;:()\-]+", text)
    if not words:
        return False
    odd = sum(1 for w in words if re.search(r"\d", w) and re.search(r"[A-Za-z]", w))
    return odd <= len(words) // 4


def _kind(name: str) -> str:
    low = name.lower()
    return next((k for k in _KINDS if k in low), "monument")


def display_name(name: str) -> str:
    """What a reader sees. 'Mosque (unnamed)' -> 'A mosque'; garbled -> its kind if we can tell it,
    else 'A monument'; a readable real name passes through."""
    name = (name or "").strip()
    if not name or _JUNK_NAME.match(name):
        return "A monument"
    if _UNNAMED.search(name) or not _readable(name):
        return f"A {_kind(name)}"
    return name


def parse(text: str) -> list[dict]:
    """Split a volume's OCR text into monument entries, each tagged with the lane it is filed under."""
    entries: list[dict] = []
    locality = ""
    current: Optional[dict] = None
    buffer: list[str] = []
    seq = 0

    def flush() -> None:
        nonlocal current, buffer
        if current is not None:
            current["name"], current["period"], current["description"] = _fields(" ".join(buffer))
            if _worth_keeping(current):
                entries.append(current)
        current, buffer = None, []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        at = _entry_start(line)
        if at is not None:
            flush()
            seq += 1
            current = {"number": seq, "book_number": _book_number(line[:at]), "locality": locality}
            buffer = [line[at:]]
            continue
        if _looks_like_heading(line):
            flush()
            locality = _fix_heading(line)
            continue
        if current is not None:
            buffer.append(line)
    flush()
    return entries


CACHE_DIR = Path(__file__).resolve().parent / "gazetteer_cache"


async def fetch_volume_text(client: httpx.AsyncClient, archive_id: str) -> str:
    """The OCR text of an Internet Archive item, downloaded once and kept on disk after that."""
    cached = CACHE_DIR / f"{archive_id}.txt"
    if cached.exists() and cached.stat().st_size > 10_000:
        return cached.read_text(encoding="utf-8")
    meta = (await client.get(f"{ARCHIVE}/metadata/{archive_id}", timeout=60)).json()
    names = [f["name"] for f in meta.get("files", []) if f.get("name", "").endswith("_djvu.txt")]
    if not names:
        raise RuntimeError(f"{archive_id} has no OCR text file")
    r = await client.get(f"{ARCHIVE}/download/{archive_id}/{names[0]}", timeout=180, follow_redirects=True)
    r.raise_for_status()
    CACHE_DIR.mkdir(exist_ok=True)
    cached.write_text(r.text, encoding="utf-8")
    return r.text


# ---- placing entries on the map -------------------------------------------------------------

_nominatim_lock = asyncio.Lock()
_nominatim_last = 0.0


async def _geocode(client: httpx.AsyncClient, query: str, viewbox: Optional[str]) -> Optional[tuple[float, float, str]]:
    """Public Nominatim allows about one request a second; hold the whole process to that."""
    global _nominatim_last
    async with _nominatim_lock:
        wait = 1.1 - (asyncio.get_event_loop().time() - _nominatim_last)
        if wait > 0:
            await asyncio.sleep(wait)
        _nominatim_last = asyncio.get_event_loop().time()
    params = {"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "in", "addressdetails": 1}
    if viewbox:
        params |= {"viewbox": viewbox, "bounded": 1}
    r = await client.get("https://nominatim.openstreetmap.org/search", params=params, timeout=30)
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return None
    return float(rows[0]["lat"]), float(rows[0]["lon"]), rows[0].get("display_name", "")


def _locality_queries(locality: str) -> list[str]:
    """A 1916 lane name, spelled the ways a modern map might know it."""
    out: list[str] = []
    alias = LOCALITY_ALIASES.get(locality.upper())
    if alias:
        out.append(f"{alias}, Delhi")
    for part in re.split(r"\s+OR\s+", locality, flags=re.I):  # "EGERTON ROAD OR NAI SARAK"
        base = re.sub(r"\s{2,}", " ", part.title().replace("’", "'")).strip()
        if not base:
            continue
        out.append(f"{base}, Delhi")
        swapped = re.sub(r"^Kuncha-I-", "Kucha ", base, flags=re.I).replace("Muhalla ", "Mohalla ").replace("Chauk", "Chowk")
        if swapped != base:
            out.append(f"{swapped}, Delhi")
        bare = re.sub(r"^(Muhalla|Mohalla|Kuncha-I-|Kucha|Gali|Katra|Haveli|Bazar|Chhatta)\s*", "", swapped, flags=re.I).strip()
        if bare and bare != swapped and len(bare) > 3:
            out.append(f"{bare}, Old Delhi, Delhi")
    return list(dict.fromkeys(out))


async def geocode_localities(localities: Iterable[str], viewbox: Optional[str], progress: Optional[dict] = None) -> dict[str, dict]:
    """Resolve each lane name once. Lanes that no longer exist on the map simply get no entry."""
    names = list(dict.fromkeys(localities))
    found: dict[str, dict] = {}
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        for i, name in enumerate(names, start=1):
            for query in _locality_queries(name):
                try:
                    hit = await _geocode(client, query, viewbox)
                except Exception as exc:
                    logger.warning("geocode %r failed: %s", query, exc)
                    hit = None
                if hit:
                    lat, lng, display = hit
                    found[name] = {"lat": lat, "lng": lng, "matched": query, "display_name": display}
                    break
            if progress is not None:
                progress.update({"localities_done": i, "localities_total": len(names), "localities_found": len(found)})
    return found


async def import_volumes(db, volumes: list[int], viewbox: Optional[str], progress: Optional[dict] = None, dry_run: bool = False) -> dict:
    """Download, parse, place and store. dry_run parses only, and reports what it found."""
    if progress is not None:
        progress.update({"state": "downloading", "volumes": volumes, "entries": 0})
    parsed: list[dict] = []
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        for vol in volumes:
            spec = VOLUMES[vol]
            text = await fetch_volume_text(client, spec["archive_id"])
            got = parse(text)
            for e in got:
                e |= {"volume": vol, "area": spec["area"], "year": spec["year"], "archive_id": spec["archive_id"]}
            parsed += got
            logger.info("gazetteer: volume %s -> %s entries from %s chars", vol, len(got), len(text))
            if progress is not None:
                progress.update({"entries": len(parsed)})

    localities = [e["locality"] for e in parsed if e["locality"]]
    stats = {
        "entries_parsed": len(parsed),
        "with_description": sum(1 for e in parsed if e["description"]),
        "unique_localities": len(set(localities)),
    }
    if dry_run:
        stats |= {
            "state": "dry run",
            "sample_localities": sorted(set(localities))[:40],
            "sample_entries": [{k: e.get(k) for k in ("volume", "book_number", "locality", "name", "period", "description")} for e in parsed[::max(1, len(parsed) // 12)][:12]],
        }
        if progress is not None:
            progress.update(stats)
        return stats

    if progress is not None:
        progress.update({"state": "placing lanes on the map", **stats})
    placed: dict[str, dict] = {
        loc: {"lat": lat, "lng": lng, "matched": f"{label} (placed by hand)", "display_name": label}
        for loc, (lat, lng, label) in LANE_COORDS.items()
    }
    for vol in volumes:
        lanes = [
            e["locality"] for e in parsed
            if e["volume"] == vol and e["locality"] and e["locality"].upper() not in UNPLACEABLE and e["locality"].upper() not in LANE_COORDS
        ]
        placed |= await geocode_localities(lanes, VOLUMES[vol].get("viewbox") or viewbox, progress)

    if progress is not None:
        progress.update({"state": "storing"})
    stored = 0
    for e in parsed:
        where = placed.get(e["locality"])
        if not where:
            continue
        doc = {
            **e,
            "lat": where["lat"],
            "lng": where["lng"],
            "location": {"type": "Point", "coordinates": [where["lng"], where["lat"]]},
            "geocoded_from": where["matched"],
        }
        await db.gazetteer.update_one({"volume": e["volume"], "number": e["number"], "locality": e["locality"]}, {"$set": doc}, upsert=True)
        stored += 1

    result = {
        "state": "done",
        **stats,
        "localities_placed": len(placed),
        "entries_stored": stored,
        "entries_unplaced": len(parsed) - stored,
        "total_in_db": await db.gazetteer.count_documents({}),
    }
    if progress is not None:
        progress.update(result)
    return result


async def nearby(db, lat: float, lng: float, radius_m: int = 400, limit: int = 12) -> list[dict]:
    cursor = db.gazetteer.aggregate(
        [
            {"$geoNear": {"near": {"type": "Point", "coordinates": [lng, lat]}, "distanceField": "dist_m", "maxDistance": radius_m, "spherical": True}},
            {"$limit": limit},
            {"$project": {"_id": 0, "locality": 1, "name": 1, "period": 1, "description": 1, "number": 1, "volume": 1, "year": 1, "dist_m": 1}},
        ]
    )
    return [doc async for doc in cursor]


def as_lines(entries: Iterable[dict]) -> list[str]:
    out = []
    for e in entries:
        if not _worth_keeping(e):
            continue
        head = display_name(e.get("name", ""))
        where = ""
        if e.get("locality"):
            then, now = lane_names(e["locality"])
            where = f" in {then}" + (f" (today {now})" if now else "")
        period = f" ({e['period']})" if e.get("period") else ""
        dist = f", about {round(e['dist_m'])} m away" if e.get("dist_m") is not None else ""
        body = f" {e['description']}" if e.get("description") else ""
        out.append(f"- {head}{period}{where}{dist}, surveyed {e.get('year', '')}:{body}")
    return out
