#Projekt
**AI Worker** to niezależna usługa backendowa odpowiedzialna za realizację logiki biznesowej systemu korekty i tłumaczeń tekstów.  Będą dwa skrypty sync.py oraz ai.py

Oba skrypty bedą miały plik konfiguracje .env
```
	# Parametry lokalnej bazy danych MySQL
	DB_LOCAL_HOST=x.x.x.x
	DB_LOCAL_PORT=3306
	DB_LOCAL_USER=xxxx	
	DB_LOCAL_PASSWORD=xxxxxx
	DB_LOCAL_NAME=ailexia

	# Ustawienia aplikacji
	BATCH_SIZE=500
	LOG_LEVEL=INFO
	LOG_FORMAT=[%(asctime)s] %(levelname)s %(name)s: %(message)s
	LOG_SQL_QUERIES=false
```

# Wymagania kodu PYTHON
- używaj zmiennych w języku angielskim (stardard_snake)
- nazwy funkcji w języku angielskim (stardard_snake)
- twórz komentarze we fragmentach kodu w języku polskim
- twórz opisy funkcji które tworzysz w stadardzie Google Style (w języku polskim)
- nie opieraj się na klasach tylko na bibliotekach (nie programuj obiektowo) - tworz bibioteki (importuj je w ramach glownego skryptu)
- chce wywoływać jako skrypt sync.py lub ai.py - w przyszłości chcę kolejkować wywołanie skryptów 
- nie używaj  sqlalchemy szybkie zapytania SQL jawne zgodne z MySQL
- połacznei edo baz danych tylko za pomoca TCP/IP nie używaj pipe
- nazy zewnetrze moga być jako enum('mysql', 'mssql', 'pgsql', 'sqlite') - uwzględnij to przy połaczeniu z bazą zewnetrzną
- zrobić własną prostą klasę do MySQL  (połącznie init, query, execute, close...). 
- w ramach sktyptu trzamaj połączenie do bazy lokanej i zdalnej.

#Architktura
ailexia/
│
├── .env
├── sync.py
├── ai.py
├── README.md 
├── requirements.txt
│
├── lib/
│   ├── __init__.py
│   ├── db_local.py
│   ├── db_remote.py
│   ├── db_utils.py
│   ├── task.py
│   ├── task_item.py
│   └── load_config.py
│
└── logs/
    ├── sync.log
    └── ai.log

Każdy plik ma jasno określoną rolę:
- db_local.py – tylko lokalne połączenie i konfiguracja (czytelność i bezpieczeństwo),
- db_remote.py – niezależny od lokalnego, pozwala łatwo dodać nowe typy baz (pgsql, mssql),
- task.py i task_item.py – odseparowana logika operacyjna, bez mieszania w jednym pliku,
- db_utils.py – centralne narzędzia (logowanie, hash, czas, tekst),
- load_config.py – umożliwia łatwe wczytanie konfiguracji .env przez oba skrypty (sync.py, ai.py).


.env zawiera tylko lokalne dane połączeniowe (MySQL lokalny),

Dane do zewnętrzych baz danych są trzymane w tabeli database_connection, więc nie ma ryzyka przypadkowego ujawnienia haseł w repozytorium.

# Skrypt sync.py

Skrypt sync.py jest samodzielnym skryptem python odpowiedzialnym za synchronizację danych tekstowych pomiędzy bazą zewnętrzną (źródłową) a bazą lokalną systemu ailexia.
Celem skryptu jest pobranie, porównanie i aktualizacja rekordów tekstowych przy zachowaniu spójności danych i pełnej historii zmian w tabelach task oraz task_item.

##Parametry sync.py
Skrypt może być uruchamiany ręcznie lub z crona.
Może też przyjąć argument --id_task w celu synchronizacji konkretnego zadania.

Cel działania
- Automatyczne pobieranie rekordów z baz zewnętrznych (MySQL, MSSQL, PostgreSQL).
- Wykrywanie nowych, zmodyfikowanych lub usuniętych rekordów.
- Zapis kopii danych lokalnie w tabeli task_item wraz z hashami kontrolnymi.
- Aktualizacja statusu i postępu synchronizacji w tabeli task.


## DB tablice słownikowe
Nazwa bazy danych : ailexia
Host : **
User : ***
Pass : ***


