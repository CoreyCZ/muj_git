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
     Umí češtinu, angličtinu i mix (ty mluvíš česky, postavy ve hře anglicky).
  4. Změří hlasitost zvuku v čase (výkřiky, smích, akce = hlasitá místa).
  5. Vybere nejlepší momenty:
       a) ZDARMA – vlastní bodování (hlasitost + emotivní slova + tempo řeči),
       b) CLAUDE AI – pošle přepis Claudovi, který vybere nejlepší pasáže
          a rovnou napíše názvy, popisy a úderný nadpis.
  6. Ukáže ti návrhy ke kontrole (můžeš je odškrtnout, upravit čas, nadpis, název
     a podívat se na náhled).
  7. Každý vybraný klip vystřihne, převede na 9:16 (střed / rozmazané pozadí /
     kamera nahoře + hra dole), přidá přiblížení v akčních momentech, velký
     nadpis na začátek a titulky ve stylu TikToku.
  8. Uloží hotová MP4 + soubor popisky.txt s návrhy názvů a popisů.

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

# Vzhled titulků (barvy jsou ve formátu ASS: &H00BBGGRR&, tedy MODRÁ-ZELENÁ-ČERVENÁ)
TITULKY_FONT = "Arial Black"     # tučné písmo, ve Windows je vždy k dispozici
TITULKY_VELIKOST = 92            # velikost písma (ve videu 1080x1920)
TITULKY_OBRYS = 7                # tloušťka černého obrysu
TITULKY_STIN = 3                 # stín pod textem
TITULKY_OD_SPODU = 520           # vzdálenost titulků od spodního okraje (px);
                                 # TikTok/Shorts mají dole tlačítka, proto ne úplně dole
BARVA_TEXTU = "&H00FFFFFF&"      # bílá
BARVA_ZVYRAZNENI = "&H0000FFFF&"  # žlutá – aktuálně vyslovované slovo
BARVA_DIALOGU = "&H00E6D8AD&"    # světle modrá – titulky anglických dialogů postav ve hře
SLOV_NA_RADEK_MIN = 2
SLOV_NA_RADEK_MAX = 4
ZNAKU_NA_RADEK_MAX = 22          # delší skupiny slov se rozdělí

# Velký nadpis na začátku klipu ("háček", aby divák neodscrolloval)
NADPIS_VELIKOST = 96
NADPIS_DELKA = 3.2               # kolik sekund je nadpis vidět
NADPIS_BARVA = "&H00FFFFFF&"     # bílá
NADPIS_POZADI = "&H26000000&"    # tmavý podklad pod nadpisem (první dvojčíslí = průhlednost)
NADPIS_MAX_ZNAKU = 40

# Přiblížení (zoom) v akčních momentech
PRIBLIZENI_SILA = 0.18           # 0.18 = přiblížit o 18 %
PRIBLIZENI_PRAH = 2.2            # jak moc hlasitý musí moment být (vyšší = méně často)
PRIBLIZENI_MAX = 2               # max. počet přiblížení v jednom klipu

# Kódování videa
X264_PRESET = "veryfast"         # rychlost kódování procesorem (ultrafast … slow)
X264_KVALITA = 21                # CRF: menší číslo = lepší kvalita a větší soubor

# Minimální mezera mezi dvěma vybranými klipy (sekundy), aby se neopakovaly.
MEZERA_MEZI_KLIPY = 15

# Kolik návrhů navíc ukázat ke kontrole (nad zvolený počet klipů).
NAVRHU_NAVIC = 4

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
KLICOVA_SLOVA_CS = {
    # překvapení / šok
    "ty vole": 1.0, "no ty vole": 2.0, "do prdele": 2.0, "kurva": 1.5,
    "paneboze": 2.0, "pane boze": 2.0, "proboha": 1.5, "boze": 1.0, "coze": 1.5,
    "to snad ne": 2.5, "to neni mozny": 2.5, "to neni mozne": 2.5,
    "no ne": 1.5, "neverim": 2.0, "co to bylo": 2.5, "co se stalo": 1.5,
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
    # GTA
    "policajti": 1.5, "fizlove": 1.5, "honicka": 2.0, "utekl jsem": 2.0, "wasted": 2.5,
    "busted": 2.5, "bouracka": 2.0, "vybuch": 2.0, "nabural": 1.5, "hvezdy": 1.0,
    # smích
    "haha": 2.5, "hahaha": 3.0, "hehe": 1.5, "smich": 2.0, "to je vtipny": 2.0,
    "to je vtipne": 2.0, "jsem se posral": 2.5, "nemuzu": 1.0,
}
KLICOVA_SLOVA_EN = {
    "oh my god": 2.5, "omg": 2.0, "what the": 2.0, "wtf": 2.0, "no way": 2.5,
    "lets go": 2.5, "let s go": 2.5, "holy": 2.0, "shit": 1.5, "fuck": 1.5, "damn": 1.5,
    "bro": 1.0, "dude": 1.0, "wow": 2.0, "insane": 2.5, "crazy": 2.0, "i m dead": 2.0,
    "wasted": 2.5, "busted": 2.5, "run": 1.0, "help": 1.5, "haha": 2.5, "hahaha": 3.0,
    "lol": 2.0, "yes": 2.0, "clutch": 2.5, "headshot": 2.0, "are you kidding": 2.5,
    "what just happened": 3.0, "nice": 1.0, "gg": 1.5, "cops": 1.5, "police": 1.5,
    "get out": 1.5, "watch out": 1.5, "oh no": 2.0, "no no no": 2.5, "unbelievable": 2.5,
}

# Jazyky v okně: popisek -> kód
JAZYKY_RECI = {
    "Čeština": "cs",
    "Angličtina": "en",
    "Čeština + angličtina (mluvím česky, postavy ve hře anglicky)": "mix",
}
JAZYKY_TEXTU = {"Čeština": "cs", "English": "en"}

# Rozložení svislého videa
ROZLOZENI = {
    "Oříznout na střed": "stred",
    "Rozostřené pozadí (celý obraz hry)": "rozmazane",
    "Kamera nahoře + hra dole (facecam)": "kamera",
}
POZICE_KAMERY = ["Vpravo nahoře", "Vlevo nahoře", "Vpravo dole", "Vlevo dole"]


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


def bez_emoji(text):
    """Odstraní emoji (do videa se vypálit nedají – zobrazily by se jako čtverečky)."""
    t = "".join(c for c in text if unicodedata.category(c) not in ("So", "Cs", "Co", "Cn")
                and c not in "\u200d\ufe0f")
    return re.sub(r"\s+", " ", t).strip()


def tvar(n, jeden, dva_az_ctyri, pet_a_vic):
    """Správný český tvar: 1 klip, 3 klipy, 5 klipů."""
    if n == 1:
        return f"{n} {jeden}"
    return f"{n} {dva_az_ctyri if 2 <= n <= 4 else pet_a_vic}"


def cas_text(sekundy):
    """123.4 -> '2:03', 3725 -> '1:02:05'"""
    s = int(round(sekundy))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def cas_presny(sekundy):
    """123.45 -> '2:03.5' (s desetinou sekundy – pro úpravy v tabulce)"""
    d = int(round(sekundy * 10))
    h, d = divmod(d, 36000)
    m, d = divmod(d, 600)
    s, d = divmod(d, 10)
    return f"{h}:{m:02d}:{s:02d}.{d}" if h else f"{m}:{s:02d}.{d}"


def precti_cas(text):
    """'2:03.5' / '1:02:03' / '123.5' -> sekundy"""
    casti = str(text).strip().replace(",", ".").split(":")
    try:
        hodnoty = [float(c) for c in casti]
    except ValueError:
        raise ValueError(f"Nerozumím času „{text}“ (piš např. 2:03.5)")
    sekundy = 0.0
    for h in hodnoty:
        sekundy = sekundy * 60 + h
    return sekundy


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
            "Nenašel jsem program ffmpeg. Zavři program, restartuj počítač "
            "a spusť START.bat znovu (ffmpeg doinstaluje)."
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
        raise RuntimeError(f"Příkaz selhal ({Path(prikaz[0]).name}):\n{konec}")
    return vysledek


