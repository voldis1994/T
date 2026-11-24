# SHADOW — Capital.com treidinga robots

Automātisks 1m supply/demand + struktūras robots ar profesionālu dashboard.  
Pieslēgums caur **Capital.com REST API**. Plūsma: tu atver pirmo treidu app → robots pārņem.

## Ātrais starts

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # aizpildi API datus (vai palaid paper režīmā bez tiem)
python -m shadow.main
```

Atver **http://127.0.0.1:8080**

### Bez API atslēgām
Dashboard strādā **paper** režīmā ar sintētisku EURUSD. Spied **Simulēt pirmo treidu** — tas ir handover.

### Ar Capital.com
1. Settings → API Integrations → Generate key  
2. Ievadi atslēgu, e-pastu un API paroli dashboard formā (vai `.env`)  
3. Izvēlies `demo` vai `live`  
4. Atver **pirmo treidu** Capital.com app uz to pašu instrumentu  
5. Robots ierauga pozīciju, uzliek strukturālo SL/TP un turpina tirgot

## Stratēģijas edge (no tavām shēmām)

| Modulis | Ko dara |
|---------|---------|
| `structure.py` | HH/HL/LH/LL, BOS, CHOCH |
| `zones.py` | Base → impulse supply/demand zonas + kvalitāte |
| `candles.py` | Pin bar, engulfing, impulse, rejection series |
| `scenarios.py` | TREND / RANGE / BREAKOUT / RETEST / REVERSAL / FAKEOUT |
| `brackets.py` | Strukturāls SL/TP katram režīmam, min R:R 1.5 |
| `fusion.py` | Confluence score + decision feature vector |
| `brain.py` | Lēmumu vārti (data, regime, news, session, RR, handover) |
| `handover.py` | Gaida tavu pirmo app treidu, tad ACTIVE |

**Limiti:** nav dienas zaudējumu / treidu skaita / riska % limitu (pēc tava pieprasījuma).  
Katram treidam joprojām ir **metodikas SL/TP** — bez tiem nav edge.

## Dashboard

Viss paredzams vienā skatā: cena, signāls, regime, confluence, lēmumu vārti, zonas, SL/TP, pozīcijas, konts, žurnāls, API forma.

## API (lokāli)

- `GET /api/state` — pilns stāvoklis  
- `WS /ws` — live plūsma  
- `POST /api/handover/simulate` — `{ "direction": "BUY" }`  
- `POST /api/credentials` — pieslēgt Capital.com  

## Brīdinājums

CFD/Forex ir risks. DEMO vispirms. LIVE orderi iet caur tavu Capital.com kontu.