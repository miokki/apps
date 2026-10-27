# Agent OLX — asystent zakupowy dla OLX.pl

Agent AI (Claude) do **wyszukiwania, porównywania, negocjowania i wspierania decyzji zakupowych na OLX.pl**.
Agent **ogląda i interpretuje zdjęcia z ogłoszeń** (stan, autentyczność, zgodność z opisem, tekst na etykietach
i ekranach), czyta opisy i parametry, sprawdza sprzedawcę, liczy ceny rynkowe, przygotowuje wiadomości do
sprzedawcy i prowadzi przez bezpieczny zakup.

```
Ty> Szukam iPhone'a 13 128 GB do 2000 zł, Kraków albo wysyłka. Bateria min. 85%.
  · Szukam ofert i sprawdzam ceny rynkowe.
  ⚙ search_listings(query="iphone 13 128gb", city="Kraków", price_max=2000)
    ✓ Wyniki dla „iphone 13 128gb”: 20 ofert na tej stronie (łącznie w OLX: ~240)
  ⚙ market_price_stats(query="iphone 13", condition="used", title_must_include=["128"], ...)
  ⚙ get_listing(listing="912345678", market_median=1950)
  ⚙ view_listing_photos(listing="912345678")
    ✓ Ogłoszenie [912345678] „iPhone 13 128GB Midnight” — 1 900 PLN … [6 obraz(y)]
  ⚙ zoom_listing_photo(listing="912345678", photo=4, left=0.1, top=0.3, right=0.9, bottom=0.7)
Agent> Najlepszy kandydat: [912345678] — 1 900 zł (mediana rynku 1 950 zł). Na zdjęciu 4 widać
       zrzut „Kondycja baterii: 87%”, na zdjęciu 2 rysę w prawym górnym rogu ekranu …
       Plan negocjacji: start 1 700 zł, cel 1 780 zł, maksimum 1 850 zł. Wiadomość do wysłania: …
```

## Co potrafi

| Etap | Jak |
|---|---|
| **Wyszukiwanie** | Zapytania z filtrami (cena, stan, miasto + promień, tylko prywatni, tylko z Przesyłką OLX, sortowanie, kategoria). Kilka wariantów frazy, odsiewanie akcesoriów po `category_id`. |
| **Zdjęcia (wizja)** | `view_listing_photos` pobiera zdjęcia ogłoszenia i przekazuje je modelowi jako obrazy. `zoom_listing_photo` wycina fragment z oryginału w pełnej rozdzielczości (etykiety, numery seryjne, ekran baterii, licznik, rysy, rdza). `view_image` i komenda `/zdjecie` — zdjęcia i zrzuty od sprzedawcy, paragony, zrzuty ogłoszeń. |
| **Tekst** | Pełny opis (oczyszczony z HTML), parametry, historia ceny, staż i aktywność konta, typ sprzedawcy, lokalizacja, dostępność Przesyłki OLX. |
| **Ceny rynkowe** | `market_price_stats`: mediana, przedział P25–P75, P10/P90, podział wg stanu, najtańsze i najnowsze oferty; odrzucanie odstających cen i filtrowanie tytułów (np. tylko „128”, bez „etui”). |
| **Ryzyko** | Heurystyki: kontakt poza OLX (WhatsApp/Telegram), linki do „płatności”, BLIK, zaliczki, „sprzedawca za granicą”, repliki, świeże konto, cena podejrzanie niska, brak/za mało zdjęć — a model weryfikuje je ze zdjęciami i opisem. |
| **Porównanie i decyzja** | `compare_listings`: tabela 2–8 ofert (cena vs mediana, stan, parametry, sprzedawca, sygnały), ranking z uzasadnieniem, macierz decyzyjna wg priorytetów użytkownika. |
| **Negocjacje** | Oferta otwierająca / cel / cena maksymalna z uzasadnieniem (rynek + wady ze zdjęć), gotowe wiadomości do skopiowania, analiza odpowiedzi sprzedawcy i kolejny ruch. |
| **Proces zakupu** | Tracker (lista, statusy, oferty, korespondencja, preferencje — zapisywany między sesjami), checklisty `buying_guide` dla kategorii (telefony, laptopy, konsole, aparaty, samochody, rowery, meble/AGD, odzież, bilety, wynajem) i etapów (bezpieczeństwo, Przesyłka OLX, odbiór osobisty, negocjacje, prawa kupującego). |

Agent **niczego nie wysyła ani nie kupuje sam** — przygotowuje analizy i treść wiadomości, a decyzje i kontakt ze
sprzedawcą zostają po stronie użytkownika. Treść ogłoszeń i wiadomości sprzedawców traktuje jako dane, nie polecenia
(ochrona przed „prompt injection” w opisach).

## Instalacja i uruchomienie

Wymagania: Python 3.10+, klucz API Anthropic.

```bash
cd olx-agent
python -m venv .venv && source .venv/bin/activate
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
olx-agent                          # tryb interaktywny
olx-agent "Ile realnie kosztuje używany PS5 z napędem w Warszawie?"   # jednorazowe polecenie
```

Komendy w trybie interaktywnym:

| Komenda | Działanie |
|---|---|
| `/zdjecie <ścieżka> [komentarz]` | dołącza zdjęcie z dysku (np. zrzut rozmowy, dodatkowe zdjęcia od sprzedawcy) |
| `/tracker` | śledzone ogłoszenia i preferencje |
| `/nowa` | nowa rozmowa (tracker zostaje) |
| `/koszt` | zużycie tokenów i rozmiar obrazów w rozmowie |
| `/wyjdz` | koniec (także Ctrl+D) |