def info_o_videu(cesta):
    """Zjistí délku videa (s) a počet snímků za sekundu."""
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    r = spust_prikaz([ffprobe, "-v", "error", "-select_streams", "v:0",
                      "-show_entries", "stream=r_frame_rate:format=duration",
                      "-of", "json", str(cesta)])
    data = json.loads(r.stdout or "{}")
    try:
        delka = float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        delka = 0.0
    fps = "30"
    try:
        fps_text = data["streams"][0]["r_frame_rate"]
        a, b = fps_text.split("/")
        if float(a) > 0 and float(b) > 0 and float(a) / float(b) <= 120:
            fps = fps_text
    except Exception:
        pass
    return delka, fps


def fps_cislo(fps):
    a, _, b = str(fps).partition("/")
    return float(a) / float(b or 1)


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


def priprav_video(vstup, log):
    """Vstup = odkaz na YouTube nebo cesta k souboru. Vrací (cesta, název)."""
    vstup = str(vstup).strip().strip('"')
    if je_odkaz(vstup):
        return stahni_z_youtube(vstup, log)
    cesta = Path(vstup)
    if cesta.exists():
        log(f"📁 Používám soubor: {cesta.name}")
        return cesta, cesta.stem
    raise RuntimeError(f"Soubor neexistuje: {vstup}")


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
    a = max(0, int(od / KROK_HLASITOSTI))
    b = max(a + 1, int(do / KROK_HLASITOSTI))
    return vzruseni[a:b]


# =============================================================================
#  KROK 3: PŘEPIS ŘEČI (faster-whisper)
# =============================================================================

SLOVA_CS = {"je", "a", "se", "na", "že", "ze", "ty", "jsem", "co", "tak", "ne", "jo", "vole", "už",
            "uz", "jak", "tam", "tady", "mi", "mě", "me", "no", "ale", "by", "si", "asi", "teď",
            "ted", "proč", "proc", "kde", "není", "neni", "jsi", "bude", "máme", "dobře", "jako",
            "sem", "fakt", "toho", "tom", "ten", "ta", "ještě", "jeste", "já", "ja", "mám", "mam"}
SLOVA_EN = {"the", "you", "and", "is", "what", "i", "of", "it", "that", "this", "we", "my", "your",
            "don't", "i'm", "it's", "are", "was", "with", "for", "get", "got", "they", "be",
            "have", "just", "know", "right", "man", "come", "go", "here", "there", "now", "yeah",
            "okay", "oh", "hey", "what's", "gonna", "you're", "let's", "can", "do", "not", "all"}


def je_anglicky(text):
    """Jednoduchý odhad, jestli je věta anglicky (podle běžných slov a diakritiky)."""
    t = text.lower()
    slova = re.findall(r"[a-záčďéěíňóřšťúůýž']+", t)
    if not slova:
        return False
    cs = sum(1 for s in slova if s in SLOVA_CS) + 2 * len(re.findall(r"[áčďéěíňóřšťúůýž]", t))
    en = sum(1 for s in slova if s in SLOVA_EN)
    return en > cs


def nacti_wav(wav):
    """Načte WAV (16 kHz, mono, 16 bit) do pole čísel pro Whisper."""
    with wave.open(str(wav), "rb") as w:
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def prepis_rec(wav, slozka, model_nazev, jazyk, log):
    """Přepíše řeč na text. Vrací seznam slov:
    [{"s": začátek, "e": konec, "w": "slovo", "l": "cs"/"en"}, …].
    Výsledek se uloží, takže při dalším spuštění se stejným videem je hotový hned."""
    soubor = slozka / f"prepis_{model_nazev}_{jazyk}.json"
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
        word_timestamps=True,              # časy jednotlivých slov (kvůli titulkům)
        vad_filter=True,                   # přeskočí ticho a samotnou hudbu ze hry
        beam_size=1,                       # rychlejší varianta (na CPU se to vyplatí)
        condition_on_previous_text=False,  # u dlouhých streamů brání "zacyklení" přepisu
    )
    if jazyk == "mix":
        nastaveni.update(language=None, multilingual=True)   # jazyk se pozná u každé věty zvlášť
    else:
        nastaveni.update(language=jazyk)

    # Zvuk načteme sami (WAV 16 kHz mono) – nespoléháme na knihovnu "av",
    # jejíž novější verze nejsou s faster-whisper kompatibilní.
    zvuk = nacti_wav(wav)

    log("📝 Přepisuji řeč na text… (na procesoru to u 3h streamu trvá zhruba 30–90 minut "
        "podle zvoleného modelu – nech okno otevřené)")
    start = time.time()
    try:
        # Dávkové zpracování je na vícejádrovém procesoru rychlejší.
        davkovy = BatchedInferencePipeline(model=model)
        segmenty, info = davkovy.transcribe(zvuk, batch_size=8, **nastaveni)
    except Exception:
        segmenty, info = model.transcribe(zvuk, **nastaveni)

    celkem = info.duration or 1
    slova = []
    posledni_hlaseni = 0
    for seg in segmenty:
        lang = "en" if (jazyk == "en" or (jazyk == "mix" and je_anglicky(seg.text))) else "cs"
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                slova.append({"s": round(w.start, 2), "e": round(w.end, 2), "w": text, "l": lang})
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
        "\n".join(f"[{cas_text(v['s'])}]{' (EN)' if v['l'] == 'en' else ''} {v['text']}" for v in vety),
        encoding="utf-8")
    log(f"✅ Přepis hotový za {cas_text(time.time() - start)} ({len(slova)} slov).")
    return slova


def vytvor_vety(slova):
    """Seskupí slova do vět/promluv. Věta končí interpunkcí (. ! ?), delší pauzou,
    změnou jazyka nebo po 12 sekundách. Díky tomu klipy nezačínají ani nekončí
    uprostřed věty."""
    vety, aktualni = [], []

    def uzavri():
        if aktualni:
            vety.append({
                "s": aktualni[0]["s"], "e": aktualni[-1]["e"],
                "text": " ".join(w["w"] for w in aktualni),
                "l": aktualni[0].get("l", "cs"),
                "slova": list(aktualni),
            })
            aktualni.clear()

    for w in slova:
        if aktualni and (w["s"] - aktualni[-1]["e"] > 0.8 or w["e"] - aktualni[0]["s"] > 12
                         or w.get("l") != aktualni[-1].get("l")):
            uzavri()
        aktualni.append(w)
        if re.search(r"[.!?…]$", w["w"]):
            uzavri()
    uzavri()
    return vety


# =============================================================================
#  KROK 4a: VÝBĚR MOMENTŮ ZDARMA (bez AI)
# =============================================================================

def _pro_hledani(text):
    return " " + re.sub(r"[^a-z0-9*? !]+", " ", bez_diakritiky(text)) + " "


def skore_textu(text, klicova_slova):
    """Kolik "emocí" je v textu: klíčová slova, vykřičníky, otazníky, opakování."""
    t = _pro_hledani(text)
    skore = 0.0
    for fraze, vaha in klicova_slova.items():
        f = _pro_hledani(fraze).strip()
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


def klicova_slova_pro(jazyk):
    if jazyk == "cs":
        return KLICOVA_SLOVA_CS
    if jazyk == "en":
        return KLICOVA_SLOVA_EN
    return {**KLICOVA_SLOVA_EN, **KLICOVA_SLOVA_CS}


def okraje_klipu(vety, i, j, delka_videa_s):
    """Začátek a konec klipu s malou rezervou, aby se neusekla slova."""
    start = vety[i]["s"] - 0.3
    if i > 0:
        start = max(start, vety[i - 1]["e"] + 0.05)
    konec = vety[j]["e"] + 0.6
    if j + 1 < len(vety):
        konec = min(konec, vety[j + 1]["s"] - 0.05)
    return max(0.0, start), min(konec, delka_videa_s)


