# -*- coding: utf-8 -*-
"""
SHORTS MAKER
============
Z dlouhého videa (YouTube odkaz nebo MP4 soubor) automaticky udělá krátká
svislá videa (9:16, 1080x1920) pro YouTube Shorts a TikTok s vypálenými
titulky ve stylu TikToku.

Postup programu:
  1. Získá video (stáhne z YouTube přes yt-dlp, nebo použije tvůj soubor).
  2. Vytáhne z videa zvuk (ffmpeg).
  3. Přepíše řeč na text s časy jednotlivých slov (faster-whisper, lokálně, zdarma).
  4. Změří hlasitost zvuku v čase (výkřiky, smích, akce = hlasitá místa).
  5. Vybere nejlepší momenty:
       a) ZDARMA – vlastní bodování (hlasitost + emotivní slova + tempo řeči),
       b) CLAUDE AI – pošle přepis Claudovi, který vybere nejlepší pasáže
          a rovnou napíše názvy a popisy.
  6. Každý klip vystřihne, převede na 9:16 a vypálí do něj titulky.
  7. Uloží hotová MP4 + soubor popisky.txt s návrhy názvů a popisů.

Spuštění:  python shorts_maker.py   (otevře se okno v prohlížeči)
"""

import os
import sys
import re
import json
import time
import wave
import queue
import shutil
import hashlib
import datetime
import threading
import traceback
import subprocess
import unicodedata
from pathlib import Path

import numpy as np

# Aby výpisy s háčky a čárkami nepadaly ve Windows konzoli.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Potlačí zbytečné varování knihovny Hugging Face ve Windows.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


# =============================================================================
#  NASTAVENÍ – tyto hodnoty můžeš klidně upravit
# =============================================================================

PROGRAM_DIR = Path(__file__).resolve().parent
VYSTUP_DIR = PROGRAM_DIR / "vystup"          # sem se ukládají hotové klipy
PRACOVNI_DIR = PROGRAM_DIR / "pracovni"      # stažená videa, zvuk, přepisy (mezipaměť)
SOUBOR_S_KLICEM = PROGRAM_DIR / "api_klic.txt"

JAZYK = "cs"                     # jazyk řeči pro přepis ("cs" = čeština)

# Vzhled titulků (barvy jsou ve formátu ASS: &H00BBGGRR&, tedy MODRÁ-ZELENÁ-ČERVENÁ)
TITULKY_FONT = "Arial Black"     # tučné písmo, ve Windows je vždy k dispozici
TITULKY_VELIKOST = 92            # velikost písma (ve videu 1080x1920)
TITULKY_OBRYS = 7                # tloušťka černého obrysu
TITULKY_STIN = 3                 # stín pod textem
TITULKY_OD_SPODU = 520           # vzdálenost titulků od spodního okraje (px);
                                 # TikTok/Shorts mají dole tlačítka, proto ne úplně dole
BARVA_TEXTU = "&H00FFFFFF&"      # bílá
BARVA_ZVYRAZNENI = "&H0000FFFF&"  # žlutá – aktuálně vyslovované slovo
SLOV_NA_RADEK_MIN = 2
SLOV_NA_RADEK_MAX = 4
ZNAKU_NA_RADEK_MAX = 22          # delší skupiny slov se rozdělí

# Kódování videa
X264_PRESET = "veryfast"         # rychlost kódování procesorem (ultrafast … slow)
X264_KVALITA = 21                # CRF: menší číslo = lepší kvalita a větší soubor

# Minimální mezera mezi dvěma vybranými klipy (sekundy), aby se neopakovaly.
MEZERA_MEZI_KLIPY = 15

# Modely Claude, ze kterých se dá vybrat v okně: (popisek, id modelu, cena vstup $/1M, cena výstup $/1M)
CLAUDE_MODELY = [
    ("Claude Opus 5.5 – nejchytřejší (cca 10–15 Kč / 3h stream)", "claude-opus-5-5", 4.00, 20.00),
    ("Claude Sonnet 5.5 – vyvážený (cca 5–8 Kč / 3h stream)", "claude-sonnet-5-5", 2.00, 10.00),
    ("Claude Haiku 5.5 – nejlevnější (cca 0,5–2 Kč / 3h stream)", "claude-haiku-5-5", 0.10, 0.50),
]
KURZ_USD_CZK = 23.0              # jen pro orientační přepočet ceny do korun

# Slova a fráze, které obvykle znamenají zajímavý/vtipný/emotivní moment.
# Číslo = váha (čím vyšší, tím víc to zvedne skóre). Klidně si doplň vlastní
# hlášky, které na streamu často říkáš. Píše se BEZ diakritiky a malými písmeny.
KLICOVA_SLOVA = {
    # překvapení / šok
    "ty vole": 1.0, "no ty vole": 2.0, "do prdele": 2.0, "kurva": 1.5, "pi*a": 1.5,
    "paneboze": 2.0, "pane boze": 2.0, "proboha": 1.5, "boze": 1.0, "cože": 1.5,
    "coze": 1.5, "to snad ne": 2.5, "to neni mozny": 2.5, "to neni mozne": 2.5,
    "no ne": 1.5, "nevěřím": 2.0, "neverim": 2.0, "co to bylo": 2.5, "co se stalo": 1.5,
    "vazne": 1.0, "fakt jo": 1.0, "wow": 2.0, "sakra": 1.5, "kruci": 1.0, "do haje": 1.5,
    "jejda": 1.0, "ach jo": 1.0, "hruza": 1.5, "des": 1.0,
    # nadšení / výhra
    "jo jo jo": 2.5, "jooo": 2.0, "yes": 2.0, "jupi": 2.0, "vyhral": 2.0, "vyhrali": 2.0,
    "vyhra": 2.0, "gol": 2.0, "neuveritelny": 2.5, "neuveritelne": 2.5, "silene": 2.0,
    "sileny": 2.0, "husty": 1.5, "huste": 1.5, "nejlepsi": 1.5, "legendarni": 2.0,
    "epicky": 2.0, "epic": 2.0, "clutch": 2.5, "headshot": 2.0, "mam ho": 2.0,
    "dostal jsem ho": 2.0, "zabil jsem": 1.5, "boss": 1.0, "konecne": 1.5,
    # prohra / frustrace
    "umrel jsem": 2.0, "umrel": 1.5, "chcipl": 2.0, "zabil me": 2.0, "zabili me": 2.0,
    "nejhorsi": 1.5, "to je bug": 2.0, "co to je": 1.5, "proc": 0.5, "nenavidim": 2.0,
    "pomoc": 1.5, "utikej": 2.0, "rychle": 1.0, "delej": 1.0, "pozor": 1.0,
    # smích
    "haha": 2.5, "hahaha": 3.0, "hehe": 1.5, "smich": 2.0, "to je vtipny": 2.0,
    "to je vtipne": 2.0, "jsem se posral": 2.5, "nemuzu": 1.0,
}


