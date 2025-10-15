### Frontend – Yii2 z komponentami JS dla interaktywności

- **Yii2 (widoki PHP)** – główna warstwa UI do podglądu i akceptacji zmian
- **AlpineJS** – lekka interaktywność w widokach (toggle, modale, formularze)
- **Vue (wybrane ekrany)** – bogatsze komponenty tam, gdzie potrzebna jest większa reaktivność
- **Bootstrap 4/5** – spójny system stylów i siatki
- **TypeScript (opcjonalnie w bundle dla Vue/Alpine)** – lepsze typowanie w kodzie frontu

#### Backend – warstwa aplikacyjna + worker AI

- **Warstwa aplikacyjna (Web/API):**
    - **Yii2 (PHP 8.x)** – panele, REST endpoints do triggerowania zadań i akceptacji wyników
    - **MSSQL (baza aplikacji)** – dane domenowe, statusy zadań, audyt, wersjonowanie zmian
- **Warstwa przetwarzania w tle (AI worker):**
    - **Python (FastAPI)** – serwis workerowy do komunikacji z modelami AI i bazą
    
- **Źródła danych do korekty (read-only):**
    - **MySQL / MSSQL / PostgreSQL / SQLite** – heterogeniczne bazy jako źródła tekstów


### API – modele do korekty językowej

- API Gemini – modele do korekty językowej i normalizacji tekstu testowo (**Gemini 1.5 Flash**: ~15 zapytań na minutę (RPM) i do ~1 500 zapytań na dzień (RPD) w darmowym planie.)
- ChatGPT (opcja)