def zkrat(text, max_znaku):
    text = text.strip()
    if len(text) <= max_znaku:
        return text
    return text[:max_znaku].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def vyber_zdarma(vety, vzruseni, delka_s, pocet, min_d, max_d, jazyk_reci, log):
    """Projde všechny možné úseky (od začátku jedné věty po konec jiné věty, délky
    min_d–max_d) a každému dá skóre. Pak vybere nejlepší, které se nepřekrývají."""
    log("🔎 Hledám nejlepší momenty (varianta zdarma)…")
    klicova = klicova_slova_pro(jazyk_reci)
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
        skore_vet = [skore_textu(v["text"], klicova) for v in vety]
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

    # Názvy, nadpisy a popisy (bez AI jednoduše z přepisu)
    for k in vybrane:
        if k["i"] is not None:
            useky = vety[k["i"]:k["j"] + 1]
            nejlepsi = max(useky, key=lambda v: skore_textu(v["text"], klicova) + 0.01 * len(v["text"]))
            veta = nejlepsi["text"].strip()
            nazev = zkrat(veta, 60)
            nazev = (nazev[:1].upper() + nazev[1:]) if nazev else "Moment ze streamu"
            nadpis = zkrat(" ".join(veta.split()[:7]).rstrip(",.;:"), NADPIS_MAX_ZNAKU)
            prepis = " ".join(v["text"] for v in useky)
            popis = zkrat(prepis, 180)
        else:
            nazev = f"Akce v {cas_text(k['start'])}"
            nadpis = ""
            popis = "Moment ze streamu."
        k.update(nazev=nazev, nadpis=nadpis, popis=popis, hashtagy=[], duvod=f"skóre {k['skore']:.2f}")
    log(f"✅ Nalezeno: {tvar(len(vybrane), 'moment', 'momenty', 'momentů')}.")
    return vybrane


# =============================================================================
#  KROK 4b: VÝBĚR MOMENTŮ POMOCÍ CLAUDE AI
# =============================================================================

SYSTEM_PROMPT = """Jsi zkušený střihač krátkých videí (YouTube Shorts, TikTok) pro herní kanál
(PS5, např. GTA). Dostaneš přepis dlouhého streamu rozdělený na očíslované věty s časy,
s úrovní hlasitosti (hl0 = ticho, hl9 = křik/smích/výbuch – hlasité místo bývá vtipná nebo
vypjatá situace) a případně se značkou [EN] pro anglické dialogy postav ve hře.

Tvůj úkol: vybrat úseky, které budou fungovat jako samostatné krátké video.
Dobrý klip:
- má silný začátek (háček) v prvních 2–3 sekundách – divák se nesmí nudit,
- je srozumitelný i bez kontextu celého streamu,
- obsahuje vtipnou hlášku, silnou emoci, překvapení, epický moment, fail nebo zajímavou informaci,
- končí pointou nebo dokončenou myšlenkou (ne uprostřed věty),
- neobsahuje dlouhá hluchá místa.
Klipy se nesmí překrývat. Seřaď je od nejlepšího.

Ke každému klipu napiš (v jazyce, který určí zadání):
- "nadpis": krátký úderný text, který bude velkým písmem v prvních 3 sekundách videa
  (max. 35 znaků, BEZ emoji, láká k dokoukání, např. „TOHLE JSEM NEČEKAL“),
- "nazev": chytlavý název pro Shorts/TikTok (max. 70 znaků, může mít 1 emoji, nelži o obsahu),
- "popis": 1–2 věty popisu,
- "hashtagy": 3–6 hashtagů (bez mezer, s #),
- "duvod": krátce česky, proč je moment dobrý."""


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


def vyber_claude(vety, vzruseni, delka_s, pocet, min_d, max_d, nast, log):
    """Pošle přepis Claudovi a nechá ho vybrat nejlepší momenty. Vrací seznam klipů."""
    import anthropic

    model_id = nast["claude_model"]
    api_klic = nacti_api_klic(nast["api_klic"])
    if not vety:
        raise RuntimeError("Ve videu nebyla rozpoznána žádná řeč – AI nemá z čeho vybírat.")
    if not api_klic:
        raise RuntimeError("Chybí API klíč pro Claude (vlož ho do okna nebo do souboru api_klic.txt).")

    # Přepis ve tvaru: "číslo|od-do|hlX|text"
    radky = []
    for idx, v in enumerate(vety):
        h = vzruseni_v_useku(vzruseni, v["s"], v["e"])
        uroven = int(np.clip(round((float(h.max()) if len(h) else 0) * 1.5 + 2), 0, 9))
        znacka = "[EN] " if (nast["jazyk_reci"] == "mix" and v["l"] == "en") else ""
        radky.append(f"{idx}|{cas_text(v['s'])}-{cas_text(v['e'])}|hl{uroven}|{znacka}{v['text']}")
    prepis = "\n".join(radky)

    jazyk_textu = "češtině" if nast["jazyk_textu"] == "cs" else "angličtině (English)"
    zadani = (
        f"Hra: {nast['nazev_hry'] or 'neuvedeno'}\n"
        f"Nadpis, název, popis a hashtagy piš v {jazyk_textu}.\n"
        f"Vyber přesně {pocet} klipů. Každý klip je souvislý úsek vět od \"prvni_veta\" do "
        f"\"posledni_veta\" (čísla vět z přepisu) a musí být dlouhý {min_d:.0f}–{max_d:.0f} sekund.\n"
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
                        "nadpis": {"type": "string"},
                        "nazev": {"type": "string"},
                        "popis": {"type": "string"},
                        "hashtagy": {"type": "array", "items": {"type": "string"}},
                        "duvod": {"type": "string"},
                    },
                    "required": ["prvni_veta", "posledni_veta", "nadpis", "nazev", "popis",
                                 "hashtagy", "duvod"],
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
             "nadpis": bez_emoji(n["nadpis"])[:NADPIS_MAX_ZNAKU],
             "nazev": n["nazev"].strip(), "popis": n["popis"].strip(),
             "hashtagy": n["hashtagy"], "duvod": n["duvod"].strip()}
        if all(k["konec"] <= v["start"] or k["start"] >= v["konec"] for v in vybrane):
            vybrane.append(k)
        if len(vybrane) >= pocet:
            break

    if len(vybrane) < pocet:
        log(f"   AI vrátila jen {len(vybrane)} použitelné návrhy, zbytek doplním variantou zdarma.")
        for k in vyber_zdarma(vety, vzruseni, delka_s, pocet * 3, min_d, max_d,
                              nast["jazyk_reci"], lambda *a, **b: None):
            if all(k["konec"] <= v["start"] or k["start"] >= v["konec"] for v in vybrane):
                vybrane.append(k)
            if len(vybrane) >= pocet:
                break
    log(f"✅ Claude vybral {tvar(len(vybrane), 'moment', 'momenty', 'momentů')}.")
    return vybrane


# =============================================================================
#  KROK 5: TITULKY A NADPIS (formát ASS)
# =============================================================================

