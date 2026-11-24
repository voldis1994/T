# SHADOW — Capital.com treidinga robots

Automātisks 1m supply/demand + struktūras robots ar profesionālu dashboard.  
Pieslēgums caur **Capital.com REST API**. Plūsma: tu atver pirmo treidu app → robots pārņem.

## Windows (CMD) — ieteicamais veids

1. Uzliec **Python 3.12 vai 3.13** no [python.org](https://www.python.org/downloads/)  
   (atzīmē **Add python.exe to PATH**). **Izvairies no Python 3.14**, ja iespējams.
2. Atver mapi `T-main` un palaid:

```bat
setup.bat
run.bat
```

3. Atver pārlūkā **http://127.0.0.1:8080**
4. Dashboardā **Reģistrē SHADOW** — ievadi Capital.com API key, e-pastu un API paroli (saglabājas `.env`)

### Ja `pip` rāda Permission denied
Nepalaid `pip` uz sistēmas Python — izmanto `setup.bat` (tas veido `.venv` un `--no-cache-dir`).

### Windows CMD kļūdas (ko NEizmantot)
| Linux / macOS | Windows CMD |
|---|---|
| `cp .env.example .env` | `copy .env.example .env` |
| `PYTHONPATH=. python -m shadow.main` | `run.bat` vai `python start.py` |
| `source .venv/bin/activate` | `.venv\Scripts\activate.bat` |

## Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python start.py
```

## Bez API atslēgām
Dashboard strādā **paper** režīmā. Spied **Simulēt pirmo treidu** — tas ir handover.

## Ar Capital.com
1. Settings → API Integrations → Generate key  
2. Ievadi atslēgu, e-pastu un API paroli dashboard formā (vai `.env`)  
3. Izvēlies `demo` vai `live`  
4. Atver **pirmo treidu** Capital.com app uz to pašu instrumentu  
5. Robots ierauga pozīciju, uzliek strukturālo SL/TP un turpina tirgot

## Stratēģijas edge

| Modulis | Ko dara |
|---------|---------|
| `structure.py` | HH/HL/LH/LL, BOS, CHOCH |
| `zones.py` | Base → impulse supply/demand zonas |
| `candles.py` | Pin bar, engulfing, impulse |
| `scenarios.py` | TREND / RANGE / BREAKOUT / RETEST / REVERSAL / FAKEOUT |
| `brackets.py` | Strukturāls SL/TP, min R:R 1.5 |
| `fusion.py` | Confluence + feature vector |
| `brain.py` | Lēmumu vārti |
| `handover.py` | Gaida pirmo app treidu, tad ACTIVE |

**Limiti:** nav dienas / treidu skaita / riska % limitu. Katram treidam ir metodikas SL/TP.

## API (lokāli)

- `GET /api/state` — pilns stāvoklis  
- `WS /ws` — live plūsma  
- `POST /api/handover/simulate` — `{ "direction": "BUY" }`  
- `POST /api/credentials` — pieslēgt Capital.com  

## Brīdinājums

CFD/Forex ir risks. DEMO vispirms. LIVE orderi iet caur tavu Capital.com kontu.