# =============================================================================
#  POMOCNÉ FUNKCE
# =============================================================================

def bez_diakritiky(text):
    """'Příliš žluťoučký' -> 'prilis zlutoucky' (pro hledání klíčových slov)."""
    t = unicodedata.normalize("NFKD", text)
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def nazev_souboru(text, max_delka=50):
    """Z libovolného textu udělá bezpečný název souboru (bez diakritiky a znaků jako ?:/)."""
    t = bez_diakritiky(text)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return (t[:max_delka].rstrip("-")) or "klip"


def cas_text(sekundy):
    """123.4 -> '2:03', 3725 -> '1:02:05'"""
    s = int(round(sekundy))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def cas_ass(sekundy):
    """Čas ve formátu titulků ASS: h:mm:ss.cc"""
    sekundy = max(0.0, sekundy)
    cs = int(round(sekundy * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def najdi_ffmpeg():
    cesta = shutil.which("ffmpeg")
    if not cesta:
        raise RuntimeError(
            "Nenašel jsem program ffmpeg. Nainstaluj ho příkazem\n"
            "   winget install --id Gyan.FFmpeg -e\n"
            "a pak ZAVŘI a znovu otevři okno příkazového řádku i tento program."
        )
    return cesta


def spust_prikaz(prikaz, cwd=None):
    """Spustí externí program (ffmpeg). Při chybě vyhodí výjimku se srozumitelným textem."""
    vysledek = subprocess.run(
        prikaz, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    if vysledek.returncode != 0:
        konec = "\n".join(vysledek.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"Příkaz selhal ({prikaz[0]}):\n{konec}")
    return vysledek


def delka_videa(cesta):
    """Zjistí délku videa v sekundách pomocí ffprobe."""
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    r = spust_prikaz([ffprobe, "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=noprint_wrappers=1:nokey=1", str(cesta)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# =============================================================================
#  KROK 1: ZÍSKÁNÍ VIDEA
# =============================================================================

def je_odkaz(text):
    return bool(re.match(r"^https?://", text.strip(), re.I))


def stahni_z_youtube(url, log):
    """Stáhne video z YouTube v kvalitě max. 1080p jako MP4. Vrací (cesta, název)."""
    import yt_dlp

    cil = PRACOVNI_DIR / "stazene"
    cil.mkdir(parents=True, exist_ok=True)
    posledni = {"procenta": -10}

    def prubeh(d):
        if d.get("status") == "downloading":
            celkem = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if celkem:
                p = int(d.get("downloaded_bytes", 0) * 100 / celkem)
                if p >= posledni["procenta"] + 5:
                    posledni["procenta"] = p
                    log(f"   stahuji… {p} %", prepsat=True)
        elif d.get("status") == "finished":
            posledni["procenta"] = -10
            log("   část stažena, spojuji…", prepsat=True)

    nastaveni = {
        # nejlepší video do 1080p + nejlepší zvuk, spojené do MP4
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(cil / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [prubeh],
    }
    log("⬇️  Stahuji video z YouTube (u 3h streamu to může trvat i desítky minut)…")
    with yt_dlp.YoutubeDL(nastaveni) as ydl:
        info = ydl.extract_info(url, download=True)
        if "entries" in info:          # kdyby to byl playlist, vezmi první video
            info = info["entries"][0]
        cesta = None
        for d in info.get("requested_downloads") or []:
            if d.get("filepath"):
                cesta = Path(d["filepath"])
        if cesta is None or not cesta.exists():
            cesta = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
    if not cesta.exists():
        raise RuntimeError("Stažení se nepovedlo – soubor nebyl nalezen.")
    log(f"✅ Staženo: {info.get('title', cesta.name)}")
    return cesta, info.get("title") or cesta.stem


# =============================================================================
#  KROK 2: ZVUK A HLASITOST
# =============================================================================

def pracovni_slozka_pro(video):
    """Každé video má vlastní pracovní složku (podle názvu, velikosti a data změny),
    takže když stejné video zpracuješ znovu, přepis se nemusí dělat znovu."""
    st = video.stat()
    otisk = hashlib.md5(f"{video.resolve()}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:8]
    slozka = PRACOVNI_DIR / f"{nazev_souboru(video.stem, 40)}_{otisk}"
    slozka.mkdir(parents=True, exist_ok=True)
    return slozka


def vytahni_zvuk(video, slozka, log):
    """Uloží zvuk jako WAV 16 kHz mono (formát, který potřebuje Whisper)."""
    wav = slozka / "zvuk.wav"
    if wav.exists() and wav.stat().st_size > 1000:
        log("✅ Zvuk už je připravený z minula.")
        return wav
    log("🔊 Vytahuji zvuk z videa…")
    docasny = slozka / "zvuk_tmp.wav"
    spust_prikaz([najdi_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                  "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                  "-c:a", "pcm_s16le", str(docasny)])
    docasny.replace(wav)
    log("✅ Zvuk připraven.")
    return wav


KROK_HLASITOSTI = 0.5   # hlasitost se měří po půlsekundách


def spocitej_vzruseni(wav, slozka, log):
    """Vrátí pole 'vzrušení' po 0,5 s: o kolik je dané místo hlasitější než
    okolní dvě minuty (v násobcích směrodatné odchylky). Výkřik = vysoké číslo."""
    soubor = slozka / "vzruseni.npy"
    if soubor.exists():
        return np.load(soubor)
    log("📈 Měřím hlasitost zvuku…")
    db = []
    with wave.open(str(wav), "rb") as w:
        sr = w.getframerate()
        okno = int(sr * KROK_HLASITOSTI)
        while True:
            data = w.readframes(okno * 240)          # čte po 2 minutách
            if not data:
                break
            x = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            k = len(x) // okno
            if k == 0:
                break
            x = x[: k * okno].reshape(k, okno)
            rms = np.sqrt((x ** 2).mean(axis=1) + 1e-12)
            db.extend((20 * np.log10(rms + 1e-6)).tolist())
    db = np.array(db, dtype=np.float32)
    if len(db) == 0:
        return db
    # Klouzavý průměr přes 2 minuty = "normální" hlasitost v daném úseku streamu
    sirka = min(len(db), int(120 / KROK_HLASITOSTI))
    jadro = np.ones(sirka, dtype=np.float32) / sirka
    zaklad = np.convolve(np.pad(db, (sirka // 2, sirka - sirka // 2 - 1), mode="edge"), jadro, mode="valid")
    rozdil = db - zaklad
    odchylka = float(np.std(rozdil)) or 1.0
    vzruseni = np.clip(rozdil / odchylka, -3, 6).astype(np.float32)
    np.save(soubor, vzruseni)
    return vzruseni


def vzruseni_v_useku(vzruseni, od, do):
    a = int(od / KROK_HLASITOSTI)
    b = max(a + 1, int(do / KROK_HLASITOSTI))
    return vzruseni[a:b]


# =============================================================================
#  KROK 3: PŘEPIS ŘEČI (faster-whisper)
# =============================================================================

def prepis_rec(wav, slozka, model_nazev, log):
    """Přepíše řeč na text. Vrací seznam slov: [{"s": začátek, "e": konec, "w": "slovo"}, …].
    Výsledek se uloží, takže při dalším spuštění se stejným videem je hotový hned."""
    soubor = slozka / f"prepis_{model_nazev}.json"
    if soubor.exists():
        data = json.loads(soubor.read_text(encoding="utf-8"))
        log(f"✅ Přepis už existuje z minula ({len(data['slova'])} slov).")
        return data["slova"]

    from faster_whisper import WhisperModel, BatchedInferencePipeline

    log(f"🧠 Načítám model pro přepis řeči „{model_nazev}“ "
        "(poprvé se stahuje z internetu, může to chvíli trvat)…")
    # Máš AMD grafiku, takže Whisper poběží na procesoru. "int8" = rychlé a úsporné na paměť.
    model = WhisperModel(model_nazev, device="cpu", compute_type="int8",
                         cpu_threads=os.cpu_count() or 4)

    nastaveni = dict(
        language=JAZYK,
        word_timestamps=True,              # časy jednotlivých slov (kvůli titulkům)
        vad_filter=True,                   # přeskočí ticho a samotnou hudbu ze hry
        beam_size=1,                       # rychlejší varianta (na CPU se to vyplatí)
        condition_on_previous_text=False,  # u dlouhých streamů brání "zacyklení" přepisu
    )
    log("📝 Přepisuji řeč na text… (na procesoru to u 3h streamu trvá zhruba 30–90 minut "
        "podle zvoleného modelu – nech okno otevřené)")
    start = time.time()
    try:
        # Dávkové zpracování je na vícejádrovém procesoru rychlejší.
        davkovy = BatchedInferencePipeline(model=model)
        segmenty, info = davkovy.transcribe(str(wav), batch_size=8, **nastaveni)
    except Exception:
        segmenty, info = model.transcribe(str(wav), **nastaveni)

    celkem = info.duration or 1
    slova = []
    posledni_hlaseni = 0
    for seg in segmenty:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                slova.append({"s": round(w.start, 2), "e": round(w.end, 2), "w": text})
        if time.time() - posledni_hlaseni > 3:
            posledni_hlaseni = time.time()
            p = min(100, seg.end * 100 / celkem)
            uplynulo = time.time() - start
            zbyva = uplynulo / max(p, 0.1) * (100 - p)
            log(f"   přepsáno {p:.0f} % ({cas_text(seg.end)} z {cas_text(celkem)}), "
                f"zbývá asi {cas_text(zbyva)}", prepsat=True)

    slova.sort(key=lambda x: x["s"])
    soubor.write_text(json.dumps({"model": model_nazev, "slova": slova}, ensure_ascii=False),
                      encoding="utf-8")
    # Pro zajímavost uloží i čitelný přepis
    vety = vytvor_vety(slova)
    (slozka / "prepis_citelny.txt").write_text(
        "\n".join(f"[{cas_text(v['s'])}] {v['text']}" for v in vety), encoding="utf-8")
    log(f"✅ Přepis hotový za {cas_text(time.time() - start)} ({len(slova)} slov).")
    return slova


def vytvor_vety(slova):
    """Seskupí slova do vět/promluv. Věta končí interpunkcí (. ! ?), delší pauzou
    nebo po 12 sekundách. Díky tomu klipy nezačínají ani nekončí uprostřed věty."""
    vety, aktualni = [], []

    def uzavri():
        if aktualni:
            vety.append({
                "s": aktualni[0]["s"], "e": aktualni[-1]["e"],
                "text": " ".join(w["w"] for w in aktualni),
                "slova": list(aktualni),
            })
            aktualni.clear()

    for w in slova:
        if aktualni and (w["s"] - aktualni[-1]["e"] > 0.8 or w["e"] - aktualni[0]["s"] > 12):
            uzavri()
        aktualni.append(w)
        if re.search(r"[.!?…]$", w["w"]):
            uzavri()
    uzavri()
    return vety


# =============================================================================
#  KROK 4a: VÝBĚR MOMENTŮ ZDARMA (bez AI)
# =============================================================================

def skore_textu(text):
    """Kolik "emocí" je v textu: klíčová slova, vykřičníky, otazníky, opakování."""
    t = " " + re.sub(r"[^a-z0-9*? !]+", " ", bez_diakritiky(text)) + " "
    skore = 0.0
    for fraze, vaha in KLICOVA_SLOVA.items():
        f = bez_diakritiky(fraze)
        pocet = t.count(" " + f + " ") + t.count(" " + f + "!") + t.count(" " + f + "?")
        skore += vaha * min(pocet, 3)
    skore += 0.4 * min(text.count("!"), 5) + 0.2 * min(text.count("?"), 5)
    # opakované slovo ("ne ne ne", "jo jo jo") = emoce
    slova = t.split()
    for i in range(len(slova) - 2):
        if slova[i] == slova[i + 1] == slova[i + 2] and len(slova[i]) <= 5:
            skore += 1.0
            break
    return skore


def okraje_klipu(vety, i, j, delka_videa_s):
    """Začátek a konec klipu s malou rezervou, aby se neusekla slova."""
    start = vety[i]["s"] - 0.3
    if i > 0:
        start = max(start, vety[i - 1]["e"] + 0.05)
    konec = vety[j]["e"] + 0.6
    if j + 1 < len(vety):
        konec = min(konec, vety[j + 1]["s"] - 0.05)
    return max(0.0, start), min(konec, delka_videa_s)


def vyber_zdarma(vety, vzruseni, delka_s, pocet, min_d, max_d, log):
    """Projde všechny možné úseky (od začátku jedné věty po konec jiné věty, délky
    min_d–max_d) a každému dá skóre. Pak vybere nejlepší, které se nepřekrývají."""
    log("🔎 Hledám nejlepší momenty (varianta zdarma)…")
    kandidati = []

    if not vety:
        # Žádná řeč – vybírá se jen podle hlasitosti, po 30s úsecích.
        delka = min(max(30, min_d), max_d)
        t = 0.0
        while t + delka <= delka_s:
            v = vzruseni_v_useku(vzruseni, t, t + delka)
            if len(v):
                s = float(np.mean(np.sort(v)[-max(1, len(v) // 4):])) + 0.5 * float(v.max())
                kandidati.append({"start": t, "konec": t + delka, "skore": s, "i": None, "j": None})
            t += 5
    else:
        skore_vet = [skore_textu(v["text"]) for v in vety]
        surova = []
        for i in range(len(vety)):
            for j in range(i, len(vety)):
                start, konec = okraje_klipu(vety, i, j, delka_s)
                d = konec - start
                if d > max_d:
                    break
                if d < min_d:
                    continue
                v = vzruseni_v_useku(vzruseni, start, konec)
                if len(v) == 0:
                    continue
                horni_ctvrtina = float(np.mean(np.sort(v)[-max(1, len(v) // 4):]))
                vrchol = float(v.max())
                text = float(sum(skore_vet[i:j + 1])) / (d / 30.0) ** 0.5
                pocet_slov = sum(len(vety[k]["slova"]) for k in range(i, j + 1))
                hustota = min(1.0, (pocet_slov / d) / 1.8)     # málo slov = nuda/ticho
                # "Háček" – silný začátek (hlasitý nebo emotivní první 4 sekundy)
                prvni = vzruseni_v_useku(vzruseni, start, start + 4)
                hacek = max(float(prvni.max()) if len(prvni) else 0.0, 0.0) + skore_vet[i]
                konci_vetou = 1.0 if re.search(r"[.!?…]$", vety[j]["text"]) else 0.0
                surova.append((i, j, start, konec, horni_ctvrtina, vrchol, text, hustota, hacek, konci_vetou))

        if not surova:
            return []
        pole = np.array([r[4:] for r in surova], dtype=np.float64)

        def normalizuj(sloupec):
            s = pole[:, sloupec]
            return (s - s.mean()) / (s.std() or 1.0)

        celkove = (1.0 * normalizuj(0)      # dlouhodobě hlasité
                   + 0.6 * normalizuj(1)    # výkřik / vrchol
                   + 1.2 * normalizuj(2)    # emotivní slova
                   + 0.4 * normalizuj(4)    # silný začátek
                   + 0.3 * pole[:, 5]       # končí celou větou
                   - 2.0 * (1 - pole[:, 3]))  # penalizace za ticho
        for r, s in zip(surova, celkove):
            kandidati.append({"start": r[2], "konec": r[3], "skore": float(s), "i": r[0], "j": r[1]})

    kandidati.sort(key=lambda k: k["skore"], reverse=True)
    vybrane = []
    for k in kandidati:
        if all(k["konec"] + MEZERA_MEZI_KLIPY <= v["start"] or k["start"] >= v["konec"] + MEZERA_MEZI_KLIPY
               for v in vybrane):
            vybrane.append(k)
            if len(vybrane) >= pocet:
                break

    # Názvy a popisy (bez AI jednoduše z přepisu)
    for k in vybrane:
        if k["i"] is not None:
            useky = vety[k["i"]:k["j"] + 1]
            nejlepsi = max(useky, key=lambda v: skore_textu(v["text"]) + 0.01 * len(v["text"]))
            nazev = nejlepsi["text"].strip()
            if len(nazev) > 60:
                nazev = nazev[:60].rsplit(" ", 1)[0] + "…"
            nazev = (nazev[:1].upper() + nazev[1:]) if nazev else "Moment ze streamu"
            prepis = " ".join(v["text"] for v in useky)
            popis = (prepis[:180].rsplit(" ", 1)[0] + "…") if len(prepis) > 180 else prepis
        else:
            nazev = f"Akce v {cas_text(k['start'])}"
            popis = "Moment ze streamu."
        k.update(nazev=nazev, popis=popis, hashtagy=[], duvod=f"skóre {k['skore']:.2f}")
    log(f"✅ Vybráno {len(vybrane)} klipů.")
    return vybrane


# =============================================================================
#  KROK 4b: VÝBĚR MOMENTŮ POMOCÍ CLAUDE AI
# =============================================================================

SYSTEM_PROMPT = """Jsi zkušený střihač krátkých videí (YouTube Shorts, TikTok) pro český herní kanál.
Dostaneš přepis dlouhého streamu z PS5 rozdělený na očíslované věty s časy a s úrovní hlasitosti
(hl0 = ticho, hl9 = křik/smích/výbuch – hlasité místo bývá vtipná nebo vypjatá situace).

Tvůj úkol: vybrat úseky, které budou fungovat jako samostatné krátké video.
Dobrý klip:
- má silný začátek (háček) v prvních 2–3 sekundách – divák se nesmí nudit,
- je srozumitelný i bez kontextu celého streamu,
- obsahuje vtipnou hlášku, silnou emoci, překvapení, epický moment, fail nebo zajímavou informaci,
- končí pointou nebo dokončenou myšlenkou (ne uprostřed věty),
- neobsahuje dlouhá hluchá místa.
Klipy se nesmí překrývat. Seřaď je od nejlepšího.

Ke každému klipu napiš:
- "nazev": chytlavý český název pro Shorts/TikTok (max. 70 znaků, může mít 1 emoji, nelži o obsahu),
- "popis": 1–2 věty popisu v češtině,
- "hashtagy": 3–6 hashtagů (bez mezer, s #),
- "duvod": krátce, proč je moment dobrý."""


def nacti_api_klic(zadany):
    """Klíč z okna (uloží se do api_klic.txt pro příště), nebo z api_klic.txt, nebo z proměnné prostředí."""
    zadany = (zadany or "").strip()
    if zadany:
        SOUBOR_S_KLICEM.write_text(zadany, encoding="utf-8")
        return zadany
    if SOUBOR_S_KLICEM.exists():
        k = SOUBOR_S_KLICEM.read_text(encoding="utf-8").strip()
        if k:
            return k
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


def vyber_claude(vety, vzruseni, delka_s, pocet, min_d, max_d, model_id, api_klic, nazev_hry, log):
    """Pošle přepis Claudovi a nechá ho vybrat nejlepší momenty. Vrací seznam klipů."""
    import anthropic

    if not vety:
        raise RuntimeError("Ve videu nebyla rozpoznána žádná řeč – AI nemá z čeho vybírat.")
    if not api_klic:
        raise RuntimeError("Chybí API klíč pro Claude (vlož ho do okna nebo do souboru api_klic.txt).")

    # Přepis ve tvaru: "číslo|od-do|hlX|text"
    radky = []
    for idx, v in enumerate(vety):
        h = vzruseni_v_useku(vzruseni, v["s"], v["e"])
        uroven = int(np.clip(round((float(h.max()) if len(h) else 0) * 1.5 + 2), 0, 9))
        radky.append(f"{idx}|{cas_text(v['s'])}-{cas_text(v['e'])}|hl{uroven}|{v['text']}")
    prepis = "\n".join(radky)

    zadani = (
        f"Hra: {nazev_hry or 'neuvedeno'}\n"
        f"Vyber přesně {pocet} klipů. Každý klip je souvislý úsek vět od \"prvni_veta\" do "
        f"\"posledni_veta\" (čísla vět z přepisu) a musí být dlouhý {min_d}–{max_d} sekund.\n"
        f"Mezi klipy nech aspoň {MEZERA_MEZI_KLIPY} sekund odstup.\n\n"
        f"<prepis>\n{prepis}\n</prepis>"
    )
    schema = {
        "type": "object",
        "properties": {
            "klipy": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "prvni_veta": {"type": "integer"},
                        "posledni_veta": {"type": "integer"},
                        "nazev": {"type": "string"},
                        "popis": {"type": "string"},
                        "hashtagy": {"type": "array", "items": {"type": "string"}},
                        "duvod": {"type": "string"},
                    },
                    "required": ["prvni_veta", "posledni_veta", "nazev", "popis", "hashtagy", "duvod"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["klipy"],
        "additionalProperties": False,
    }

    log(f"🤖 Posílám přepis ({len(vety)} vět) modelu {model_id}… (obvykle 1–3 minuty)")
    klient = anthropic.Anthropic(api_key=api_klic)
    parametry = dict(
        model=model_id,
        max_tokens=32000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": zadani}],
        output_config={"effort": "medium",
                       "format": {"type": "json_schema", "schema": schema}},
    )
    try:
        if model_id in ("claude-opus-5-5", "claude-sonnet-5-5"):
            # Kdyby model požadavek odmítl, server ho automaticky zkusí jiným modelem.
            proud = klient.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **parametry)
        else:
            proud = klient.messages.stream(**parametry)
        with proud as s:
            zprava = s.get_final_message()
    except anthropic.AuthenticationError:
        raise RuntimeError("API klíč je neplatný. Zkontroluj ho na console.anthropic.com.")
    except anthropic.PermissionDeniedError:
        raise RuntimeError("API klíč nemá oprávnění (zkontroluj kredit / nastavení účtu).")
    except anthropic.RateLimitError:
        raise RuntimeError("Překročen limit požadavků – zkus to za pár minut znovu.")
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Chyba API ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        raise RuntimeError("Nepodařilo se spojit se serverem Anthropic – zkontroluj internet.")

    if zprava.stop_reason == "refusal":
        raise RuntimeError("Model požadavek odmítl.")
    if zprava.stop_reason == "max_tokens":
        raise RuntimeError("Odpověď modelu byla useknutá (příliš dlouhá).")

    # Orientační cena
    ceny = {m[1]: (m[2], m[3]) for m in CLAUDE_MODELY}
    cin, cout = ceny.get(model_id, (0, 0))
    u = zprava.usage
    cena = (u.input_tokens * cin + u.output_tokens * cout) / 1_000_000
    log(f"💰 Spotřeba: {u.input_tokens:,} vstupních + {u.output_tokens:,} výstupních tokenů "
        f"≈ ${cena:.3f} (≈ {cena * KURZ_USD_CZK:.1f} Kč)".replace(",", " "))

    text = next(b.text for b in zprava.content if b.type == "text")
    navrhy = json.loads(text)["klipy"]

    # Kontrola a oprava návrhů: správná čísla vět, délka, nepřekrývání
    vybrane = []
    for n in navrhy:
        i, j = int(n["prvni_veta"]), int(n["posledni_veta"])
        if not (0 <= i < len(vety)) or not (0 <= j < len(vety)):
            continue
        if j < i:
            i, j = j, i
        start, konec = okraje_klipu(vety, i, j, delka_s)
        while konec - start < min_d and j + 1 < len(vety):        # moc krátký -> prodloužit
            j += 1
            start, konec = okraje_klipu(vety, i, j, delka_s)
        while konec - start > max_d and j > i:                    # moc dlouhý -> zkrátit
            j -= 1
            start, konec = okraje_klipu(vety, i, j, delka_s)
        if konec - start > max_d:
            konec = start + max_d
        k = {"start": start, "konec": konec, "i": i, "j": j, "skore": 0.0,
             "nazev": n["nazev"].strip(), "popis": n["popis"].strip(),
             "hashtagy": n["hashtagy"], "duvod": n["duvod"].strip()}
        if all(k["konec"] <= v["start"] or k["start"] >= v["konec"] for v in vybrane):
            vybrane.append(k)
        if len(vybrane) >= pocet:
            break

    if len(vybrane) < pocet:
        log(f"   AI vrátila jen {len(vybrane)} použitelných klipů, doplním je variantou zdarma.")
        for k in vyber_zdarma(vety, vzruseni, delka_s, pocet * 3, min_d, max_d, lambda *a, **b: None):
            if all(k["konec"] <= v["start"] or k["start"] >= v["konec"] for v in vybrane):
                vybrane.append(k)
            if len(vybrane) >= pocet:
                break
    log(f"✅ Claude vybral {len(vybrane)} klipů.")
    return vybrane


# =============================================================================
#  KROK 5: TITULKY VE STYLU TIKTOKU (formát ASS)
# =============================================================================

def ass_escape(text):
    return text.replace("\\", "/").replace("{", "(").replace("}", ")")


def vytvor_titulky(slova, start_klipu, konec_klipu, velka_pismena):
    """Vytvoří obsah souboru .ass: po 2–4 slovech, aktuální slovo žluté a o kousek větší."""
    slova_klipu = []
    for w in slova:
        if w["s"] >= start_klipu - 0.05 and w["e"] <= konec_klipu + 0.3:
            text = w["w"].strip().strip(",.;:…\"„“")   # čárky a tečky ve stylu TikToku nepíšeme
            if not text:
                continue
            if velka_pismena:
                text = text.upper()
            slova_klipu.append({"s": w["s"] - start_klipu, "e": w["e"] - start_klipu,
                                "w": ass_escape(text), "konec_vety": bool(re.search(r"[.!?…]$", w["w"]))})

    # 1a) rozdělení na úseky řeči – nový úsek začíná po konci věty nebo po pauze
    useky, aktualni = [], []
    for w in slova_klipu:
        if aktualni and (aktualni[-1]["konec_vety"] or w["s"] - aktualni[-1]["e"] > 0.6):
            useky.append(aktualni)
            aktualni = []
        aktualni.append(w)
    if aktualni:
        useky.append(aktualni)

    # 1b) každý úsek rovnoměrně rozdělit na skupinky po 2–4 slovech
    #     (např. 5 slov -> 3 + 2, ne 4 + 1, aby nezůstalo osamocené slovo)
    def rozdel(seznam):
        n = len(seznam)
        pocet_skupin = -(-n // SLOV_NA_RADEK_MAX)            # zaokrouhlení nahoru
        velikosti = [n // pocet_skupin + (1 if i < n % pocet_skupin else 0) for i in range(pocet_skupin)]
        vysledek, i = [], 0
        for v in velikosti:
            skupina = seznam[i:i + v]
            i += v
            znaku = sum(len(x["w"]) + 1 for x in skupina)
            if znaku > ZNAKU_NA_RADEK_MAX and len(skupina) >= 2:   # moc dlouhá slova -> půlit
                vysledek.extend(rozdel(skupina[:len(skupina) // 2]))
                vysledek.extend(rozdel(skupina[len(skupina) // 2:]))
            else:
                vysledek.append(skupina)
        return vysledek

    skupiny = []
    for usek in useky:
        skupiny.extend(rozdel(usek))

    # 2) pro každé slovo jeden řádek titulků, kde je právě to slovo zvýrazněné
    udalosti = []
    delka = konec_klipu - start_klipu
    for g, skupina in enumerate(skupiny):
        dalsi_start = skupiny[g + 1][0]["s"] if g + 1 < len(skupiny) else delka
        konec_skupiny = min(skupina[-1]["e"] + 0.4, dalsi_start, delka)
        for k, w in enumerate(skupina):
            od = skupina[0]["s"] if k == 0 else w["s"]
            do = skupina[k + 1]["s"] if k + 1 < len(skupina) else konec_skupiny
            if do - od < 0.02:
                do = od + 0.02
            casti = []
            for m, x in enumerate(skupina):
                if m == k:
                    casti.append("{\\c" + BARVA_ZVYRAZNENI + "\\fscx108\\fscy108}" + x["w"] + "{\\r}")
                else:
                    casti.append(x["w"])
            udalosti.append(f"Dialogue: 0,{cas_ass(od)},{cas_ass(do)},TikTok,,0,0,0,,{' '.join(casti)}")

    hlavicka = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTok,{TITULKY_FONT},{TITULKY_VELIKOST},{BARVA_TEXTU},{BARVA_TEXTU},&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,{TITULKY_OBRYS},{TITULKY_STIN},2,70,70,{TITULKY_OD_SPODU},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return hlavicka + "\n".join(udalosti) + "\n"


# =============================================================================
#  KROK 6: STŘIH, PŘEVOD NA 9:16 A VYPÁLENÍ TITULKŮ (ffmpeg)
# =============================================================================

AMD_NEFUNGUJE = False   # nastaví se, když kódování grafikou AMD selže


def vyrenderuj_klip(video, start, konec, ass_obsah, cil, rozostrene_pozadi, pouzit_amd, log):
    """Vystřihne úsek, převede ho na 1080x1920 a vypálí titulky."""
    delka = konec - start
    pracovni = cil.parent / "_docasne"
    pracovni.mkdir(exist_ok=True)
    ass_soubor = pracovni / (cil.stem + ".ass")
    ass_soubor.write_text(ass_obsah, encoding="utf-8")

    if rozostrene_pozadi:
        # Celé video uprostřed + jeho rozmazaná zvětšená kopie jako pozadí
        obraz = ("[0:v]split=2[pozadi][popredi];"
                 "[pozadi]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
                 "boxblur=8:2,scale=1080:1920,eq=brightness=-0.1[pozadi2];"
                 "[popredi]scale=1080:-2:flags=lanczos[popredi2];"
                 "[pozadi2][popredi2]overlay=(W-w)/2:(H-h)/2,setsar=1")
    else:
        # Ořez na střed obrazu
        obraz = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
                 "crop=1080:1920,setsar=1")
    # Titulky: ffmpeg spouštíme přímo ve složce s .ass souborem, takže stačí krátký
    # název souboru (vyhneme se problémům s dvojtečkou v cestě C:\ ve Windows).
    obraz += f",ass='{ass_soubor.name}',format=yuv420p[v]"

    zvuk = f"afade=t=in:d=0.15,afade=t=out:st={max(0.0, delka - 0.35):.2f}:d=0.35"

    def prikaz(kodek):
        if kodek == "amd":
            video_kodek = ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp",
                           "-qp_i", "20", "-qp_p", "22", "-qp_b", "24"]
        else:
            video_kodek = ["-c:v", "libx264", "-preset", X264_PRESET, "-crf", str(X264_KVALITA)]
        return ([najdi_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                 "-ss", f"{start:.3f}", "-i", str(Path(video).resolve()), "-t", f"{delka:.3f}",
                 "-filter_complex", obraz, "-map", "[v]", "-map", "0:a:0?",
                 "-af", zvuk]
                + video_kodek
                + ["-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                   "-movflags", "+faststart", str(cil.resolve())])

    global AMD_NEFUNGUJE
    if pouzit_amd and not AMD_NEFUNGUJE:
        try:
            spust_prikaz(prikaz("amd"), cwd=pracovni)
            return
        except RuntimeError as e:
            AMD_NEFUNGUJE = True      # příště už to nezkoušet
            log(f"   ⚠️ Kódování přes AMD grafiku nejde, používám procesor. ({str(e).splitlines()[-1]})")
    spust_prikaz(prikaz("cpu"), cwd=pracovni)


# =============================================================================
#  HLAVNÍ POSTUP
# =============================================================================

def zpracuj(vstup_text, nahrany_soubor, nazev_hry, rezim_ai, claude_model, api_klic,
            pocet, min_d, max_d, whisper_model, rozostrene, velka_pismena, pouzit_amd, log):
    najdi_ffmpeg()
    PRACOVNI_DIR.mkdir(parents=True, exist_ok=True)
    VYSTUP_DIR.mkdir(parents=True, exist_ok=True)
    pocet, min_d, max_d = int(pocet), float(min_d), float(max_d)
    if min_d > max_d:
        min_d, max_d = max_d, min_d

    # --- 1) vstupní video ---
    vstup_text = (vstup_text or "").strip().strip('"')
    if nahrany_soubor:
        video, titul = Path(nahrany_soubor), Path(nahrany_soubor).stem
        log(f"📁 Používám nahraný soubor: {video.name}")
    elif vstup_text and je_odkaz(vstup_text):
        video, titul = stahni_z_youtube(vstup_text, log)
    elif vstup_text and Path(vstup_text).exists():
        video, titul = Path(vstup_text), Path(vstup_text).stem
        log(f"📁 Používám soubor z disku: {video}")
    else:
        raise RuntimeError("Vlož odkaz na YouTube, cestu k souboru, nebo nahraj MP4 soubor.")

    delka_s = delka_videa(video)
    log(f"⏱️  Délka videa: {cas_text(delka_s)}")
    slozka = pracovni_slozka_pro(video)

    # --- 2) zvuk, hlasitost, přepis ---
    wav = vytahni_zvuk(video, slozka, log)
    vzruseni = spocitej_vzruseni(wav, slozka, log)
    slova = prepis_rec(wav, slozka, whisper_model, log)
    vety = vytvor_vety(slova)

    # --- 3) výběr momentů ---
    klipy = None
    if rezim_ai:
        try:
            klipy = vyber_claude(vety, vzruseni, delka_s, pocet, min_d, max_d,
                                 claude_model, nacti_api_klic(api_klic), nazev_hry, log)
        except Exception as e:
            log(f"⚠️ Výběr přes Claude se nepovedl: {e}")
            log("   Pokračuji variantou zdarma.")
    if not klipy:
        klipy = vyber_zdarma(vety, vzruseni, delka_s, pocet, min_d, max_d, log)
    if not klipy:
        raise RuntimeError("Nepodařilo se najít žádný vhodný úsek (je video dost dlouhé?).")

    # --- 4) výstupní složka ---
    razitko = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    cilova = VYSTUP_DIR / f"{nazev_souboru(titul, 40)}_{razitko}"
    cilova.mkdir(parents=True, exist_ok=True)

    zakladni_tagy = ["#shorts", "#ps5", "#gaming", "#cz", "#czsk"]
    if nazev_hry:
        zakladni_tagy.insert(1, "#" + re.sub(r"[^A-Za-z0-9]", "", bez_diakritiky(nazev_hry)))

    # --- 5) render klipů ---
    hotove, popisky = [], []
    for n, k in enumerate(klipy, start=1):
        soubor = cilova / f"{n:02d}_{nazev_souboru(k['nazev'])}.mp4"
        log(f"🎬 Klip {n}/{len(klipy)}: {cas_text(k['start'])}–{cas_text(k['konec'])} "
            f"({k['konec'] - k['start']:.0f} s) „{k['nazev']}“")
        ass = vytvor_titulky(slova, k["start"], k["konec"], velka_pismena)
        vyrenderuj_klip(video, k["start"], k["konec"], ass, soubor, rozostrene, pouzit_amd, log)
        hotove.append(str(soubor))

        tagy = []
        for t in list(k.get("hashtagy") or []) + zakladni_tagy:
            t = "#" + t.strip().lstrip("#").replace(" ", "")
            if len(t) > 1 and t.lower() not in [x.lower() for x in tagy]:
                tagy.append(t)
        popisky.append(
            f"=== {soubor.name} ===\n"
            f"Čas v původním videu: {cas_text(k['start'])} – {cas_text(k['konec'])} "
            f"({k['konec'] - k['start']:.0f} s)\n"
            f"Název: {k['nazev']}\n"
            f"Popis: {k['popis']}\n"
            f"Hashtagy: {' '.join(tagy[:8])}\n"
            f"Proč tento moment: {k.get('duvod', '')}\n"
        )

    (cilova / "popisky.txt").write_text("\n".join(popisky), encoding="utf-8")
    shutil.rmtree(cilova / "_docasne", ignore_errors=True)
    log(f"\n🎉 HOTOVO! {len(hotove)} klipů je ve složce:\n   {cilova}")
    log("   Názvy a popisy najdeš v souboru popisky.txt.")
    if sys.platform.startswith("win"):
        try:
            os.startfile(cilova)      # otevře složku v Průzkumníku
        except Exception:
            pass
    return hotove + [str(cilova / "popisky.txt")]


# =============================================================================
#  OVLÁDACÍ OKNO (Gradio – otevře se v prohlížeči)
# =============================================================================

def spustit_z_okna(vstup_text, nahrany_soubor, nazev_hry, rezim, claude_model, api_klic,
                   pocet, min_d, max_d, whisper_model, format_videa, velka_pismena, pouzit_amd):
    """Spustí zpracování ve vedlejším vlákně a průběžně posílá výpis do okna."""
    fronta = queue.Queue()
    vysledek = {}

    def log(zprava, prepsat=False):
        print(zprava)
        fronta.put(("prepsat" if prepsat else "pridat", zprava))

    def prace():
        try:
            vysledek["soubory"] = zpracuj(
                vstup_text, nahrany_soubor, nazev_hry, rezim.startswith("Claude"),
                claude_model, api_klic, pocet, min_d, max_d, whisper_model,
                format_videa.startswith("Rozostřené"), velka_pismena, pouzit_amd, log)
        except Exception as e:
            log(f"\n❌ CHYBA: {e}")
            log("\n(Technické detaily pro hledání chyby:)\n" + traceback.format_exc())
        finally:
            fronta.put(None)

    threading.Thread(target=prace, daemon=True).start()
    radky, posledni_prepsatelny = [], False
    while True:
        polozka = fronta.get()
        if polozka is None:
            break
        druh, zprava = polozka
        if druh == "prepsat" and posledni_prepsatelny and radky:
            radky[-1] = zprava              # průběh (procenta) přepisuje poslední řádek
        else:
            radky.append(zprava)
        posledni_prepsatelny = druh == "prepsat"
        yield "\n".join(radky[-400:]), None
    yield "\n".join(radky[-400:]), vysledek.get("soubory")


def vytvor_okno():
    import gradio as gr

    with gr.Blocks(title="Shorts Maker") as okno:
        gr.Markdown("# 🎬 Shorts Maker\nZ dlouhého streamu udělá krátká svislá videa s titulky "
                    "pro YouTube Shorts a TikTok.")
        # --- To hlavní: co zpracovat a jak vybírat ---
        vstup_text = gr.Textbox(
            label="1) Vlož odkaz na YouTube video NEBO cestu k MP4 souboru",
            placeholder="https://www.youtube.com/watch?v=…   nebo   C:\\Videa\\stream.mp4")
        nahrany = gr.File(label="…nebo sem přetáhni MP4 soubor", file_types=["video"], type="filepath")
        rezim = gr.Radio(["Zdarma (bez AI)", "Claude AI (placené, chytřejší výběr a názvy)"],
                         value="Zdarma (bez AI)", label="2) Jak vybírat nejlepší momenty")
        api_klic = gr.Textbox(label="Claude API klíč – jen pokud jsi vybral Claude AI "
                                    "(stačí jednou, program si ho zapamatuje)",
                              type="password", placeholder="sk-ant-…")

        # --- Pokročilé volby: není potřeba na ně sahat ---
        with gr.Accordion("⚙️ Pokročilé nastavení (není potřeba měnit)", open=False):
            with gr.Row():
                with gr.Column():
                    pocet = gr.Slider(5, 15, value=8, step=1, label="Počet klipů")
                    min_d = gr.Slider(15, 60, value=20, step=1, label="Minimální délka klipu (s)")
                    max_d = gr.Slider(20, 90, value=60, step=1, label="Maximální délka klipu (s)")
                    nazev_hry = gr.Textbox(label="Název hry (pro hashtagy, nepovinné)",
                                           placeholder="např. GTA V")
                    claude_model = gr.Dropdown([(m[0], m[1]) for m in CLAUDE_MODELY],
                                               value=CLAUDE_MODELY[0][1], label="Model Claude")
                with gr.Column():
                    whisper_model = gr.Dropdown(
                        [("small – rychlý, dobrý (doporučeno)", "small"),
                         ("large-v3-turbo – přesnější, asi 2× pomalejší", "large-v3-turbo"),
                         ("medium – přesnější, nejpomalejší", "medium")],
                        value="small", label="Přesnost přepisu řeči")
                    format_videa = gr.Radio(["Oříznout na střed", "Rozostřené pozadí (celý obraz hry)"],
                                            value="Oříznout na střed", label="Převod na svislé video")
                    velka_pismena = gr.Checkbox(value=True, label="Titulky VELKÝMI PÍSMENY")
                    pouzit_amd = gr.Checkbox(value=True, label="Kódovat video grafikou AMD (rychlejší; "
                                                                "když nejde, použije se procesor)")
        tlacitko = gr.Button("3) 🚀 Spustit", variant="primary", size="lg")
        vypis = gr.Textbox(label="Průběh", lines=18, max_lines=30, autoscroll=True)
        soubory = gr.File(label="Hotové klipy (ke stažení)", file_count="multiple")

        tlacitko.click(
            spustit_z_okna,
            inputs=[vstup_text, nahrany, nazev_hry, rezim, claude_model, api_klic,
                    pocet, min_d, max_d, whisper_model, format_videa, velka_pismena, pouzit_amd],
            outputs=[vypis, soubory],
        )
    return okno


if __name__ == "__main__":
    print("Spouštím Shorts Maker… okno se otevře v prohlížeči.")
    print("Tohle černé okno NEZAVÍREJ, dokud program používáš.")
    vytvor_okno().queue().launch(inbrowser=True, allowed_paths=[str(VYSTUP_DIR)])