def ass_escape(text):
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def vytvor_titulky(slova, start_klipu, konec_klipu, nast, nadpis=""):
    """Vytvoří obsah souboru .ass:
    - titulky po 2–4 slovech, aktuální slovo žluté a o kousek větší,
    - (volitelně) velký nadpis v prvních sekundách klipu."""
    velka_pismena = nast["velka_pismena"]
    mix = nast["jazyk_reci"] == "mix"
    slova_klipu = []
    for w in slova:
        if w["s"] >= start_klipu - 0.05 and w["e"] <= konec_klipu + 0.3:
            je_dialog = mix and w.get("l") == "en"
            if je_dialog and not nast["titulky_dialogy"]:
                continue                                  # anglické dialogy postav vynechat
            text = w["w"].strip().strip(",.;:…\"„“")      # čárky a tečky ve stylu TikToku nepíšeme
            if not text:
                continue
            if velka_pismena:
                text = text.upper()
            slova_klipu.append({"s": w["s"] - start_klipu, "e": w["e"] - start_klipu,
                                "w": ass_escape(text), "dialog": je_dialog,
                                "konec_vety": bool(re.search(r"[.!?…]$", w["w"]))})

    # 1a) rozdělení na úseky řeči – nový úsek začíná po konci věty, po pauze nebo při změně jazyka
    useky, aktualni = [], []
    for w in slova_klipu:
        if aktualni and (aktualni[-1]["konec_vety"] or w["s"] - aktualni[-1]["e"] > 0.6
                         or w["dialog"] != aktualni[-1]["dialog"]):
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
        zaklad = ("{\\c" + BARVA_DIALOGU + "}") if skupina[0]["dialog"] else ""
        for k, w in enumerate(skupina):
            od = skupina[0]["s"] if k == 0 else w["s"]
            do = skupina[k + 1]["s"] if k + 1 < len(skupina) else konec_skupiny
            if do - od < 0.02:
                do = od + 0.02
            casti = []
            for m, x in enumerate(skupina):
                if m == k:
                    casti.append("{\\c" + BARVA_ZVYRAZNENI + "\\fscx108\\fscy108}" + x["w"]
                                 + "{\\r}" + zaklad)
                else:
                    casti.append(x["w"])
            udalosti.append(f"Dialogue: 0,{cas_ass(od)},{cas_ass(do)},TikTok,,0,0,0,,{zaklad}{' '.join(casti)}")

    # 3) velký nadpis na začátku (vyskočí, chvíli drží a zmizí)
    nadpis = ass_escape(bez_emoji(nadpis or ""))
    if nast["nadpis"] and nadpis:
        efekt = "{\\fad(120,300)\\fscx70\\fscy70\\t(0,160,\\fscx112\\fscy112)\\t(160,300,\\fscx100\\fscy100)}"
        udalosti.append(f"Dialogue: 1,{cas_ass(0)},{cas_ass(min(NADPIS_DELKA, delka))},Nadpis,,0,0,0,,"
                        f"{efekt}{nadpis.upper()}")

    # Nadpis se dává nahoru; u rozložení s kamerou na předěl kamera/hra
    nadpis_od_shora = {"stred": 250, "rozmazane": 330, "kamera": 520}.get(nast["rozlozeni"], 250)

    hlavicka = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTok,{TITULKY_FONT},{TITULKY_VELIKOST},{BARVA_TEXTU},{BARVA_TEXTU},&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,{TITULKY_OBRYS},{TITULKY_STIN},2,70,70,{TITULKY_OD_SPODU},1
Style: Nadpis,{TITULKY_FONT},{NADPIS_VELIKOST},{NADPIS_BARVA},{NADPIS_BARVA},{NADPIS_POZADI},&H00000000&,-1,0,0,0,100,100,0,0,3,22,0,8,90,90,{nadpis_od_shora},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return hlavicka + "\n".join(udalosti) + "\n"


# =============================================================================
#  KROK 6: STŘIH, PŘEVOD NA 9:16, PŘIBLÍŽENÍ A TITULKY (ffmpeg)
# =============================================================================

def momenty_priblizeni(vzruseni, start, konec):
    """Najde nejhlasitější místa klipu (výbuch, výkřik), kde se obraz přiblíží.
    Vrací seznam časů (od začátku klipu)."""
    v = vzruseni_v_useku(vzruseni, start, konec)
    if len(v) == 0:
        return []
    poradi = np.argsort(v)[::-1]
    casy = []
    for idx in poradi:
        if v[idx] < PRIBLIZENI_PRAH or len(casy) >= PRIBLIZENI_MAX:
            break
        t = idx * KROK_HLASITOSTI
        if t < 1.0 or t > (konec - start) - 2.5:
            continue
        if all(abs(t - c) > 8 for c in casy):
            casy.append(t)
    return sorted(casy)


def filtr_priblizeni(casy, fps, sirka, vyska):
    """ffmpeg filtr zoompan: v daných časech rychle přiblíží, chvíli drží, pak oddálí."""
    if not casy:
        return ""
    T = f"(in/{fps_cislo(fps):.5f})"
    casti = []
    for t in casy:
        a = max(0.0, t - 0.3)                 # začátek přiblížení (kousek před vrcholem)
        b = a + 0.15 + 1.4 + 0.4              # konec oddálení
        casti.append(f"min(1,max(0,min(({T}-{a:.2f})/0.15,({b:.2f}-{T})/0.4)))")
    vyraz = casti[0]
    for c in casti[1:]:
        vyraz = f"max({vyraz},{c})"
    return (f",zoompan=z='1+{PRIBLIZENI_SILA}*{vyraz}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={sirka}x{vyska}:fps={fps}")


def vyrez_kamery(nast):
    """Kde ve videu je kamera (facecam): vrací (x, y, šířka, výška) jako podíl obrazu."""
    f = max(0.08, min(0.6, nast["kamera_velikost"] / 100.0))
    pozice = nast["kamera_pozice"]
    x = 1 - f if "Vpravo" in pozice else 0.0
    y = 1 - f if "dole" in pozice else 0.0
    return x, y, f, f


AMD_NEFUNGUJE = False   # nastaví se, když kódování grafikou AMD selže


def vyrenderuj_klip(video, k, slova, vzruseni, fps, nast, cil, log, nahled=False):
    """Vystřihne úsek, převede ho na 1080x1920, přidá přiblížení, nadpis a titulky.
    nahled=True vyrobí rychlý malý náhled (540x960) pro kontrolu."""
    global AMD_NEFUNGUJE
    start, konec = k["start"], k["konec"]
    delka = konec - start
    pracovni = Path(cil).parent / "_docasne"
    pracovni.mkdir(parents=True, exist_ok=True)
    ass_soubor = pracovni / (Path(cil).stem + ".ass")
    ass_soubor.write_text(vytvor_titulky(slova, start, konec, nast, k.get("nadpis", "")), encoding="utf-8")

    zoom_casy = momenty_priblizeni(vzruseni, start, konec) if nast["priblizeni"] else []
    rozlozeni = nast["rozlozeni"]

    if rozlozeni == "rozmazane":
        # Celé video uprostřed + jeho rozmazaná zvětšená kopie jako pozadí
        obraz = ("[0:v]split=2[pozadi][popredi];"
                 "[pozadi]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
                 "boxblur=8:2,scale=1080:1920,eq=brightness=-0.1[pozadi2];"
                 "[popredi]scale=1080:-2:flags=lanczos[popredi2];"
                 "[pozadi2][popredi2]overlay=(W-w)/2:(H-h)/2,setsar=1"
                 + filtr_priblizeni(zoom_casy, fps, 1080, 1920))
    elif rozlozeni == "kamera":
        # Nahoře kamera (1080x608), dole hra oříznutá na střed (1080x1312)
        x, y, w, h = vyrez_kamery(nast)
        obraz = ("[0:v]split=2[k][h];"
                 f"[k]crop=iw*{w:.4f}:ih*{h:.4f}:iw*{x:.4f}:ih*{y:.4f},"
                 "scale=1080:608:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:608,setsar=1[kam];"
                 "[h]scale=1080:1312:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1312,setsar=1"
                 + filtr_priblizeni(zoom_casy, fps, 1080, 1312) + "[hra];"
                 "[kam][hra]vstack=inputs=2,setsar=1")
    else:
        # Ořez na střed obrazu
        obraz = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
                 "crop=1080:1920,setsar=1" + filtr_priblizeni(zoom_casy, fps, 1080, 1920))
    # Titulky: ffmpeg spouštíme přímo ve složce s .ass souborem, takže stačí krátký
    # název souboru (vyhneme se problémům s dvojtečkou v cestě C:\ ve Windows).
    obraz += f",ass='{ass_soubor.name}'"
    if nahled:
        obraz += ",scale=540:960"
    obraz += ",format=yuv420p[v]"

    zvuk = f"afade=t=in:d=0.15,afade=t=out:st={max(0.0, delka - 0.35):.2f}:d=0.35"

    def prikaz(kodek):
        if nahled:
            video_kodek = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30"]
        elif kodek == "amd":
            video_kodek = ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp",
                           "-qp_i", "20", "-qp_p", "22", "-qp_b", "24"]
        else:
            video_kodek = ["-c:v", "libx264", "-preset", X264_PRESET, "-crf", str(X264_KVALITA)]
        return ([najdi_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                 "-ss", f"{start:.3f}", "-i", str(Path(video).resolve()), "-t", f"{delka:.3f}",
                 "-filter_complex", obraz, "-map", "[v]", "-map", "0:a:0?",
                 "-af", zvuk]
                + video_kodek
                + ["-c:a", "aac", "-b:a", "96k" if nahled else "192k", "-ar", "48000",
                   "-movflags", "+faststart", str(Path(cil).resolve())])

    if nast["amd"] and not AMD_NEFUNGUJE and not nahled:
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