```
CREATE TABLE `database_connection` (
  `id_database_connection` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `id_user` INT NOT NULL,
  `alias` VARCHAR(64) NOT NULL COMMENT 'np. HR, CRM, Magazyn',
  `description` TEXT DEFAULT NULL,
  `db_type` ENUM('mysql','mssql','pgsql','sqlite') DEFAULT 'mysql',
  `host` VARCHAR(128) NOT NULL,
  `port` INT UNSIGNED DEFAULT 3306,
  `db_name` VARCHAR(128) NOT NULL,
  `db_user` VARCHAR(128) NOT NULL,
  `db_password` CHAR(128) DEFAULT NULL COMMENT 'haslo jawnie',
  `use_ssl` TINYINT(1) DEFAULT 0,
  `status` ENUM('active','disabled','error') DEFAULT 'disabled',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `idx_database_alias` (`alias`),
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```



```
CREATE TABLE `task` (
  `id_task` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT 'Identyfikator zadania',
  `id_user` INT NOT NULL COMMENT 'Użytkownik, który zainicjował zadanie',
  `id_database_connectione` INT UNSIGNED NOT NULL COMMENT 'Źródłowa baza danych (z tabeli database_connection)',
  `id_ai_model` INT UNSIGNED DEFAULT NULL COMMENT 'Model AI używany w zadaniu (jeśli dotyczy)',
  `table_name` VARCHAR(64) NOT NULL COMMENT 'Nazwa tabeli źródłowej',
  `column_name` VARCHAR(64) NOT NULL COMMENT 'Nazwa kolumny tekstowej do synchronizacji',
  
  `status` ENUM('new','in_progress','paused','resync','completed','error','cancelled') 
       DEFAULT 'new' COMMENT 'Etap przetwarzania zadania',
  
  `records_total` INT UNSIGNED DEFAULT 0 COMMENT 'Liczba rekordów w tabeli źródłowej w momencie rozpoczęcia',
  `records_fetched` INT UNSIGNED DEFAULT 0 COMMENT 'Ilość rekordów pobranych do task_item',
  `records_processed` INT UNSIGNED DEFAULT 0 COMMENT 'Ilość rekordów przetworzonych / zhashowanych',
  `records_new` INT UNSIGNED DEFAULT 0 COMMENT 'Nowe rekordy dodane lokalnie',
  `records_updated` INT UNSIGNED DEFAULT 0 COMMENT 'Rekordy zaktualizowane po zmianie hash',
  `records_deleted` INT UNSIGNED DEFAULT 0 COMMENT 'Rekordy usunięte w źródle (jeśli śledzimy)',
  
  `records_approved` INT UNSIGNED DEFAULT 0 COMMENT 'Zatwierdzone przez użytkownika',
  `records_rejected` INT UNSIGNED DEFAULT 0 COMMENT 'Odrzucone przez użytkownika',
  `records_exported` INT UNSIGNED DEFAULT 0 COMMENT 'Wyeksportowane z powrotem do źródła',

  `last_processed_id` BIGINT UNSIGNED DEFAULT NULL COMMENT 'ID ostatniego przetworzonego rekordu (do wznawiania)',
  `sync_progress` DECIMAL(5,2) DEFAULT 0.00 COMMENT 'Procent synchronizacji (0–100)',
  `sync_stage` ENUM('init','fetch','compare','update','verify','done') DEFAULT 'init'
       COMMENT 'Aktualny etap procesu synchronizacji',

  `resume_marker` VARCHAR(128) DEFAULT NULL COMMENT 'Znacznik / ID od którego wznowić synchronizację',
  `hash_method` VARCHAR(32) DEFAULT 'sha256' COMMENT 'Algorytm hashujący treść tekstową',
  
  `description` TEXT DEFAULT NULL COMMENT 'Opis zadania / kontekst użytkownika',
  `error_log` TEXT DEFAULT NULL COMMENT 'Log błędów podczas przetwarzania',

  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `started_at` DATETIME DEFAULT NULL,
  `finished_at` DATETIME DEFAULT NULL,
  `total_time_ms` BIGINT UNSIGNED DEFAULT 0 COMMENT 'Czas całkowity w milisekundach',
  KEY `idx_task_status` (`status`),
  KEY `idx_task_progress` (`sync_progress`),
  KEY `idx_task_stage` (`sync_stage`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



Etap (sync_stage)	Znaczenie	Typowy procent postępu
init	inicjalizacja połączenia i metadanych	0–5%
fetch	pobieranie rekordów z bazy zewnętrznej	5–40%
compare	porównywanie hashy / identyfikacja zmian	40–70%
update	aktualizacja lub dodawanie rekordów	70–90%
verify	weryfikacja poprawności lokalnej kopii	90–98%
done	zakończenie zadania	100%

```

