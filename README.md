# AI Worker

## Opis projektu
**AI Worker** to niezależna usługa backendowa odpowiedzialna za realizację logiki biznesowej systemu korekty i tłumaczeń tekstów. Repozytorium zawiera kompletną strukturę plików oraz bibliotek wspierających dwa główne skrypty uruchamiane bezpośrednio z linii poleceń: `sync.py` (synchronizacja danych między bazami) oraz `ai.py` (moduł przetwarzania danych z użyciem modeli AI).

Repozytorium nastawione jest na prostą, modułową architekturę opartą o funkcje i dedykowane biblioteki, bez stosowania paradygmatu obiektowego w głównej logice biznesowej.

## Wymagania wstępne
- Python 3.10+
- Dostęp do lokalnej bazy danych MySQL (parametry w `.env`).
- Dostęp do baz zewnętrznych (MySQL, MSSQL, PostgreSQL lub SQLite) zdefiniowanych w tabeli `database_connection` w bazie lokalnej.
- Zainstalowane zależności z pliku `requirements.txt`.

## Instalacja zależności
Zalecane jest korzystanie z wirtualnego środowiska (np. `venv`).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Konfiguracja środowiska
Lokalne parametry połączenia z bazą danych oraz ustawienia aplikacji przechowywane są w pliku `.env` (niecommitowanym do repozytorium). Przykładowa zawartość:

```dotenv
# Parametry lokalnej bazy danych MySQL
DB_LOCAL_HOST=192.168.2.5
DB_LOCAL_PORT=3306
DB_LOCAL_USER=root
DB_LOCAL_PASSWORD=seba00
DB_LOCAL_NAME=ailexia

# Ustawienia aplikacji
BATCH_SIZE=500
LOG_LEVEL=INFO
LOG_FORMAT=[%(asctime)s] %(levelname)s %(name)s: %(message)s
LOG_SQL_QUERIES=false
```

Zmienne są wczytywane w obu skryptach poprzez bibliotekę `lib/load_config.py` (funkcja `load_env`). Dane dostępowe do zewnętrznych baz danych NIE są przechowywane w `.env` — znajdują się w tabeli `database_connection` w lokalnej bazie, co minimalizuje ryzyko przypadkowego ujawnienia haseł.

## Struktura katalogów
```
ailexia/
├── .env                  # Konfiguracja lokalnej bazy danych (nie w repozytorium)
├── sync.py               # Skrypt synchronizacji danych
├── ai.py                 # Skrypt logiki AI (planowany / rozwijany)
├── README.md             # Dokumentacja projektu
├── requirements.txt      # Lista zależności
│
├── lib/                  # Wspólne biblioteki
│   ├── __init__.py
│   ├── db_local.py       # Połączenie z lokalną bazą MySQL
│   ├── db_remote.py      # Fabryka połączeń z bazami zewnętrznymi (MySQL/MSSQL/PG/SQLite)
│   ├── db_utils.py       # Funkcje narzędziowe (logowanie, hash, czas)
│   ├── load_config.py    # Wczytywanie konfiguracji środowiskowej
│   ├── task.py           # Funkcje obsługi zadań synchronizacji
│   └── task_item.py      # (docelowo) logika operacji na rekordach szczegółowych
│
└── logs/
    ├── sync.log          # Logi działania skryptu synchronizacji
    └── ai.log            # Logi działania skryptu AI
```

## Przegląd bibliotek (`lib/`)
- `db_local.py` – tworzy wyłącznie połączenie z lokalną bazą MySQL na podstawie konfiguracji z `.env` (`connect_local`).
- `db_remote.py` – udostępnia funkcję `connect_remote`, która otwiera połączenie z bazą zewnętrzną zgodnie z typem `db_type` (`mysql`, `mssql`, `pgsql`, `sqlite`).
- `db_utils.py` – centralne narzędzia: `setup_logger` (konfiguracja loggera), `hash_text`, `now_str`.
- `load_config.py` – funkcja `load_env` zwracająca słownik konfiguracji na potrzeby skryptów.
- `task.py` – funkcje `get_next_task` (pobieranie zadania ze statusem `new`, `in_progress`, `resync`) oraz `get_remote_db_params` (odczyt parametrów połączenia dla bazy zewnętrznej).
- `task_item.py` – przygotowane miejsce na funkcje obsługujące rekordy szczegółowe zadań (hashowanie, porównywanie, aktualizacje).