def analyzuj(vstup, nast, log, pocet_navrhu=None):
    """Kroky 1–4: získá video, přepíše řeč, změří hlasitost a navrhne momenty.
    Vrací slovník se vším, co je potřeba pro náhledy a výrobu klipů."""
    najdi_ffmpeg()
    PRACOVNI_DIR.mkdir(parents=True, exist_ok=True)
    pocet = int(pocet_navrhu or nast["pocet"])
    min_d, max_d = sorted((float(nast["min_d"]), float(nast["max_d"])))

    video, titul = priprav_video(vstup, log)
    delka_s, fps = info_o_videu(video)
    log(f"⏱️  Délka videa: {cas_text(delka_s)}")
    slozka = pracovni_slozka_pro(video)

    wav = vytahni_zvuk(video, slozka, log)
    vzruseni = spocitej_vzruseni(wav, slozka, log)
    slova = prepis_rec(wav, slozka, nast["whisper_model"], nast["jazyk_reci"], log)
    vety = vytvor_vety(slova)

    klipy = None
    if nast["rezim_ai"]:
        try:
            klipy = vyber_claude(vety, vzruseni, delka_s, pocet, min_d, max_d, nast, log)
        except Exception as e:
            log(f"⚠️ Výběr přes Claude se nepovedl: {e}")
            log("   Pokračuji variantou zdarma.")
    if not klipy:
        klipy = vyber_zdarma(vety, vzruseni, delka_s, pocet, min_d, max_d, nast["jazyk_reci"], log)
    if not klipy:
        raise RuntimeError("Nepodařilo se najít žádný vhodný úsek (je video dost dlouhé?).")

    return {"video": str(video), "titul": titul, "delka": delka_s, "fps": fps,
            "slozka": str(slozka), "slova": slova, "klipy": klipy}


def vyrob_klipy(analyza, klipy, nast, log):
    """Krok 5–6: vyrobí vybrané klipy a soubor popisky.txt. Vrací (seznam souborů, složka)."""
    VYSTUP_DIR.mkdir(parents=True, exist_ok=True)
    vzruseni = np.load(Path(analyza["slozka"]) / "vzruseni.npy")
    razitko = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    cilova = VYSTUP_DIR / f"{nazev_souboru(analyza['titul'], 40)}_{razitko}"
    cilova.mkdir(parents=True, exist_ok=True)

    if nast["jazyk_textu"] == "en":
        zakladni_tagy = ["#shorts", "#ps5", "#gaming", "#gameplay", "#fyp"]
    else:
        zakladni_tagy = ["#shorts", "#ps5", "#gaming", "#cz", "#czsk"]
    if nast["nazev_hry"]:
        zakladni_tagy.insert(1, "#" + re.sub(r"[^A-Za-z0-9]", "", bez_diakritiky(nast["nazev_hry"])))

    hotove, popisky = [], []
    for n, k in enumerate(klipy, start=1):
        soubor = cilova / f"{n:02d}_{nazev_souboru(k['nazev'])}.mp4"
        log(f"🎬 Klip {n}/{len(klipy)}: {cas_text(k['start'])}–{cas_text(k['konec'])} "
            f"({k['konec'] - k['start']:.0f} s) „{k['nazev']}“")
        vyrenderuj_klip(analyza["video"], k, analyza["slova"], vzruseni, analyza["fps"], nast, soubor, log)
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
            f"Nadpis ve videu: {k.get('nadpis', '')}\n"
            f"Popis: {k['popis']}\n"
            f"Hashtagy: {' '.join(tagy[:8])}\n"
            f"Proč tento moment: {k.get('duvod', '')}\n"
        )

    (cilova / "popisky.txt").write_text("\n".join(popisky), encoding="utf-8")
    shutil.rmtree(cilova / "_docasne", ignore_errors=True)
    log(f"\n🎉 HOTOVO! Vytvořeno: {tvar(len(hotove), 'klip', 'klipy', 'klipů')}. Složka:\n   {cilova}")
    log("   Názvy a popisy najdeš v souboru popisky.txt.")
    return hotove + [str(cilova / "popisky.txt")], cilova


def otevri_slozku(slozka):
    if sys.platform.startswith("win"):
        try:
            os.startfile(slozka)      # otevře složku v Průzkumníku
        except Exception:
            pass


def zpracuj_vse(vstupy, nast, log):
    """Více videí najednou: každé zanalyzuje a rovnou vyrobí nejlepší klipy (bez kontroly)."""
    vsechny, posledni = [], None
    for c, vstup in enumerate(vstupy, start=1):
        log(f"\n━━━━━━━━ Video {c}/{len(vstupy)} ━━━━━━━━")
        try:
            analyza = analyzuj(vstup, nast, log)
            soubory, posledni = vyrob_klipy(analyza, analyza["klipy"], nast, log)
            vsechny.extend(soubory)
        except Exception as e:
            log(f"❌ Video {c} se nepodařilo zpracovat: {e}")
    if posledni:
        otevri_slozku(posledni.parent if len(vstupy) > 1 else posledni)
    return vsechny


# =============================================================================
#  VZHLED OKNA
# =============================================================================

VZHLED_CSS = """
:root, .dark {
    --sm-bg: #0a0b12;
    --sm-karta: rgba(255,255,255,0.035);
    --sm-okraj: rgba(255,255,255,0.08);
    --sm-text: #e7e9f3;
    --sm-tlumeny: #9aa0b8;
    --sm-gradient: linear-gradient(100deg, #8b5cf6 0%, #ec4899 55%, #f97316 100%);
}
body, gradio-app, .gradio-container {
    background:
        radial-gradient(900px 500px at 0% -10%, rgba(139,92,246,0.22), transparent 60%),
        radial-gradient(800px 450px at 100% 0%, rgba(236,72,153,0.16), transparent 60%),
        var(--sm-bg) !important;
    color: var(--sm-text);
}
.gradio-container { max-width: 1040px !important; margin: 0 auto !important; padding: 12px 16px 40px !important; }
footer { display: none !important; }

/* Hlavička */
#hero { text-align: center; padding: 22px 10px 6px; }
#hero .logo { font-size: 46px; line-height: 1; }
#hero h1 { font-size: clamp(32px, 6vw, 50px); font-weight: 900; letter-spacing: -1.5px; margin: 6px 0 4px; }
#hero p { color: var(--sm-tlumeny); font-size: 17px; margin: 0 auto; max-width: 620px; }
#hero .stitky { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; margin-top: 18px; }
#hero .stitek {
    font-size: 13px; padding: 6px 12px; border-radius: 999px; color: var(--sm-text);
    background: rgba(255,255,255,0.05); border: 1px solid var(--sm-okraj);
}

/* Karty */
.karta {
    background: var(--sm-karta) !important; border: 1px solid var(--sm-okraj) !important;
    border-radius: 20px !important; padding: 20px !important;
    box-shadow: 0 10px 40px rgba(0,0,0,0.25); backdrop-filter: blur(6px);
}
.karta .block, .karta .form { background: transparent !important; border: none !important; box-shadow: none !important; }
.nadpis-karty { font-size: 18px; font-weight: 800; margin: 0 0 6px; color: var(--sm-text); }
.nadpis-karty span {
    display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px;
    border-radius: 9px; margin-right: 8px; font-size: 15px; color: white; background: var(--sm-gradient);
}
.napoveda { color: var(--sm-tlumeny); font-size: 13.5px; margin: 0 0 4px; }

input[type=text], input[type=password], input[type=number], textarea {
    background: rgba(0,0,0,0.35) !important; border: 1px solid var(--sm-okraj) !important;
    border-radius: 12px !important; color: var(--sm-text) !important;
}
input[type=text]:focus, input[type=password]:focus, textarea:focus { border-color: #a78bfa !important; box-shadow: 0 0 0 3px rgba(139,92,246,0.25) !important; }

/* Tlačítko Spustit */
#spustit, #vytvorit {
    background: var(--sm-gradient) !important; border: none !important; color: white !important;
    font-size: 20px !important; font-weight: 900 !important; letter-spacing: 0.3px;
    padding: 18px !important; border-radius: 16px !important; margin-top: 6px;
    box-shadow: 0 12px 34px rgba(236,72,153,0.35); transition: transform .15s ease, filter .15s ease;
}
#spustit:hover, #vytvorit:hover { transform: translateY(-2px); filter: brightness(1.08); }

/* Výpis průběhu */
#vypis textarea {
    font-family: ui-monospace, "Cascadia Code", Consolas, monospace !important; font-size: 13.5px !important;
    line-height: 1.55 !important; background: #05060b !important;
}
.karta-pokrocile {
    border-radius: 16px !important; background: var(--sm-karta) !important; border: 1px solid var(--sm-okraj) !important;
}
input[type=checkbox], input[type=radio] { accent-color: #a855f7; }
/* Vybraná volba v přepínači */
label.selected { background: var(--sm-gradient) !important; color: white !important; border-color: transparent !important; }

#vytvorit { font-size: 17px !important; padding: 14px !important; }
#stav {
    text-align: center; font-size: 19px; font-weight: 700; padding: 16px 18px; border-radius: 16px;
    background: rgba(255,255,255,0.04); border: 1px solid var(--sm-okraj); color: var(--sm-text);
}
#vstup textarea { font-size: 17px !important; padding: 14px !important; }
#tabulka, #tabulka * { font-family: "Inter", "Segoe UI", system-ui, sans-serif !important; font-size: 13.5px; }
"""