| `status_id` | Nazwa       | Znaczenie                                 |     |
| ----------- | ----------- | ----------------------------------------- | --- |
| `0`         | NEW         | Zadanie utworzone, oczekuje na realizację |     |
| `1`         | RESYNC      | Wymagana resynchronoizacji                |     |
| `2`         | SYNC        | W trakckje synchronizacji                 |     |
| `3`         | IN_LERNING  | W toku nauki - wymagana ocena             |     |
| `4`         | IN_PROGRESS | Przetwarzanie w toku                      |     |
| `5`         | COMPLETED   | Zakończone pomyślnie                      |     |
| `6`         | ERROR       | Błąd podczas przetwarzania                |     |
| `7`         | CANCELLED   | Przerwane przez użytkownika               |     |

tabela `task_item` – poszczególne rekordy zadania

```
CREATE TABLE `task_item` (
  `id_task_item` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT 'Identyfikator rekordu lokalnego',
  `id_task` INT UNSIGNED NOT NULL COMMENT 'Powiązanie z tabelą task',
  `remote_id` BIGINT DEFAULT NULL COMMENT 'Identyfikator w tabeli źródłowej (np. klucz główny)',
  
  `text_original` TEXT COMMENT 'Tekst pobrany z bazy źródłowej',
  `text_corrected` TEXT COMMENT 'Ewentualny tekst po przetworzeniu / korekcie / AI',
  `change_summary` TEXT COMMENT 'Opis różnic lub zmian wprowadzonych podczas synchronizacji',
  
  `original_hash` CHAR(64) DEFAULT NULL COMMENT 'Hash tekstu źródłowego w momencie pobrania',
  `local_hash` CHAR(64) DEFAULT NULL COMMENT 'Hash wersji lokalnej (do porównania przy resync)',
  `is_changed` TINYINT(1) DEFAULT 0 COMMENT 'Flaga: 1 = tekst w źródle uległ zmianie od ostatniej synchronizacji',
  
  `status` ENUM('pending','processed','accepted','rejected','exported','conflict','outdated') 
      DEFAULT 'pending' COMMENT 'Stan przetwarzania pojedynczego rekordu',
  
  `fetched_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Data pobrania rekordu z bazy źródłowej',
  `processed_at` DATETIME DEFAULT NULL COMMENT 'Data przetworzenia / porównania',
  `verified_at` DATETIME DEFAULT NULL COMMENT 'Data ponownej weryfikacji przy resync',
  `approved_at` DATETIME DEFAULT NULL COMMENT 'Data zatwierdzenia użytkownika',
  `approved_by` VARCHAR(64) DEFAULT NULL COMMENT 'Kto zatwierdził rekord',

  `operation_uuid` CHAR(36) DEFAULT NULL COMMENT 'Unikalny identyfikator operacji (np. UUID)',
  `tokens_input` INT UNSIGNED DEFAULT 0 COMMENT 'Liczba tokenów wejściowych (AI)',
  `tokens_output` INT UNSIGNED DEFAULT 0 COMMENT 'Liczba tokenów wyjściowych (AI)',
  `cost_usd` DECIMAL(10,6) DEFAULT 0 COMMENT 'Koszt przetworzenia AI dla tego rekordu',

  KEY `idx_task_item_status` (`status`),
  KEY `idx_task_item_changed` (`is_changed`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

Propozycja statusów dla tabeli task
status_id	Nazwa (ENUM)	Znaczenie operacyjne	Użycie w sync.py
0	new	Zadanie utworzone, oczekuje na rozpoczęcie.	Start CRON / CLI
1	queued	Zadanie dodane do kolejki (oczekuje na dostęp do workera).	Worker scheduler
2	in_progress	Trwa główna synchronizacja rekordów (pobieranie, porównywanie hashy, aktualizacja).	Główna pętla sync
3	paused	Synchronizacja wstrzymana (np. limit czasu, ręczne zatrzymanie, przerwanie CRON-a).	Można wznowić
4	resync	Ponowna synchronizacja — sprawdzanie zmian w rekordach już istniejących.	Tryb aktualizacji
5	verifying	Etap walidacji po synchronizacji – weryfikacja poprawności danych lokalnych vs źródłowych.	Po fazie compare
6	completed	Zadanie zakończone pomyślnie (wszystkie dane zsynchronizowane, brak błędów krytycznych).	Koniec procesu
7	error	Wystąpił błąd (np. brak połączenia z bazą, niezgodność schematu, problem z kodowaniem).	Worker loguje błąd
8	cancelled	Zadanie anulowane przez użytkownika.	Ręczna akcja
9	archived	Zadanie zarchiwizowane – dane zostają w systemie, ale nie są aktywnie monitorowane.	Po kilku dniach



