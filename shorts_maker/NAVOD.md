# Shorts Maker: návod

Program udělá z dlouhého streamu (odkaz na YouTube nebo MP4 soubor) 5–15 svislých klipů
(1080×1920) s titulky ve stylu TikToku. Ke každému klipu napíše název a popis.

Nastavení je pro **Windows 10/11, grafiku AMD Radeon a 16 GB RAM**. Přepis řeči
poběží na procesoru, protože faster-whisper umí grafiku jen od NVIDIE. Grafika AMD se ale
použije na rychlejší kódování hotových videí.

---

## 1. Instalace (jen jednou)

Otevři **Příkazový řádek**: stiskni klávesu Windows, napiš `cmd` a stiskni Enter.
Do okna postupně vlož tyto příkazy. Každý potvrď Enterem a počkej, až doběhne.

```
winget install --id Python.Python.3.12 -e
winget install --id Gyan.FFmpeg -e
winget install --id DenoLand.Deno -e
```

* **Python 3.12**: programovací jazyk, ve kterém je program napsaný.
* **FFmpeg**: stříhá a převádí video.
* **Deno**: bez něj už nástroj yt-dlp neumí stahovat z YouTube.

Potom **zavři příkazový řádek a otevři ho znovu**, aby Windows nové programy našel. Pro kontrolu:

```
py -3.12 --version
ffmpeg -version
```

Oba příkazy musí vypsat číslo verze, nesmí napsat „není rozpoznán“.

### Stažení programu

Na GitHubu otevři repozitář, klikni na **Code → Download ZIP** a rozbal ho třeba do `C:\ShortsMaker`.
Ve složce `shorts_maker` musí být soubory `shorts_maker.py`, `instalace.bat`, `spustit.bat` a `requirements.txt`.

### Instalace knihoven

Dvakrát klikni na **`instalace.bat`**. Instalace trvá několik minut a stáhne asi 1 GB.
Až se objeví „Hotovo“, stiskni libovolnou klávesu.

---

## 2. Spuštění

1. Dvakrát klikni na **`spustit.bat`**. Otevře se černé okno (to **nezavírej**) a v prohlížeči stránka programu.
   Kdyby se stránka neotevřela, zadej do prohlížeče adresu `http://127.0.0.1:7860`.
2. Do horního pole vlož **odkaz na YouTube** nebo **cestu k souboru**, např. `C:\Videa\stream.mp4`.
   Cestu zkopíruješ tak, že na soubor klikneš pravým tlačítkem a vybereš „Kopírovat jako cestu“.
   U velkých souborů je vložení cesty mnohem rychlejší než přetažení souboru do okna.
3. Nastav počet klipů, jejich délku a vzhled. Pak klikni na **🚀 Spustit**.
4. Ve spodním poli uvidíš průběh. Na konci se otevře složka `vystup\...` s hotovými klipy a souborem `popisky.txt`.

### Jak dlouho to trvá (3hodinový stream, běžný 6–8jádrový procesor)

| Krok | Přibližný čas |
|---|---|
| Stažení z YouTube | 5–30 min (podle internetu) |
| Přepis řeči, model `small` | asi 30–60 min |
| Přepis řeči, model `large-v3-turbo` | asi 1–2 h |
| Výběr momentů | do 1 min (zdarma) nebo 1–3 min (Claude) |
| Vytvoření 1 klipu | 10–60 s |

Přepis se ukládá, takže když stejné video zpracuješ znovu (např. s jiným nastavením nebo přes Claude),
**přepis se už nedělá** a máš klipy za pár minut.

---

## 3. Výběr momentů: zdarma, nebo s Claude AI

**a) Zdarma (bez AI):** program dá každému úseku body podle
* hlasitosti oproti okolí (výkřiky, smích, výbuchy),
* emotivních slov a hlášek („ty vole“, „to snad ne“, „haha“, „mám ho“…; seznam `KLICOVA_SLOVA` si můžeš upravit na začátku souboru),
* tempa řeči (ticho dostává mínusové body) a silného začátku.

Názvy klipů se berou přímo z přepisu, takže jsou jednodušší.

