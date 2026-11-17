# Shorts Maker: návod

Program udělá z dlouhého streamu (odkaz na YouTube nebo MP4 soubor) 5–15 svislých klipů
(1080×1920) s titulky ve stylu TikToku. Ke každému klipu napíše název a popis.

Nastavení je pro **Windows 10/11, grafiku AMD Radeon a 16 GB RAM**. Přepis řeči
poběží na procesoru, protože faster-whisper umí grafiku jen od NVIDIE. Grafika AMD se ale
použije na rychlejší kódování hotových videí.

---

## 1. Instalace a spuštění: jen 2 kroky

**Krok 1: Stáhni program.** Otevři tento odkaz (musíš být přihlášený na GitHubu):
https://github.com/CoreyCZ/muj_git/archive/refs/heads/claude/intelligent-ptolemy-xtvpag.zip

Stažený ZIP otevři, klikni na **Extrahovat vše** a rozbal ho třeba na plochu.

**Krok 2: Dvakrát klikni na `START.bat`.** Najdeš ho v rozbalené složce v podsložce `shorts_maker`.
* Když Windows napíše „Systém Windows ochránil váš počítač“, klikni na **Další informace → Přesto spustit**.
* Když se zeptá, jestli povolit změny, klikni na **Ano**.
* Při prvním spuštění se samo nainstaluje vše potřebné (Python, FFmpeg a knihovny). Trvá to 10–20 minut.
  Potom se v prohlížeči otevře stránka programu.
* Příště už jen dvakrát klikneš na `START.bat` a program se otevře za pár vteřin.

Černé okno, které se otevře, **nezavírej**, dokud program používáš.

## 2. Použití

1. **Video:** vlož odkaz na YouTube nebo cestu k souboru. Cestu zkopíruješ tak, že na video
   klikneš pravým tlačítkem a vybereš **Kopírovat jako cestu**.
   Víc videí najednou: každé dej na nový řádek. Zpracují se automaticky jedno po druhém,
   třeba přes noc.
2. **Jazyk:**
   * *Jazyk řeči ve videu*: **Čeština**, **Angličtina**, nebo **Čeština + angličtina**
     (ty mluvíš česky a postavy ve hře anglicky). U mixu můžeš zvolit, jestli mají mít
     titulky i anglické dialogy. Ty se pak zobrazí světle modře.
   * *Jazyk názvů, popisů a nadpisu*: **Čeština** nebo **English**. Přeložit do jiného jazyka
     než ve videu umí jen režim Claude AI.
3. **Vzhled klipu:**
   * **Oříznout na střed**, **Rozostřené pozadí** (vidět je celý obraz hry), nebo
     **Kamera nahoře + hra dole**. U kamery zvol, ve kterém rohu videa je, a podle náhledu
     dolaď její velikost.
   * **Velký nadpis** v prvních 3 sekundách, aby divák neodscrolloval.
   * **Přiblížení** obrazu v nejhlasitějších momentech (výbuchy, výkřiky).
4. Klikni na **🚀 Spustit**.
5. **Kontrola návrhů:** zobrazí se tabulka s návrhy (o pár víc, než kolik chceš klipů).
   * Odškrtni klipy, které nechceš.
   * Dvojklikem do buňky můžeš přepsat začátek, konec, nadpis nebo název.
   * Klikni do řádku a pak na **👁️ Ukázat náhled**, uvidíš, jak bude klip vypadat.
   * Nakonec klikni na **🎬 Vytvořit zaškrtnuté klipy**.
6. Otevře se složka s hotovými klipy a souborem `popisky.txt` (názvy, popisy, hashtagy).

Kontrolu návrhů můžeš vypnout zaškrtávátkem v kartě „Video“. Klipy se pak vytvoří rovnou.

### Tipy pro GTA a jiné hry

* **Rádio v autě vypni nebo ztiš.** Licencovaná hudba spustí na YouTube nárok na autorská
  práva a TikTok může ztlumit zvuk.
* **Na PS5 nahrávej bez HDR**, jinak video na PC vypadá vybledle.
* Program nejlépe funguje, když u hraní **mluvíš**. Hlášky, smích a výkřiky mu napoví,
  kde je dobrý moment.
* Ideální délka klipu je 20–45 s. Nejdůležitější jsou první 2 sekundy.

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
| `START.bat` hlásí chybu při instalaci | Restartuj počítač a spusť `START.bat` znovu. Pokračuje tam, kde skončil. |
| `Nenašel jsem program ffmpeg` | Restartuj počítač a spusť `START.bat` znovu. |
| Chyba při stahování z YouTube (`Sign in to confirm`, `HTTP Error 403`, `n challenge`) | Zavři program a spusť `START.bat` znovu, sám aktualizuje stahovač. Jde o tvoje video? Pak si ho můžeš stáhnout v YouTube Studiu (Obsah → ⋮ → Stáhnout) a vložit cestu k souboru. |
| `Could not load library…`, `DLL load failed` | Restartuj počítač a spusť `START.bat` znovu (doinstaluje chybějící součásti Windows). |
| Přepis je moc pomalý | Zvol model `small`. Pak už jen nech program běžet, přepis se dělá jen jednou. |
| `MemoryError` / počítač se zasekne | Zavři ostatní programy (hlavně hry a prohlížeč s mnoha panely), použij model `small`. |
| `Kódování přes AMD grafiku nejde` | Nic se neděje, program automaticky použije procesor. Můžeš odškrtnout volbu AMD. |
| `API klíč je neplatný` | Zkontroluj klíč na console.anthropic.com, nebo smaž `api_klic.txt` a vlož klíč znovu. |
| `Výběr přes Claude se nepovedl` | Program sám pokračuje variantou zdarma. Nejčastější příčiny jsou chybějící kredit nebo internet. |
| Titulky jsou posunuté nebo jinak chybné | Zvol přesnější model přepisu (`large-v3-turbo`). |
| Stránka se neotevře / port je obsazený | Zavři všechna černá okna programu a spusť `START.bat` znovu. |

Při každé chybě vypíše program dole v okně **technické detaily**. Když si nebudeš vědět rady,
zkopíruj celý text z pole „Průběh“ a pošli mi ho.

---

## 5. Úpravy vzhledu

Na začátku souboru `shorts_maker.py` (otevři ho v Poznámkovém bloku) je část **NASTAVENÍ**:

* `TITULKY_VELIKOST`, `TITULKY_FONT`, `TITULKY_OD_SPODU`: velikost, písmo a výška titulků,
* `BARVA_ZVYRAZNENI`: barva aktuálního slova. Píše se ve formátu `&H00BBGGRR&`, tedy obráceně
  (modrá, zelená, červená). Žlutá je `&H0000FFFF&`, zelená `&H0000FF00&`, růžová `&H00FF00FF&`.
* `KLICOVA_SLOVA_CS` / `KLICOVA_SLOVA_EN`: tvoje oblíbené hlášky, které mají zvýšit šanci na výběr,
* `NADPIS_VELIKOST`, `NADPIS_DELKA`: velikost a délka zobrazení úvodního nadpisu,
* `PRIBLIZENI_SILA`, `PRIBLIZENI_PRAH`: jak moc a jak často se obraz přibližuje.