# Vynutí tmavý režim stránky.
VZHLED_JS = "() => { document.body.classList.add('dark'); }"


# =============================================================================
#  OVLÁDACÍ OKNO (Gradio – otevře se v prohlížeči)
# =============================================================================

def sloz_nastaveni(rezim, claude_model, api_klic, jazyk_reci, jazyk_textu, titulky_dialogy,
                   rozlozeni, kamera_pozice, kamera_velikost, nadpis, priblizeni,
                   pocet, min_d, max_d, whisper_model, velka_pismena, amd, nazev_hry):
    """Posbírá všechna nastavení z okna do jednoho slovníku."""
    return {
        "rezim_ai": str(rezim).startswith("Claude"),
        "claude_model": claude_model or CLAUDE_MODELY[0][1],
        "api_klic": api_klic or "",
        "jazyk_reci": JAZYKY_RECI.get(jazyk_reci, "cs"),
        "jazyk_textu": JAZYKY_TEXTU.get(jazyk_textu, "cs"),
        "titulky_dialogy": bool(titulky_dialogy),
        "rozlozeni": ROZLOZENI.get(rozlozeni, "stred"),
        "kamera_pozice": kamera_pozice or POZICE_KAMERY[0],
        "kamera_velikost": float(kamera_velikost or 25),
        "nadpis": bool(nadpis),
        "priblizeni": bool(priblizeni),
        "pocet": int(pocet), "min_d": float(min_d), "max_d": float(max_d),
        "whisper_model": whisper_model or "small",
        "velka_pismena": bool(velka_pismena),
        "amd": bool(amd),
        "nazev_hry": (nazev_hry or "").strip(),
    }


def nacti_vstupy(text, soubory):
    """Každý řádek textu = jeden odkaz nebo cesta; k tomu nahrané soubory."""
    vstupy = [r.strip().strip('"') for r in (text or "").splitlines() if r.strip()]
    for s in soubory or []:
        vstupy.append(s if isinstance(s, str) else getattr(s, "name", str(s)))
    return vstupy


def na_pozadi(prace):
    """Spustí prace(log) ve vedlejším vlákně. Průběžně vrací
    (celý výpis, hotovo, výsledek, krátký stav pro velký řádek nahoře)."""
    fronta = queue.Queue()
    vysledek = {}

    def log(zprava, prepsat=False):
        print(zprava)
        fronta.put(("prepsat" if prepsat else "pridat", zprava))

    def vlakno():
        try:
            vysledek["ok"] = prace(log)
        except Exception as e:
            vysledek["chyba"] = str(e)
            log(f"\n❌ CHYBA: {e}")
            log("\n(Technické detaily pro hledání chyby:)\n" + traceback.format_exc())
        finally:
            fronta.put(None)

    threading.Thread(target=vlakno, daemon=True).start()
    radky, posledni_prepsatelny, stav = [], False, "⏳ Začínám…"
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
        if "chyba" not in vysledek and zprava.strip() and not zprava.startswith("\n("):
            stav = zprava.strip().splitlines()[0]
            if zprava.startswith("   "):     # průběh (procenta) -> hezčí ikonka
                stav = "⏳ " + stav
        yield "\n".join(radky[-400:]), False, None, stav
    if "chyba" in vysledek:
        stav = f"❌ Chyba: {vysledek['chyba'].splitlines()[0]}"
    yield "\n".join(radky[-400:]), True, vysledek.get("ok"), stav


# ---- zapamatování nastavení mezi spuštěními ----
SOUBOR_NASTAVENI = PROGRAM_DIR / "nastaveni.json"
NAZVY_NASTAVENI = ["rezim", "claude_model", "api_klic", "jazyk_reci", "jazyk_textu", "titulky_dialogy",
                   "rozlozeni", "kamera_pozice", "kamera_velikost", "nadpis", "priblizeni",
                   "pocet", "min_d", "max_d", "whisper_model", "velka_pismena", "amd", "nazev_hry"]


def nacti_ulozene():
    try:
        return json.loads(SOUBOR_NASTAVENI.read_text(encoding="utf-8"))
    except Exception:
        return {}


def uloz_nastaveni(kontrola, hodnoty):
    data = dict(zip(NAZVY_NASTAVENI, hodnoty))
    data.pop("api_klic", None)                 # klíč se ukládá zvlášť do api_klic.txt
    data["kontrola"] = bool(kontrola)
    try:
        SOUBOR_NASTAVENI.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def zvuk_hotovo():
    """Krátké pípnutí, když je hotovo (ať nemusíš hlídat obrazovku)."""
    if sys.platform.startswith("win"):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass


def stav_html(text):
    return f'<div id="stav">{text}</div>'



SLOUPCE_TABULKY = ["✔", "Začátek", "Konec", "Délka", "Nadpis ve videu", "Název", "Co se tam říká"]


def prepis_useku(slova, od, do):
    return " ".join(w["w"] for w in slova if w["s"] >= od - 0.05 and w["e"] <= do + 0.3)


def radky_tabulky(analyza, pocet):
    radky = []
    for i, k in enumerate(analyza["klipy"]):
        radky.append([i < pocet, cas_presny(k["start"]), cas_presny(k["konec"]),
                      f"{k['konec'] - k['start']:.0f} s", k.get("nadpis", ""), k["nazev"],
                      zkrat(prepis_useku(analyza["slova"], k["start"], k["konec"]), 120)])
    return radky


def je_zaskrtnuto(hodnota):
    return hodnota is True or str(hodnota).strip().lower() in ("true", "1", "ano", "x", "✔")


def radky_z_tabulky(tabulka):
    if tabulka is None:
        return []
    if hasattr(tabulka, "values"):          # kdyby Gradio vrátilo pandas tabulku
        return tabulka.values.tolist()
    return list(tabulka)


def klip_z_radku(analyza, i, radek):
    """Vezme původní návrh č. i a přepíše ho hodnotami, které jsi upravil v tabulce."""
    k = dict(analyza["klipy"][i])
    k["start"] = max(0.0, precti_cas(radek[1]))
    k["konec"] = min(precti_cas(radek[2]), analyza["delka"] or 1e9)
    if k["konec"] - k["start"] < 3:
        raise ValueError(f"Řádek {i + 1}: konec musí být aspoň 3 s po začátku.")
    if k["konec"] - k["start"] > 180:
        raise ValueError(f"Řádek {i + 1}: klip je delší než 3 minuty.")
    k["nadpis"] = bez_emoji(str(radek[4] or ""))[:60]
    k["nazev"] = str(radek[5] or "").strip() or k["nazev"]
    return k