**b) Claude AI (placené):** Claude dostane celý přepis s úrovněmi hlasitosti. Vybere pasáže,
kterým rozumí i divák, který stream neviděl, a napíše chytlavé názvy, popisy a hashtagy.

Jak získat API klíč: zaregistruj se na **console.anthropic.com**, v sekci *Billing* nabij kredit
(stačí 5 $) a v sekci *API Keys* vytvoř klíč. Vlož ho do okna programu. Program si ho uloží do `api_klic.txt`.

**Kolik to stojí na jeden 3hodinový stream** (přepis má zhruba 80–120 tisíc tokenů):

| Model | Cena za 1 stream |
|---|---|
| Claude Opus 5.5 (nejchytřejší) | asi 0,45–0,70 $ ≈ 10–16 Kč |
| Claude Sonnet 5.5 | asi 0,25–0,35 $ ≈ 5–8 Kč |
| Claude Haiku 5.5 (nejlevnější) | asi 0,02–0,08 $ ≈ 0,5–2 Kč |

Přesnou cenu každého spuštění vypíše program do průběhu.

---

## 4. Když se objeví chyba

| Hláška | Co udělat |
|---|---|
| `'py' není rozpoznán…` | Python není nainstalovaný. Spusť znovu `winget install --id Python.Python.3.12 -e` a otevři nový příkazový řádek. |
| `Nenašel jsem program ffmpeg` | `winget install --id Gyan.FFmpeg -e`, pak zavři a znovu spusť `spustit.bat`. Když to nepomůže, restartuj počítač. |
| Chyba při stahování z YouTube (`Sign in to confirm`, `HTTP Error 403`, `n challenge`) | Spusť znovu `instalace.bat` (aktualizuje yt-dlp) a ověř, že je nainstalované Deno. Jde o tvoje video? Pak si ho můžeš stáhnout v YouTube Studiu (Obsah → ⋮ → Stáhnout) a vložit cestu k souboru. |
| `Could not load library…`, `DLL load failed` | Nainstaluj „Microsoft Visual C++ Redistributable“: `winget install --id Microsoft.VCRedist.2015+.x64 -e` |
| Přepis je moc pomalý | Zvol model `small`. Pak už jen nech program běžet, přepis se dělá jen jednou. |
| `MemoryError` / počítač se zasekne | Zavři ostatní programy (hlavně hry a prohlížeč s mnoha panely), použij model `small`. |
| `Kódování přes AMD grafiku nejde` | Nic se neděje, program automaticky použije procesor. Můžeš odškrtnout volbu AMD. |
| `API klíč je neplatný` | Zkontroluj klíč na console.anthropic.com, nebo smaž `api_klic.txt` a vlož klíč znovu. |
| `Výběr přes Claude se nepovedl` | Program sám pokračuje variantou zdarma. Nejčastější příčiny jsou chybějící kredit nebo internet. |
| Titulky jsou posunuté nebo jinak chybné | Zvol přesnější model přepisu (`large-v3-turbo`). |
| Stránka se neotevře / port je obsazený | Zavři všechna černá okna programu a spusť `spustit.bat` znovu. |

Při každé chybě vypíše program dole v okně **technické detaily**. Když si nebudeš vědět rady,
zkopíruj celý text z pole „Průběh“ a pošli mi ho.

---

## 5. Úpravy vzhledu

Na začátku souboru `shorts_maker.py` (otevři ho v Poznámkovém bloku) je část **NASTAVENÍ**:

* `TITULKY_VELIKOST`, `TITULKY_FONT`, `TITULKY_OD_SPODU`: velikost, písmo a výška titulků,
* `BARVA_ZVYRAZNENI`: barva aktuálního slova. Píše se ve formátu `&H00BBGGRR&`, tedy obráceně
  (modrá, zelená, červená). Žlutá je `&H0000FFFF&`, zelená `&H0000FF00&`, růžová `&H00FF00FF&`.
* `KLICOVA_SLOVA`: tvoje oblíbené hlášky, které mají zvýšit šanci na výběr.
