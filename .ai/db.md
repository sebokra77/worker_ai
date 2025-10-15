## DB tablice słownikowe

Tabela: www_user – użytkownicy systemu

```
CREATE TABLE `www_user` (
  `id_user` INT AUTO_INCREMENT PRIMARY KEY,
  `crc` VARCHAR(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `last_name` VARCHAR(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `first_name` VARCHAR(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `email` VARCHAR(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` VARCHAR(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_reset_token` VARCHAR(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `is_deleted` TINYINT(1) NOT NULL DEFAULT 0,
  `last_login_at` DATETIME DEFAULT NULL,
  `login_count` INT NOT NULL DEFAULT 0,
  `login_fail_count` MEDIUMINT NOT NULL DEFAULT 0 COMMENT 'liczba nieudanych logowań',
  `password_changed_at` DATETIME DEFAULT NULL COMMENT 'data ostatniej zmiany hasła',
  UNIQUE KEY `idx_user_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```


Tabela: ai_model – modele AI przypisane do użytkownika

```
CREATE TABLE `ai_model` (
  `id_ai_model` INT AUTO_INCREMENT PRIMARY KEY,
  `id_user` INT NOT NULL,
  `model_name` VARCHAR(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'np. gpt-5, gemini-pro, mistral',
  `provider` VARCHAR(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'np. OpenAI, Google, Anthropic',
  `api_key_encrypted` VARBINARY(512) DEFAULT NULL COMMENT 'zaszyfrowany klucz API',
  `base_url` VARCHAR(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'opcjonalny endpoint API',
  `temperature` DECIMAL(3,2) DEFAULT 1.00 COMMENT 'kreatywność modelu',
  `max_tokens` INT DEFAULT 2048 COMMENT 'limit tokenów w miesiącu ',
  `max_char_input` INT DEFAULT 2048 COMMENT 'limit znaków z pola DB',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `fk_ai_model_user`
    FOREIGN KEY (`id_user`) REFERENCES `www_user` (`id_user`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```


Tabela: database_connection – połączenia do baz danych użytkownika

```
CREATE TABLE `database_connection` (
  `id_database` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `id_user` INT NOT NULL,
  `alias` VARCHAR(64) NOT NULL COMMENT 'np. HR, CRM, Magazyn',
  `description` TEXT DEFAULT NULL,
  `db_type` ENUM('mysql','mssql','pgsql','sqlite','oracle') DEFAULT 'mysql',
  `host` VARCHAR(128) NOT NULL,
  `port` INT UNSIGNED DEFAULT 3306,
  `db_name` VARCHAR(128) NOT NULL,
  `db_user` VARCHAR(128) NOT NULL,
  `db_password_encrypted` VARBINARY(512) DEFAULT NULL COMMENT 'zaszyfrowane hasło AES_ENCRYPT',
  `use_ssl` TINYINT(1) DEFAULT 0,
  `status` ENUM('active','disabled','error') DEFAULT 'active',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `idx_database_alias` (`alias`),
  CONSTRAINT `fk_database_user`
    FOREIGN KEY (`id_user`) REFERENCES `www_user` (`id_user`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;```

```

```
CREATE TABLE `task` (
  `id_task` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `id_user` INT NOT NULL,
  `id_database` INT UNSIGNED NOT NULL,
  `id_ai_model` INT UNSIGNED DEFAULT NULL,
  `table_name` VARCHAR(64) NOT NULL,
  `column_name` VARCHAR(64) NOT NULL,
  `status` ENUM('new','in_progress','completed','error','cancelled') DEFAULT 'new',
  `records_fetched` INT UNSIGNED DEFAULT 0,
  `records_processed` INT UNSIGNED DEFAULT 0,
  `records_approved` INT UNSIGNED DEFAULT 0,
  `records_rejected` INT UNSIGNED DEFAULT 0,
  `records_exported` INT UNSIGNED DEFAULT 0,
  `last_processed_id` BIGINT UNSIGNED DEFAULT NULL,
  `learning_steps` INT UNSIGNED DEFAULT 20 COMMENT 'ile kroków nauki',
  `mode` ENUM('manual','semiauto') DEFAULT 'manual',
  `description` TEXT DEFAULT NULL COMMENT 'opis lub kontekst zadania',
  `error_log` TEXT DEFAULT NULL,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `started_at` DATETIME DEFAULT NULL,
  `finished_at` DATETIME DEFAULT NULL,
  `total_time_ms` BIGINT UNSIGNED DEFAULT 0,
  GENERATED ALWAYS AS (
    CASE WHEN `records_fetched` > 0
         THEN (`records_processed` / `records_fetched` * 100)
         ELSE 0 END
  ) STORED `progress_percent` DECIMAL(5,2),
  KEY `idx_task_status` (`status`),
  KEY `idx_task_table` (`id_database`,`table_name`),
  CONSTRAINT `fk_task_user`
    FOREIGN KEY (`id_user`) REFERENCES `www_user` (`id_user`)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_task_database`
    FOREIGN KEY (`id_database`) REFERENCES `database_connection` (`id_database`)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_task_ai_model`
    FOREIGN KEY (`id_ai_model`) REFERENCES `ai_model` (`id_ai_model`)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE `task_item`
  ADD COLUMN `tokens_input` INT UNSIGNED DEFAULT 0,
  ADD COLUMN `tokens_output` INT UNSIGNED DEFAULT 0,
  ADD COLUMN `cost_usd` DECIMAL(10,6) DEFAULT 0;

```

| `status_id` | Nazwa       | Znaczenie                                 |     |
| ----------- | ----------- | ----------------------------------------- | --- |
| `0`         | NEW         | Zadanie utworzone, oczekuje na realizację |     |
| `1`         | IN_LERNING  | W toku nauki - wymagana ocena             |     |
| `2`         | IN_PROGRESS | Przetwarzanie w toku                      |     |
| `3`         | COMPLETED   | Zakończone pomyślnie                      |     |
| `4`         | ERROR       | Błąd podczas przetwarzania                |     |
| `5`         | CANCELLED   | Przerwane przez użytkownika               |     |

tabela `task_item` – poszczególne rekordy zadania

```
CREATE TABLE `task_item` (
  `id_task_item` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `id_task` INT UNSIGNED NOT NULL,
  `remote_id` BIGINT DEFAULT NULL COMMENT 'ID rekordu z bazy źródłowej',
  `text_original` TEXT,
  `text_corrected` TEXT,
  `change_summary` TEXT,
  `original_hash` CHAR(64),
  `status` ENUM('pending','processed','accepted','rejected','exported','conflict') DEFAULT 'pending',
  `fetched_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `processed_at` DATETIME DEFAULT NULL,
  `approved_at` DATETIME DEFAULT NULL,
  `approved_by` VARCHAR(64) DEFAULT NULL,
  `operation_uuid` CHAR(36) DEFAULT (UUID()),
  UNIQUE KEY `uniq_task_remote` (`id_task`,`remote_id`),
  CONSTRAINT `fk_task_item_task`
    FOREIGN KEY (`id_task`) REFERENCES `task` (`id_task`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

| `status_id` | Nazwa      | Znaczenie                         |
| ----------- | ---------- | --------------------------------- |
| `0`         | PENDING    | Oczekuje na przetwarzanie         |
| `1`         | PROCESSED  | Przetworzony przez AI             |
| `2`         | ACCEPTED   | Zatwierdzony przez użytkownika    |
| `3`         | REJECTED   | Odrzucony przez użytkownika       |
| `4`         | EXPORTED   | Wyeksportowany do bazy źródłowej  |
| `5`         | CONFLICT   | Konflikt danych (zmiana w źródle) |
| 6           | TOO_LONG_1 | Za długi teskt z bazy pierwotnej  |
| 7           | TOO_LONG_2 | Za długi tekst po tłumaczeniu     |



Tabele na przyszłość poza MVP 

```
CREATE TABLE `task_proof_note` (
  `id_note` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `id_task` INT UNSIGNED NOT NULL,
  `id_user` INT UNSIGNED NOT NULL,
  `note_text` TEXT NOT NULL COMMENT 'np. "nie upraszczaj zdań technicznych"',
   `note_correct` TEXT NOT NULL COMMENT 'np. "nie upraszczaj zdań technicznych"',
  `is_active` TINYINT(1) DEFAULT 1,
  `priority` INT UNSIGNED DEFAULT 1,
  `context_tag` VARCHAR(64) DEFAULT NULL COMMENT 'np. styl, gramatyka, ton',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_note`),
  KEY `idx_tasknote_task` (`id_task`),
  CONSTRAINT `fk_tasknote_task`
    FOREIGN KEY (`id_task`) REFERENCES `task`(`id_task`)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_tasknote_user`
    FOREIGN KEY (`id_user`) REFERENCES `www_user`(`id_user`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```


### Kluczowe tabele

|Tabela|Opis|Połączenia|
|---|---|---|
|`www_user`|Użytkownicy systemu|1:N z `ai_model`, `task`|
|`ai_model`|Modele AI przypisane do użytkownika|FK → `www_user.id_user`|
|`database_connection`|Połączenia użytkownika do baz źródłowych|FK → `www_user.id_user`|
|`task`|Zadanie przetwarzania (np. korekta, tłumaczenie)|FK → `ai_model.id_ai_model`|
|`task_item`|Pojedynczy rekord do przetworzenia|FK → `task.id_task`|
|`task_proof_note`|Uwagi użytkownika (na przyszłość)|FK → `task.id_task`|