def vytvor_okno():
    import gradio as gr

    ul = nacti_ulozene()                       # naposledy použité nastavení

    def u(nazev, vychozi, moznosti=None):
        """Hodnota z uloženého nastavení (pokud je platná), jinak výchozí."""
        h = ul.get(nazev, vychozi)
        if moznosti is not None and h not in moznosti:
            return vychozi
        return h

    def ukaz_klic(r):
        return gr.Textbox(visible=str(r).startswith("Claude"))

    def ukaz_dialogy(j):
        return gr.Checkbox(visible=JAZYKY_RECI.get(j) == "mix")

    def ukaz_kameru(r):
        viditelne = ROZLOZENI.get(r) == "kamera"
        return gr.Dropdown(visible=viditelne), gr.Slider(visible=viditelne)

    # ---------- velké tlačítko ----------
    def spustit(text, soubory, kontrola, *hodnoty):
        uloz_nastaveni(kontrola, hodnoty)
        nast = sloz_nastaveni(*hodnoty)
        vstupy = nacti_vstupy(text, soubory)
        skryj = gr.Column(visible=False)
        # výstupy: stav, výpis, soubory, panel kontroly, tabulka, analýza, složka
        if not vstupy:
            yield (stav_html("👆 Nejdřív vlož odkaz na YouTube nebo vyber video."),
                   gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip())
            return

        if kontrola and len(vstupy) == 1:
            prace = lambda log: analyzuj(vstupy[0], nast, log, nast["pocet"] + NAVRHU_NAVIC)
            prvni = True
            for vypis, hotovo, vysl, stav in na_pozadi(prace):
                if not hotovo:
                    yield (stav_html(stav), vypis, None, skryj if prvni else gr.skip(),
                           gr.skip(), gr.skip(), gr.skip())
                    prvni = False
                elif vysl:
                    zvuk_hotovo()
                    yield (stav_html(f"👇 Našel jsem {tvar(len(vysl['klipy']), 'moment', 'momenty', 'momentů')} – zkontroluj je níže "
                                     "a klikni na „Vytvořit zaškrtnuté klipy“."),
                           vypis, None, gr.Column(visible=True), radky_tabulky(vysl, nast["pocet"]),
                           vysl, gr.skip())
                else:
                    yield stav_html(stav), vypis, None, gr.skip(), gr.skip(), gr.skip(), gr.skip()
        else:
            for vypis, hotovo, vysl, stav in na_pozadi(lambda log: zpracuj_vse(vstupy, nast, log)):
                if hotovo and vysl:
                    zvuk_hotovo()
                    stav = f"🎉 Hotovo! Vytvořeno: {tvar(sum(1 for f in vysl if f.endswith('.mp4')), 'klip', 'klipy', 'klipů')}."
                slozka = str(Path(vysl[0]).parent) if (hotovo and vysl) else gr.skip()
                yield (stav_html(stav), vypis, (gr.File(value=vysl, visible=True) if (hotovo and vysl) else gr.skip()), skryj,
                       gr.skip(), gr.skip(), slozka)

    # ---------- vytvoření klipů po kontrole ----------
    def vytvorit_vybrane(analyza, tabulka, *hodnoty):
        nast = sloz_nastaveni(*hodnoty)
        if not analyza:
            yield stav_html("👆 Nejdřív klikni na „Najít nejlepší momenty“."), gr.skip(), None, gr.skip()
            return
        try:
            klipy = [klip_z_radku(analyza, i, r) for i, r in enumerate(radky_z_tabulky(tabulka))
                     if i < len(analyza["klipy"]) and je_zaskrtnuto(r[0])]
        except ValueError as e:
            yield stav_html(f"❌ {e}"), gr.skip(), None, gr.skip()
            return
        if not klipy:
            yield stav_html("❌ Není zaškrtnutý žádný klip."), gr.skip(), None, gr.skip()
            return

        def prace(log):
            soubory, slozka = vyrob_klipy(analyza, klipy, nast, log)
            otevri_slozku(slozka)
            return soubory

        for vypis, hotovo, vysl, stav in na_pozadi(prace):
            if hotovo and vysl:
                zvuk_hotovo()
                stav = f"🎉 Hotovo! Vytvořeno: {tvar(len(vysl) - 1, 'klip', 'klipy', 'klipů')}. Názvy a popisy jsou v popisky.txt."
            slozka = str(Path(vysl[0]).parent) if (hotovo and vysl) else gr.skip()
            yield stav_html(stav), vypis, (gr.File(value=vysl, visible=True) if (hotovo and vysl) else gr.skip()), slozka

    # ---------- náhled ----------
    def zapamatuj_radek(evt: gr.SelectData):
        radek = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        return radek, f"Vybraný řádek: **{radek + 1}** – klikni na „Ukázat náhled“."

    def nahled(analyza, tabulka, radek, *hodnoty):
        if not analyza:
            raise gr.Error("Nejdřív najdi momenty.")
        radky = radky_z_tabulky(tabulka)
        radek = int(radek or 0)
        if radek >= len(radky) or radek >= len(analyza["klipy"]):
            raise gr.Error("Klikni nejdřív do řádku v tabulce.")
        try:
            k = klip_z_radku(analyza, radek, radky[radek])
        except ValueError as e:
            raise gr.Error(str(e))
        nast = sloz_nastaveni(*hodnoty)
        slozka = Path(analyza["slozka"]) / "nahledy"
        slozka.mkdir(exist_ok=True)
        for stary in slozka.glob("nahled_*.mp4"):
            try:
                stary.unlink()
            except OSError:
                pass
        cil = slozka / f"nahled_{int(time.time() * 1000)}.mp4"
        vzruseni = np.load(Path(analyza["slozka"]) / "vzruseni.npy")
        try:
            vyrenderuj_klip(analyza["video"], k, analyza["slova"], vzruseni, analyza["fps"],
                            nast, cil, print, nahled=True)
        except Exception as e:
            raise gr.Error(f"Náhled se nepovedl: {e}")
        return str(cil)

    def otevrit(slozka):
        cil = Path(slozka) if slozka else VYSTUP_DIR
        cil.mkdir(parents=True, exist_ok=True)
        otevri_slozku(cil)
        if not sys.platform.startswith("win"):
            gr.Info(f"Klipy jsou ve složce: {cil}")

    with gr.Blocks(title="Shorts Maker") as okno:
        analyza = gr.State(None)
        vybrany_radek = gr.State(0)
        posledni_slozka = gr.State("")

        gr.HTML("""
        <div id="hero">
          <h1>🎬 <span style="background-image: linear-gradient(100deg, #8b5cf6 0%, #ec4899 55%, #f97316 100%); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; color: transparent;">Shorts Maker</span></h1>
          <p>Vlož video a klikni na tlačítko. Zbytek udělám já.</p>
        </div>""")

        # ===== HLAVNÍ ČÁST: jen vložit video a kliknout =====
        with gr.Column(elem_classes="karta"):
            gr.HTML('<div class="nadpis-karty"><span>1</span>Vlož video</div>'
                    '<div class="napoveda">Odkaz na YouTube, nebo přetáhni MP4 soubor do pole pod tím. '
                    '(Víc videí najednou = každý odkaz na nový řádek.)</div>')
            vstup_text = gr.Textbox(show_label=False, container=False, lines=1, max_lines=8,
                                    placeholder="Sem vlož odkaz, např. https://www.youtube.com/watch?v=…",
                                    elem_id="vstup")
            nahrane = gr.File(label="…nebo sem přetáhni video ze složky", file_types=["video"],
                              type="filepath", file_count="multiple", height=140)

        tlacitko = gr.Button("🚀  Najít nejlepší momenty", variant="primary", elem_id="spustit")
        stav = gr.HTML(stav_html("Připraveno. Vlož video a klikni na tlačítko výše."))

        # ===== KONTROLA NÁVRHŮ (ukáže se po analýze) =====
        with gr.Column(elem_classes="karta", visible=False) as panel_kontroly:
            gr.HTML('<div class="nadpis-karty"><span>2</span>Vyber klipy</div>'
                    '<div class="napoveda">Odškrtni, co nechceš. Pro náhled klikni do řádku a na '
                    '„Ukázat náhled“. Čas, nadpis i název můžeš přepsat dvojklikem.</div>')
            tabulka = gr.Dataframe(headers=SLOUPCE_TABULKY,
                                   datatype=["bool", "str", "str", "str", "str", "str", "str"],
                                   type="array", interactive=True, wrap=True, static_columns=[3, 6],
                                   elem_id="tabulka",
                                   column_widths=["6%", "10%", "10%", "8%", "20%", "22%", "24%"])
            with gr.Row():
                with gr.Column(scale=1):
                    tlacitko_vytvorit = gr.Button("🎬  Vytvořit zaškrtnuté klipy", variant="primary",
                                                  elem_id="vytvorit")
                    info_radek = gr.Markdown("Klikni do řádku v tabulce a pak na „Ukázat náhled“.")
                    tlacitko_nahled = gr.Button("👁️  Ukázat náhled")
                with gr.Column(scale=1):
                    video_nahled = gr.Video(label="Náhled", height=480, autoplay=True)

        # ===== VÝSLEDKY =====
        with gr.Row():
            soubory = gr.File(label="Hotové klipy", file_count="multiple", height=170, scale=3, visible=False)
            tlacitko_slozka = gr.Button("📂  Otevřít složku s klipy", scale=1)
        with gr.Accordion("📋 Podrobný výpis (pro hledání chyb)", open=False):
            vypis = gr.Textbox(show_label=False, lines=12, max_lines=30, autoscroll=True,
                               elem_id="vypis", placeholder="Tady uvidíš, co program právě dělá…")

        # ===== NASTAVENÍ (schované, pamatuje si se) =====
        with gr.Accordion("⚙️  Nastavení – není potřeba měnit, program si ho pamatuje", open=False,
                          elem_classes="karta-pokrocile"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("**🗣️ Jazyk**")
                    jazyk_reci = gr.Dropdown(list(JAZYKY_RECI), label="Jazyk řeči ve videu",
                                             value=u("jazyk_reci", "Čeština", list(JAZYKY_RECI)))
                    titulky_dialogy = gr.Checkbox(value=u("titulky_dialogy", True),
                                                  visible=JAZYKY_RECI.get(u("jazyk_reci", "Čeština")) == "mix",
                                                  label="Titulky i pro anglické dialogy postav (modře)")
                    jazyk_textu = gr.Radio(list(JAZYKY_TEXTU), label="Jazyk názvů a nadpisu "
                                                                     "(překlad umí jen Claude AI)",
                                           value=u("jazyk_textu", "Čeština", list(JAZYKY_TEXTU)))
                    gr.Markdown("**🔥 Výběr momentů**")
                    rezim = gr.Radio(["Zdarma (bez AI)", "Claude AI (placené)"], show_label=False,
                                     value=u("rezim", "Zdarma (bez AI)",
                                             ["Zdarma (bez AI)", "Claude AI (placené)"]))
                    api_klic = gr.Textbox(label="Claude API klíč (stačí jednou)", type="password",
                                          placeholder="sk-ant-…",
                                          visible=str(u("rezim", "")).startswith("Claude"))
                    kontrola = gr.Checkbox(value=u("kontrola", True),
                                           label="Před vytvořením ukázat návrhy ke kontrole")
                with gr.Column():
                    gr.Markdown("**🎨 Vzhled klipu**")
                    rozlozeni = gr.Radio(list(ROZLOZENI), label="Převod na svislé video",
                                         value=u("rozlozeni", "Oříznout na střed", list(ROZLOZENI)))
                    je_kamera = ROZLOZENI.get(u("rozlozeni", "")) == "kamera"
                    kamera_pozice = gr.Dropdown(POZICE_KAMERY, visible=je_kamera,
                                                label="Kde je ve videu tvoje kamera",
                                                value=u("kamera_pozice", POZICE_KAMERY[0], POZICE_KAMERY))
                    kamera_velikost = gr.Slider(10, 50, step=1, visible=je_kamera,
                                                value=u("kamera_velikost", 25),
                                                label="Velikost kamery (% šířky) – ověř v náhledu")
                    nadpis = gr.Checkbox(value=u("nadpis", True), label="Velký nadpis v prvních 3 sekundách")
                    priblizeni = gr.Checkbox(value=u("priblizeni", True),
                                             label="Přiblížení obrazu v akčních momentech")
                    velka_pismena = gr.Checkbox(value=u("velka_pismena", True), label="Titulky VELKÝMI PÍSMENY")
            with gr.Accordion("🔧 Pro pokročilé", open=False):
                with gr.Row():
                    with gr.Column():
                        pocet = gr.Slider(5, 15, value=u("pocet", 8), step=1, label="Počet klipů")
                        min_d = gr.Slider(15, 60, value=u("min_d", 20), step=1, label="Minimální délka klipu (s)")
                        max_d = gr.Slider(20, 90, value=u("max_d", 60), step=1, label="Maximální délka klipu (s)")
                        nazev_hry = gr.Textbox(label="Název hry (pro hashtagy)", value=u("nazev_hry", ""),
                                               placeholder="např. GTA 6")
                    with gr.Column():
                        modely_prepisu = [("small – rychlý, dobrý (doporučeno)", "small"),
                                          ("large-v3-turbo – přesnější, asi 2× pomalejší", "large-v3-turbo"),
                                          ("medium – přesnější, nejpomalejší", "medium")]
                        whisper_model = gr.Dropdown(modely_prepisu, label="Přesnost přepisu řeči",
                                                    value=u("whisper_model", "small",
                                                            [m[1] for m in modely_prepisu]))
                        claude_model = gr.Dropdown([(m[0], m[1]) for m in CLAUDE_MODELY], label="Model Claude",
                                                   value=u("claude_model", CLAUDE_MODELY[0][1],
                                                           [m[1] for m in CLAUDE_MODELY]))
                        amd = gr.Checkbox(value=u("amd", True), label="Kódovat video grafikou AMD (rychlejší)")

        # Pořadí musí odpovídat parametrům funkce sloz_nastaveni() a NAZVY_NASTAVENI
        nastaveni = [rezim, claude_model, api_klic, jazyk_reci, jazyk_textu, titulky_dialogy,
                     rozlozeni, kamera_pozice, kamera_velikost, nadpis, priblizeni,
                     pocet, min_d, max_d, whisper_model, velka_pismena, amd, nazev_hry]

        rezim.change(ukaz_klic, rezim, api_klic)
        jazyk_reci.change(ukaz_dialogy, jazyk_reci, titulky_dialogy)
        rozlozeni.change(ukaz_kameru, rozlozeni, [kamera_pozice, kamera_velikost])

        tlacitko.click(spustit, [vstup_text, nahrane, kontrola] + nastaveni,
                       [stav, vypis, soubory, panel_kontroly, tabulka, analyza, posledni_slozka])
        tabulka.select(zapamatuj_radek, None, [vybrany_radek, info_radek])
        tlacitko_nahled.click(nahled, [analyza, tabulka, vybrany_radek] + nastaveni, video_nahled)
        tlacitko_vytvorit.click(vytvorit_vybrane, [analyza, tabulka] + nastaveni,
                                [stav, vypis, soubory, posledni_slozka])
        tlacitko_slozka.click(otevrit, posledni_slozka, None)
    return okno



def vzhled():
    """Barevné téma okna (tmavé, fialovo-růžové)."""
    import gradio as gr
    return gr.themes.Base(
        primary_hue="violet", secondary_hue="pink", neutral_hue="slate", radius_size="lg",
        font=[gr.themes.GoogleFont("Inter"), "Segoe UI", "system-ui", "sans-serif"],
    )


if __name__ == "__main__":
    print("Spouštím Shorts Maker… okno se otevře v prohlížeči.")
    print("Tohle černé okno NEZAVÍREJ, dokud program používáš.")
    vytvor_okno().queue().launch(inbrowser=True, allowed_paths=[str(VYSTUP_DIR), str(PRACOVNI_DIR)],
                                 theme=vzhled(), css=VZHLED_CSS, js=VZHLED_JS)