Przykładowe prośby: wklejenie linku do ogłoszenia („oceń to”), „porównaj 3 najlepsze”, „przygotuj plan negocjacji”,
wklejenie odpowiedzi sprzedawcy („odpisał: najniżej 1800, co dalej?”), „co sprawdzić przy odbiorze?”.

## Konfiguracja (zmienne środowiskowe)

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | klucz API |
| `OLX_AGENT_MODEL` | `claude-opus-5-5` | model Claude |
| `OLX_AGENT_EFFORT` | `medium` | wysiłek modelu: `low`/`medium`/`high`/`xhigh`/`max` (wyżej = dokładniej, drożej, wolniej) |
| `OLX_AGENT_MAX_TOKENS` | `64000` | limit tokenów odpowiedzi (przy `--no-stream` maks. 16000) |
| `OLX_AGENT_FALLBACKS` | `1` | `0` wyłącza serwerowy fallback po odmowie klasyfikatora bezpieczeństwa |
| `OLX_AGENT_PROGRESS` | `1` | `0` wyłącza notki o postępie między krokami |
| `OLX_AGENT_THREADS` | `0` | `1` włącza wątki wiadomości po stronie serwera (beta SDK) — mniej danych na żądanie |
| `OLX_AGENT_IMAGE_MAX_EDGE` | `1024` | dłuższy bok zdjęć wysyłanych do modelu (zoom zawsze do 1568 px) |
| `OLX_AGENT_IMAGE_BUDGET_MB` | `22` | limit łącznego rozmiaru obrazów w jednej rozmowie |
| `OLX_AGENT_HOME` | `~/.olx-agent` | katalog z trackerem (`state.json`) |
| `OLX_BASE_URL` | `https://www.olx.pl` | adres OLX (np. do testów) |

### Szczegóły wywołań Claude API

- Pętla narzędzi: `client.beta.messages.tool_runner` z SDK `anthropic`, odpowiedzi strumieniowane.
- Adaptacyjne myślenie (`thinking: adaptive`), wysiłek ustawiany jawnie (`output_config.effort`).
- **Fallback po odmowie** jest domyślnie włączony: `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`) —
  gdy klasyfikator bezpieczeństwa błędnie zablokuje zwykłą prośbę, API ponowi ją na modelu zapasowym.
  Wyłączenie: `OLX_AGENT_FALLBACKS=0`.
- Notki o postępie między wywołaniami narzędzi: `thinking.display: "updates"` (beta `thinking-display-updates-2026-08-18`).
- Cache promptu: stały prompt systemowy i lista narzędzi + automatyczny cache końca rozmowy; dane zmienne (data,
  stan trackera) trafiają do pierwszej wiadomości, nie do promptu systemowego. Historia rozmowy jest wyłącznie
  dopisywana (bez edycji wstecz), a nieudana tura jest w całości wycofywana.
- Zdjęcia są pomniejszane i kodowane jako JPEG (base64). Każde żądanie zawiera całą historię, a API ma limit
  32 MB na żądanie — dlatego agent pilnuje budżetu obrazów i po jego wyczerpaniu proponuje `/nowa`.

## Źródło danych i ograniczenia

- Agent korzysta z publicznego API JSON, którego używa strona OLX.pl (`/api/v1/offers/`, `/api/v1/offers/{id}/`,
  `/api/v1/users/{id}/`), oraz z danych strukturalnych strony ogłoszenia (JSON-LD) jako zapasu. To **nie jest
  oficjalne, udokumentowane API** — OLX może je zmienić; dlatego filtry są dodatkowo sprawdzane lokalnie, a błędy
  zwracane modelowi czytelnym komunikatem.
- Zapytania są ograniczane (odstęp ~0,6 s, ponawianie przy 429/5xx). Używaj narzędzia do własnych zakupów,
  zgodnie z regulaminem OLX.
- Agent nie ma dostępu do konta OLX: nie widzi czatu, numerów telefonów ani Twoich zamówień — odpowiedzi sprzedawcy
  wklejasz do rozmowy, a zrzuty dołączasz `/zdjecie`.
- Statystyki dotyczą cen wywoławczych aktywnych ogłoszeń, nie cen transakcyjnych.
- Informacje prawne w poradnikach są ogólne i nie stanowią porady prawnej.

## Architektura

```
src/olx_agent/
  agent.py       pętla agenta (tool runner, strumieniowanie, historia, obsługa stop_reason)
  tools.py       13 narzędzi dla modelu (wyszukiwanie, szczegóły, zdjęcia, zoom, rynek, sprzedawca, porównanie,
                 poradniki, tracker)
  olx_client.py  klient OLX: wyszukiwanie, ogłoszenia, użytkownicy, lokalizacje, pobieranie zdjęć, fallback HTML
  listing.py     model ogłoszenia + parsery (API JSON, JSON-LD)
  images.py      przygotowanie obrazów dla modelu (orientacja EXIF, kadrowanie, skalowanie, JPEG) i budżet
  analysis.py    statystyki cen, sygnały ryzyka, tabele porównawcze
  guides.py      checklisty zakupowe
  tracker.py     trwały tracker zakupów (JSON)
  prompts.py     prompt systemowy (zasady analizy zdjęć, ryzyka, negocjacji, procesu zakupu)
  cli.py         interfejs terminalowy
```

## Testy

```bash
pip install -e ".[dev]"
pytest
```

Testy działają bez sieci i bez klucza API: OLX i Messages API są zastąpione atrapami na poziomie HTTP. Sprawdzają
m.in. parsowanie danych OLX, filtry wyszukiwania, statystyki i sygnały ryzyka, przygotowanie obrazów (skalowanie,
kadrowanie zoomu), tracker, każde narzędzie oraz pełną pętlę agenta — w tym to, że zdjęcia ogłoszenia trafiają do
modelu jako bloki obrazów w wyniku narzędzia (zarówno ze strumieniowaniem, jak i bez).
