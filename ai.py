#!/usr/bin/env python3
"""Główny skrypt odpowiedzialny za obsługę modeli AI."""

import json
import sys

from lib.load_config import load_env
from lib.db_utils import log_error_and_print, setup_logger
from lib.db_local import connect_local
from lib.task import get_next_task_to_ai, update_task_ai_progress
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
    build_processing_table,
    fetch_pending_task_items,
    parse_json_response,
    update_processing_table_with_response,
    update_task_items_from_table,
)


def main() -> None:
    """Uruchamia podstawowy przepływ przygotowania zapytań do modeli AI."""

    # Załaduj konfigurację i logger
    try:
        print("Wczytywanie konfiguracji ... ", end="", flush=True)
        cfg = load_env()

    except ValueError as error:
        print(f"Błąd konfiguracji środowiska w pliku .env: {error}")
        sys.exit(1)
    print("\033[32mOK\033[0m") 
    
    logger = setup_logger('ai', 'logs/ai.log')

    # Połączenie z bazą lokalną
    print("Łączenie z bazą lokalną ... ", end="", flush=True)
    conn_local = connect_local(cfg)
    if not conn_local:
        print(" Error")
        log_error_and_print(logger, "Nie udało się połączyć z bazą lokalną.")
        sys.exit(1)
    print("\033[32mOK\033[0m") 

    cursor_local = conn_local.cursor(dictionary=True)

    try:
        # Pobierz zadanie oczekujące na obsługę
        print("Pobieranie zadania ... ", end="", flush=True)
        task = get_next_task_to_ai(cursor_local)
        if not task:
            logger.info("Brak zadań do obsługi przez AI.")
            print(f"\033[33mbrak zadań do AI\033[0m")
            return

        if not task.get('id_ai_model'):
            logger.warning(
                "Zadanie ID=%s nie ma przypisanego modelu AI.",
                task.get('id_task'),
            )
            print("Zadanie nie ma przypisanego modelu AI.")
            return
            
        print("\033[32mOK\033[0m") 
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
            print(f"\033[33mrekordów pending dla zadania\033[0m")
            return

        processing_table = build_processing_table(pending_items)
        expected_identifiers = {
            entry['remote_id']
            if entry.get('remote_id') not in (None, '')
            else entry.get('id_task_item')
            for entry in processing_table
            if entry.get('remote_id') not in (None, '')
            or entry.get('id_task_item') not in (None, '')
        }

        prompt_text = build_correction_prompt(
            processing_table,
            task.get('ai_user_rules'),
        )
        print("Generuje prompt do modelu AI ... ", end="", flush=True)    
        #print(f"\033[90m{prompt_text}\033[0m")
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
        print("\033[32mOK\033[0m") 
        print(f"Wysyłam zapytanie do AI {provider} model {model_name} ... ", end="", flush=True)
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
        print("\033[32mOK\033[0m") 

        #print("Odpowiedź modelu AI:")
        #print(raw_response_dump)
        print(f"Sprawdzam poprawność odpowiedzi AI ... ", end="", flush=True)
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
        
        print("\033[32mOK\033[0m") 
        print("Przetworzona struktura odpowiedzi AI ... ")
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
        #for formatted_item in formatted_items:
        #    print(json.dumps(formatted_item, ensure_ascii=False))

        try:
            update_processing_table_with_response(
                processing_table,
                parsed_response,
                expected_identifiers,
            )
            response_ai_model = (response_metadata or {}).get('model')
            if response_ai_model in (None, ''):
                response_ai_model = model_name
            response_finish_reason = (response_metadata or {}).get('finish_reason')
            updated = update_task_items_from_table(
                cursor_local,
                task['id_task'],
                processing_table,
                tokens_input_total,
                tokens_output_total,
                response_ai_model,
                response_finish_reason,
            )
            progress_report = update_task_ai_progress(cursor_local, task['id_task'])
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
        logger.info(
            (
                "Postęp zadania ID=%s: changed=%s, unchanged=%s, "
                "processed=%s/%s (%.2f%%)."
            ),
            task['id_task'],
            progress_report.get('changed_count'),
            progress_report.get('unchanged_count'),
            progress_report.get('processed_total'),
            progress_report.get('records_total'),
            progress_report.get('progress_value'),
        )
        print(f"Zaktualizowano rekordy w liczbie: \033[32m{updated}\033[0m")
    finally:
        cursor_local.close()
        conn_local.close()

    print("\033[32mOK\033[0m")
if __name__ == "__main__":
    main()