## Działanie skryptu `sync.py`
Skrypt odpowiada za synchronizację danych tekstowych pomiędzy bazą zewnętrzną a lokalną. Aktualny przebieg działania:

1. **Wczytanie konfiguracji i loggera** – funkcje `load_env` i `setup_logger` dostarczają odpowiednio ustawień `.env` oraz loggera zapisującego logi do `logs/sync.log`.
2. **Połączenie z bazą lokalną** – `connect_local` (MySQL) tworzy połączenie i kursor słownikowy.
3. **Wybór zadania** – `get_next_task` pobiera najstarsze zadanie o statusie `new`, `in_progress` lub `resync`. Docelowo można wymusić konkretne zadanie argumentem `--id_task`.
4. **Pobranie konfiguracji zewnętrznej bazy** – `get_remote_db_params` zwraca rekord z tabeli `database_connection` z danymi połączeniowymi.
5. **Połączenie z bazą zewnętrzną** – `connect_remote` otwiera połączenie z odpowiednim silnikiem (`mysql`, `mssql`, `pgsql`, `sqlite`).
6. **Operacje synchronizacji** – w tym repozytorium przygotowane jest miejsce na dalszą logikę (import modułu `task_item`, porównanie rekordów, aktualizacja statusów). Implementacja kolejnych kroków jest przewidziana w trakcie rozwoju projektu.

Po zakończeniu działania skrypt zamyka połączenia z bazą lokalną i zewnętrzną oraz zapisuje odpowiednie informacje w logach.

### Uruchomienie
Skrypt można wywołać ręcznie lub poprzez cron / system kolejkowy:

```bash
python sync.py               # uruchomienie standardowe
python sync.py --id_task 42   # synchronizacja konkretnego zadania (funkcjonalność planowana)
```

## Skrypt `ai.py`
Docelowo skrypt będzie odpowiedzialny za przetwarzanie danych w oparciu o modele AI (np. korekta, tłumaczenia, klasyfikacja). Struktura repozytorium oraz biblioteki umożliwiają łatwe wykorzystanie tych samych narzędzi (konfiguracja, logowanie, połączenia z bazami).

## Logowanie
Domyślne logi zapisywane są w katalogu `logs/`. Każdy skrypt ma dedykowany plik (`sync.log`, `ai.log`). Poziom logowania (`LOG_LEVEL`) i format (`LOG_FORMAT`) można konfigurować w `.env`.

## Rozwój i testy
- W repozytorium znajduje się `requirements.txt` z zależnościami produkcyjnymi oraz narzędziami developerskimi (`pytest`, `mypy`, `black`).
- Zalecane jest dodawanie nowych funkcji w formie modułów w katalogu `lib/`, aby utrzymać modularną architekturę bez klas w głównej logice.
- Do testowania można wykorzystywać `pytest`, a jakość kodu poprawiać narzędziami `mypy` (statyczna analiza) i `black` (formatowanie).

## Najbliższe kroki rozwoju
- Implementacja szczegółowej logiki synchronizacji (porównywanie rekordów, zapisy w `task_item`).
- Dodanie obsługi parametru `--id_task` w `sync.py`.
- Przygotowanie skryptu `ai.py` z wykorzystaniem wspólnych bibliotek (`load_env`, `db_local`, `db_utils`).
- Rozszerzenie modułu logowania o możliwość logowania zapytań SQL (`LOG_SQL_QUERIES=true`).

## Licencja
Projekt jest rozwijany wewnętrznie; licencja zostanie określona na późniejszym etapie.
