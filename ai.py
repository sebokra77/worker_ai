#!/usr/bin/env python3
"""Główny skrypt odpowiedzialny za obsługę modeli AI."""

import sys

from lib.load_config import load_env
from lib.db_utils import setup_logger
from lib.db_local import connect_local
from lib.task import get_next_task
from lib.ai_api import (
    build_api_request,
    execute_api_request,
    fetch_ai_model_config,
    is_model_supported,
    is_provider_supported,
)
from lib.task_item import (
    append_task_error,
    build_correction_prompt,
    fetch_pending_task_items,
    parse_json_response,
    update_task_items_from_json,
)


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
        pending_items = fetch_pending_task_items(cursor_local, task['id_task'])
        if not pending_items:
            logger.info(
                "Brak rekordów do przetworzenia dla zadania ID=%s.",
                task['id_task'],
            )
            print("Brak rekordów pending dla zadania.")
            return

        prompt_text = build_correction_prompt(pending_items)
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

        try:
            response_text = execute_api_request(request_data)
        except Exception as api_error:  # noqa: BLE001
            logger.error(
                "Błąd wywołania modelu AI %s (%s): %s",
                model_name,
                provider,
                api_error,
            )
            append_task_error(cursor_local, task['id_task'], str(api_error))
            conn_local.commit()
            print("Błąd podczas wywołania modelu AI.")
            return

        try:
            parsed_response = parse_json_response(response_text)
        except ValueError as validation_error:
            logger.error(
                "Model AI zwrócił niepoprawny JSON dla zadania ID=%s: %s",
                task['id_task'],
                validation_error,
            )
            append_task_error(cursor_local, task['id_task'], str(validation_error))
            conn_local.commit()
            print("Niepoprawny format odpowiedzi modelu AI.")
            return

        try:
            updated = update_task_items_from_json(
                cursor_local,
                task['id_task'],
                parsed_response,
            )
            conn_local.commit()
        except ValueError as update_error:
            logger.error(
                "Nie udało się zaktualizować rekordów zadania ID=%s: %s",
                task['id_task'],
                update_error,
            )
            conn_local.rollback()
            append_task_error(cursor_local, task['id_task'], str(update_error))
            conn_local.commit()
            print("Błąd podczas aktualizacji rekordów w bazie.")
            return

        logger.info(
            "Przetworzono %s rekordów zadania ID=%s modelem %s (%s).",
            updated,
            task['id_task'],
            model_name,
            provider,
        )
        print("Model AI zakończył przetwarzanie rekordów.")
    finally:
        cursor_local.close()
        conn_local.close()


if __name__ == "__main__":
    main()
