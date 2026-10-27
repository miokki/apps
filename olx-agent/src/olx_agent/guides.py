"""Curated buying checklists, loaded on demand by the `buying_guide` tool."""

from __future__ import annotations

from typing import Literal

GuideTopic = Literal[
    "general",
    "safety",
    "olx_delivery",
    "pickup",
    "negotiation",
    "buyer_rights",
    "phones",
    "laptops",
    "consoles",
    "cameras",
    "cars",
    "bikes",
    "furniture_appliances",
    "clothing_luxury",
    "tickets",
    "rentals",
]

GUIDES: dict[str, str] = {
    "general": """\
OGÓLNA CHECKLISTA ZAKUPU NA OLX
Przed kontaktem:
- Porównaj cenę z rynkiem (market_price_stats) i z ceną nowego/odnowionego egzemplarza.
- Obejrzyj wszystkie zdjęcia; sprawdź, czy są własne (nie katalogowe) i spójne ze sobą.
- Przeczytaj opis pod kątem braków: komplet, historia, powód sprzedaży, wady, dowód zakupu.
- Sprawdź profil sprzedawcy: staż konta, inne ogłoszenia, typ (firma/prywatny).
Pierwsza wiadomość:
- Najpierw konkretne pytania (stan, wady, komplet, dowód zakupu), prośba o brakujące zdjęcia.
- Dopiero potem rozmowa o cenie.
Zakup:
- Preferuj Przesyłkę OLX (płatność przez OLX) albo odbiór osobisty z płatnością przy odbiorze.
- Nigdy nie płać przez link z SMS/WhatsApp/e-maila, nie podawaj kodów BLIK ani danych karty.
- Zachowaj zrzuty rozmowy i ogłoszenia do czasu zakończenia transakcji.""",
    "safety": """\
BEZPIECZEŃSTWO I TYPOWE OSZUSTWA
Czerwone flagi:
- Przeniesienie rozmowy na WhatsApp/Telegram/SMS/e-mail, zwłaszcza z „linkiem do odbioru płatności” lub „potwierdzenia przesyłki”.
- Fałszywe strony „OLX/InPost/DPD” proszące o dane karty, logowanie do banku lub kod BLIK. OLX nie wysyła linków do płatności poza aplikacją.
- Prośba o zaliczkę, przedpłatę przelewem lub „opłatę za rezerwację”, szczególnie gdy sprzedawca „jest za granicą”.
- Cena wyraźnie poniżej rynku przy towarach płynnych (telefony, konsole, laptopy, karty graficzne, bilety).
- Świeże konto, wiele identycznych drogich przedmiotów, zdjęcia katalogowe lub skradzione z innych ogłoszeń.
- Presja czasu („dziś muszę sprzedać”, „jest kilku chętnych, kto pierwszy wpłaci”).
- Wymyślne metody dostawy („mój kurier odbierze”, „wyślę przez firmę transportową, zapłać przez link”).
Zasady:
- Płać tylko w systemie OLX (Przesyłka OLX) albo przy odbiorze po sprawdzeniu towaru.
- Nie klikaj linków od sprzedającego/kupującego; nie loguj się do banku z linku.
- Przy podejrzeniu oszustwa: przerwij kontakt, zgłoś ogłoszenie w OLX, w razie straty — bank i policja.""",
    "olx_delivery": """\
PRZESYŁKA OLX (KUP Z PRZESYŁKĄ)
- Płacisz w aplikacji/na stronie OLX; pieniądze trafiają do sprzedawcy dopiero po potwierdzeniu odbioru albo po upływie czasu na zgłoszenie problemu — to Twoja główna ochrona.
- Całą komunikację i płatność trzymaj w OLX. Jeśli ktoś przysyła „link do Przesyłki OLX” poza aplikacją — to oszustwo.
- Przy odbiorze: nagraj otwieranie paczki (film bez cięć, z widoczną etykietą), sprawdź zgodność z ogłoszeniem i działanie.
- Problem (niezgodność, uszkodzenie, pusta paczka) zgłaszaj w aplikacji w terminie wskazanym przez OLX, zanim potwierdzisz odbiór.
- Sprawdź w aplikacji aktualne warunki ochrony i opłaty — mogą się zmieniać.""",
    "pickup": """\
ODBIÓR OSOBISTY
- Umów się w ruchliwym, dobrze oświetlonym miejscu (galeria, stacja paliw, przy komisariacie) albo u sprzedawcy, jeśli to duży przedmiot — wtedy nie idź sam.
- Zaplanuj test: ładowarka/kabel, karta SIM, pendrive, gra, powerbank itp. Daj sobie czas, nie daj się poganiać.
- Płać po sprawdzeniu. Gotówka lub BLIK na telefon/przelew natychmiastowy na miejscu. Sprawdź zaksięgowanie, jeśli to Ty otrzymujesz pieniądze.
- Weź potwierdzenie: krótka umowa kupna-sprzedaży albo przynajmniej wiadomość od sprzedawcy z opisem, ceną i datą; przy drogich rzeczach — dowód zakupu/fakturę i pudełko.
- Nie wpłacaj zaliczek „na rezerwację” przed oględzinami.""",
    "negotiation": """\
NEGOCJACJE — RAMA
1. Ustal liczby przed pierwszą wiadomością:
   - cena referencyjna = mediana porównywalnych ofert (ten sam model/wariant/stan), skorygowana o realne wady i braki,
   - oferta otwierająca ≈ 80–92% ceny wywoławczej (bliżej 92% przy uczciwej cenie i świeżym ogłoszeniu, bliżej 80% przy zawyżonej cenie, długim czasie na OLX lub wadach),
   - cel i cena maksymalna (walk-away), której nie przekraczasz.
2. Argumenty oparte na faktach: wady widoczne na zdjęciach, brak dowodu zakupu/akcesoriów, ceny porównywalnych ofert, koszt naprawy/wymiany baterii, czas wystawienia, odświeżanie ogłoszenia.
3. Argumenty niecenowe: szybki odbiór/zakup dziś, Przesyłka OLX bez kłopotu dla sprzedawcy, zakup kilku rzeczy naraz, elastyczny termin.
4. Taktyka: najpierw pytania, potem cena; uprzejmie i krótko; nie zdradzaj budżetu; ustępuj małymi, malejącymi krokami; jedna kontroferta z uzasadnieniem zamiast licytacji co 10 zł.
5. Unikaj ofert „obraźliwych” (< ~70% ceny bez wyraźnego powodu) — zamykają rozmowę.
6. Gdy sprzedawca nie schodzi z ceny: zapytaj o dodatki (etui, ładowarka, dostawa), albo zostaw kontakt i wróć za kilka dni.
7. Funkcja „Zaproponuj cenę” w OLX (gdy dostępna) to wygodny sposób na pierwszą ofertę.""",
    "buyer_rights": """\
PRAWA KUPUJĄCEGO (informacja ogólna, nie porada prawna)
- Od firmy (przedsiębiorcy), zakup na odległość (np. z wysyłką): 14 dni na odstąpienie od umowy bez podania przyczyny; odpowiedzialność za niezgodność towaru z umową — co do zasady 2 lata (dla rzeczy używanych może być skrócona, nie poniżej roku).
- Od osoby prywatnej: obowiązuje rękojmia z Kodeksu cywilnego, ale strony mogą ją ograniczyć lub wyłączyć w umowie; wyłączenie nie chroni sprzedawcy, który podstępnie zataił wadę.
- Dowody: zachowaj ogłoszenie (zrzuty), korespondencję, potwierdzenie płatności, nagranie rozpakowania.
- Samochód od osoby prywatnej: kupujący płaci 2% PCC (deklaracja PCC-3 w ciągu 14 dni, gdy wartość > 1000 zł) i rejestruje pojazd w ciągu 30 dni.""",
    "phones": """\
TELEFONY / TABLETY / SMARTWATCHE
Na zdjęciach: ekran (rysy, pęknięcia, wypalenia, plamy), ramka i rogi (wgniecenia), tylny panel, obiektywy aparatów, porty; zrzut „Ustawienia > Informacje” (model, pamięć), „Bateria > Kondycja” (iPhone: kondycja maksymalna), brak komunikatów o nieoryginalnych częściach.
Pytania: kondycja baterii (%), czy wymieniane części/ekran, czy był naprawiany lub zalany, czy jest blokada (iCloud/Find My, konto Google/FRP, simlock), czy jest pudełko/paragon/faktura, powód sprzedaży.
Przy odbiorze: sprawdź IMEI (*#06#) zgodny z pudełkiem i ustawieniami, wyloguj konto i zrób reset przy Tobie, test: ekran (białe/czarne tło), dotyk w całości, aparaty, mikrofon i głośniki (rozmowa), Wi-Fi/Bluetooth/GPS, ładowanie, Face ID/Touch ID, przyciski.
Ryzyka: podróbki (szczególnie AirPods, Apple Watch), zablokowane urządzenia, telefony z kradzieży lub na abonament z blokadą operatora. iPhone: numer seryjny można sprawdzić na checkcoverage.apple.com.""",
    "laptops": """\
LAPTOPY / KOMPUTERY / KARTY GRAFICZNE
Na zdjęciach: matryca (piksele, prześwietlenia, rysy od klawiatury), zawiasy, klawiatura i touchpad (wytarcia = intensywne użycie), obudowa, porty, naklejka z modelem; zrzuty: specyfikacja systemu, kondycja baterii (np. raport baterii), temperatury.
Pytania: konfiguracja (CPU, RAM, dysk), wiek, gwarancja, naprawy, czy był używany do kopania kryptowalut (GPU), czy jest oryginalna ładowarka, blokady BIOS/MDM (sprzęt firmowy).
Przy odbiorze: uruchom, sprawdź specyfikację w systemie, test klawiatury i portów, stress test kilka minut (temperatury, hałas), stan dysku (SMART), kondycję baterii; laptop firmowy — upewnij się, że nie ma zdalnego zarządzania (MDM).""",
    "consoles": """\
KONSOLE / GRY / AKCESORIA
Na zdjęciach: numer seryjny i model (np. wersja z napędem/digital), plomby, porty HDMI, stan padów (drift), obudowa.
Pytania: czy konsola była otwierana/czyszczona, czy jest ban konta, czy pad ma drift, data zakupu i dowód, czy konto zostanie wylogowane.
Przy odbiorze: uruchom z telewizorem/monitorem, test napędu płytą, pady (drift — gałki w spoczynku), porty, Wi-Fi, przegrzewanie po 10–15 min gry.
Ryzyka: bardzo tanie nowe konsole = częste oszustwa przedpłatowe.""",
    "cameras": """\
APARATY / OBIEKTYWY / DRONY
Na zdjęciach: przebieg migawki (zrzut z programu/serwisu), matryca (kurz, rysy), szkła obiektywu (grzyb, mgła, rysy), bagnet, ekran, gumy; dron: śmigła, gimbal, baterie (cykle).
Pytania: przebieg migawki, naprawy, upadki, kontakt z wodą/piaskiem, komplet (ładowarka, baterie), gwarancja/rejestracja drona.
Przy odbiorze: zdjęcia testowe (jednolite tło, przysłona zamknięta — kurz/martwe piksele), autofokus, stabilizacja, wszystkie przyciski i pokrętła; obiektyw pod światło (latarka) — grzyb/mgła.""",
    "cars": """\
SAMOCHODY
Na zdjęciach: równość szczelin i odcień lakieru (naprawy blacharskie), opony (zużycie, nierówne = geometria), wnętrze (zużycie kierownicy/pedałów vs przebieg), licznik, komora silnika (wycieki), podwozie i progi (rdza), tabliczka VIN.
Pytania: VIN, numer rejestracyjny i data pierwszej rejestracji (do sprawdzenia w historiapojazdu.gov.pl), historia serwisowa, wypadki, liczba właścicieli, kraj pochodzenia, czy auto jest na sprzedającego (czy pośrednik), stan rozrządu/sprzęgła/DPF, termin badania technicznego i OC.
Przed zakupem: sprawdź historię pojazdu, przegląd w niezależnym serwisie lub na stacji diagnostycznej, jazda próbna (zimny silnik!), miernik grubości lakieru, zgodność VIN w dokumentach i na nadwoziu.
Formalności: umowa kupna-sprzedaży (dwa egzemplarze), dowód rejestracyjny, karta pojazdu (jeśli wydana), polisa OC; PCC-3 (2%) w 14 dni, rejestracja w 30 dni.
Ryzyka: cofnięty licznik, auto powypadkowe/zalane, „handlarz” podający się za prywatnego właściciela, zaliczka za auto „za granicą”.""",
    "bikes": """\
ROWERY / HULAJNOGI / E-BIKE
Na zdjęciach: rama (pęknięcia przy spawach, wgniecenia — zwłaszcza karbon), napęd (zużycie zębów kaset/zębatek, łańcuch), hamulce, amortyzator (wycieki), numer ramy; e-bike: bateria (cykle/pojemność), silnik, sterownik.
Pytania: rozmiar ramy i wzrost użytkownika, numer ramy, przebieg, serwisy, dowód zakupu (rowery z kradzieży są częste), stan baterii.
Przy odbiorze: jazda próbna, hamowanie, zmiana wszystkich biegów, luzy sterów i piast, sprawdzenie numeru ramy w bazach skradzionych rowerów i porównanie z dokumentem zakupu.""",
    "furniture_appliances": """\
MEBLE / AGD / RTV
Na zdjęciach: wymiary (miarka na zdjęciu), stan tapicerki i krawędzi, zapachy/plamy (zapytaj!), tabliczka znamionowa AGD (model, rok produkcji), zawiasy i uszczelki.
Pytania: wiek, powód sprzedaży, zwierzęta/palenie w domu, demontaż i transport (kto, jak), czy działa (AGD — nagranie w działaniu), dostęp do mieszkania (piętro, winda).
Przy odbiorze: test działania na miejscu, sprawdzenie wymiarów i czy przejdzie przez drzwi, zaplanuj transport (Przesyłka OLX może nie obsługiwać dużych gabarytów).""",
    "clothing_luxury": """\
ODZIEŻ / OBUWIE / MARKOWE AKCESORIA
Na zdjęciach: metki (skład, kraj, kody), szwy, logo, podeszwy, zamki/okucia, numery seryjne/karty autentyczności (torebki, zegarki), zdjęcia w świetle dziennym (kolor).
Pytania: rozmiar w cm (długość wkładki/wymiary), dowód zakupu, ile razy noszone, czy prane/czyszczone, wady.
Ryzyka: podróbki markowych rzeczy — porównaj szczegóły z oficjalnymi zdjęciami, korzystaj z usług weryfikacji autentyczności przy drogich przedmiotach.""",
    "tickets": """\
BILETY / VOUCHERY
- Bardzo wysokie ryzyko oszustw: ten sam bilet sprzedawany wielu osobom, fałszywe PDF-y, przedpłaty bez biletu.
- Preferuj oficjalne platformy odsprzedaży organizatora lub przekazanie biletu imiennego w systemie organizatora.
- Nigdy nie płać z góry nieznajomemu przelewem/BLIK-iem; nie wierz w „zrzut ekranu biletu” jako dowód.
- Sprawdź regulamin wydarzenia (bilety imienne, zakaz odsprzedaży).""",
    "rentals": """\
WYNAJEM / NIERUCHOMOŚCI
- Nie płać kaucji ani „opłaty rezerwacyjnej” przed obejrzeniem lokalu i spotkaniem z właścicielem.
- Zweryfikuj właściciela: numer księgi wieczystej (ekw.ms.gov.pl), dokument tożsamości przy umowie, pełnomocnictwo dla pośrednika.
- Zdjęcia: porównaj z innymi ogłoszeniami (kradzione zdjęcia), sprawdź spójność (okna, widok, układ).
- Umowa pisemna: kaucja, czynsz i media, okres wypowiedzenia, protokół zdawczo-odbiorczy ze zdjęciami i stanami liczników.""",
}


def get_guide(topic: str) -> str:
    return GUIDES.get(topic, GUIDES["general"])
