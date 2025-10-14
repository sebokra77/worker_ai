#!/usr/bin/env python3
"""Główny skrypt odpowiedzialny za obsługę modeli AI."""

import sys

from lib.load_config import load_env
from lib.db_utils import setup_logger
from lib.db_local import connect_local
from lib.task import get_next_task
from lib.ai_api import fetch_ai_model_config, is_provider_supported, is_model_supported, build_api_request


def main() -> None:
    """Uruchamia podstawowy przepływ przygotowania zapytań do modeli AI."""

    # Załaduj konfigurację i logger
    try:
        print("Wczytywanie konfiguracji ")
        cfg = load_env()
    except ValueError as error:
        print(f"Błąd konfiguracji środowiska w pliku .env: {error}")
        sys.exit(1)

    logger = setup_logger('ai', 'logs/ai.log')
    logger.info("=== Rozpoczęcie obsługi zadań AI ===")

    # Połączenie z bazą lokalną
    print("Łączenie z bazą lokalną ...", end="")
    conn_local = connect_local(cfg)
    if not conn_local:
        logger.error("Nie udało się połączyć z bazą lokalną.")
        print(" Error")
        sys.exit(1)
    print(" OK")

    cursor_local = conn_local.cursor(dictionary=True)

    try:
        # Pobierz zadanie oczekujące na obsługę
        print("Pobieranie zadania ...")
        task = get_next_task(cursor_local)
        if not task:
            logger.info("Brak zadań do obsługi przez AI.")
            print("Brak zadań do obsługi przez AI.")
            return

        if not task.get('id_ai_model'):
            logger.warning(
                "Zadanie ID=%s nie ma przypisanego modelu AI.",
                task.get('id_task'),
            )
            print("Zadanie nie ma przypisanego modelu AI.")
            return

        # Pobierz konfigurację modelu
        ai_model = fetch_ai_model_config(cursor_local, task['id_ai_model'])
        if not ai_model:
            logger.error(
                "Nie znaleziono aktywnej konfiguracji modelu AI ID=%s.",
                task['id_ai_model'],
            )
            print("Brak konfiguracji modelu AI.")
            return

        provider = ai_model.get('provider')
        model_name = ai_model.get('model_name')

        # Waliduj dostawcę
        if not is_provider_supported(provider):
            logger.error(
                "Dostawca modelu AI %s nie jest obsługiwany.",
                provider,
            )
            print("Nieobsługiwany dostawca modelu AI.")
            return

        # Sprawdź dostępność konkretnego modelu
        if not is_model_supported(ai_model):
            logger.error(
                "Model %s dostawcy %s nie jest dostępny w obsługiwanym API.",
                model_name,
                provider,
            )
            print("Model AI nie jest dostępny.")
            return

        # Przygotuj dane zapytania do API (przykładowa treść promptu)
        prompt_text = ''
        try:
            request_data = build_api_request(
                ai_model,
                prompt_text,
                temperature=ai_model.get('temperature'),
                max_tokens=ai_model.get('max_tokens'),
            )
        except ValueError as api_error:
            logger.error("Nie można przygotować zapytania API: %s", api_error)
            print("Błąd przygotowania zapytania API.")
            return

        # W tym miejscu request_data można przekazać do funkcji wywołującej API.
        _ = request_data

        logger.info(
            "Przygotowano zapytanie API dla modelu %s (%s).",
            model_name,
            provider,
        )
        print("Model AI gotowy do przetwarzania.")
    finally:
        cursor_local.close()
        conn_local.close()


if __name__ == "__main__":
    main()
