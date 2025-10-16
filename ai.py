#!/usr/bin/env python3
"""Główny skrypt odpowiedzialny za obsługę modeli AI."""

import json
import sys

from lib.load_config import load_env
from lib.db_utils import log_error_and_print, setup_logger
from lib.db_local import connect_local
from lib.task import get_next_task
from lib.ai_api import (
    build_api_request,
    execute_api_request,
    fetch_ai_model_config,
    is_model_supported,
    is_provider_supported,
)
from lib.ai_prompt import build_correction_prompt
from lib.task_item import (
    append_task_error,
    build_original_text_mappings,
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
        print(" Error")
        log_error_and_print(logger, "Nie udało się połączyć z bazą lokalną.")
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
            log_error_and_print(
                logger,
                "Nie znaleziono aktywnej konfiguracji modelu AI ID=%s.",
                task['id_ai_model'],
            )
            return

        provider = ai_model.get('provider')
        model_name = ai_model.get('model_name')

        # Waliduj dostawcę
        if not is_provider_supported(provider):
            log_error_and_print(
                logger,
                "Dostawca modelu AI %s nie jest obsługiwany.",
                provider,
            )
            return

        # Sprawdź dostępność konkretnego modelu
        if not is_model_supported(ai_model):
            log_error_and_print(
                logger,
                "Model %s dostawcy %s nie jest dostępny w obsługiwanym API.",
                model_name,
                provider,
            )
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

        (
            expected_identifiers,
            remote_texts,
            local_texts,
        ) = build_original_text_mappings(pending_items)

        prompt_text = build_correction_prompt(
            pending_items,
            task.get('ai_user_rules'),
        )
        print("Wygenerowany prompt do modelu AI:")
        print(prompt_text)
        request_options = {}
        temperature_value = ai_model.get('temperature')
        if temperature_value not in (None, ''):
            request_options['temperature'] = temperature_value
        max_tokens_value = ai_model.get('max_tokens')
        if max_tokens_value not in (None, ''):
            request_options['max_tokens'] = max_tokens_value

        try:
            request_data = build_api_request(
                ai_model,
                prompt_text,
                **request_options,
            )
        except ValueError as api_error:
            log_error_and_print(
                logger,
                "Nie można przygotować zapytania API: %s",
                api_error,
            )
            return

        print(
            "Rozpoczynam połączenie do AI... "
            f"Dostawca: {provider}, model: {model_name}"
        )
        try:
            (
                response_text,
                tokens_input_total,
                tokens_output_total,
                raw_response_dump,
                response_metadata,
            ) = execute_api_request(request_data)
        except Exception as api_error:  # noqa: BLE001
            log_error_and_print(
                logger,
                "Błąd wywołania modelu AI %s (%s): %s",
                model_name,
                provider,
                api_error,
            )
            append_task_error(cursor_local, task['id_task'], str(api_error))
            conn_local.commit()
            return

        print("Odpowiedź modelu AI:")
        print(raw_response_dump)
        try:
            parsed_response = parse_json_response(response_text)
        except ValueError as validation_error:
            log_error_and_print(
                logger,
                "Model AI zwrócił niepoprawny JSON dla zadania ID=%s: %s",
                task['id_task'],
                validation_error,
            )
            append_task_error(cursor_local, task['id_task'], str(validation_error))
            conn_local.commit()
            return

        print("Przetworzona struktura odpowiedzi AI:")
        # Poniższa pętla ogranicza dane tylko do par remote_id i text_corrected
        formatted_items = []
        for item in parsed_response:
            remote_value = item.get("remote_id")
            if remote_value in (None, ""):
                remote_value = item.get("id_task_item", item.get("id"))
            formatted_items.append(
                {
                    "remote_id": remote_value,
                    "text_corrected": item.get("text_corrected", ""),
                }
            )
        for formatted_item in formatted_items:
            print(json.dumps(formatted_item, ensure_ascii=False))

        try:
            original_text_lookup = {}
            for pending_item in pending_items:
                text_value = pending_item.get('text_original')
                remote_key = pending_item.get('remote_id')
                local_key = pending_item.get('id_task_item')
                if remote_key not in (None, ''):
                    original_text_lookup[remote_key] = text_value
                if local_key not in (None, ''):
                    original_text_lookup[local_key] = text_value

            expected_remote_ids = {
                item.get('remote_id')
                if item.get('remote_id') is not None
                else item.get('id_task_item')
                for item in pending_items
                if item.get('remote_id') is not None or item.get('id_task_item') is not None
            }
            response_ai_model = (response_metadata or {}).get('model')
            if response_ai_model in (None, ''):
                response_ai_model = model_name
            response_finish_reason = (response_metadata or {}).get('finish_reason')
            updated = update_task_items_from_json(
                cursor_local,
                task['id_task'],
                parsed_response,
                expected_identifiers,
                tokens_input_total,
                tokens_output_total,
                original_text_lookup,
                response_ai_model,
                response_finish_reason,
            )
            conn_local.commit()
        except ValueError as update_error:
            log_error_and_print(
                logger,
                "Nie udało się zaktualizować rekordów zadania ID=%s: %s",
                task['id_task'],
                update_error,
            )
            conn_local.rollback()
            append_task_error(cursor_local, task['id_task'], str(update_error))
            conn_local.commit()
            return

        logger.info(
            "Przetworzono %s rekordów zadania ID=%s modelem %s (%s).",
            updated,
            task['id_task'],
            model_name,
            provider,
        )
        print(f"Zaktualizowano rekordy w liczbie: {updated}")
        print("Model AI zakończył przetwarzanie rekordów.")
    finally:
        cursor_local.close()
        conn_local.close()


if __name__ == "__main__":
    main()
