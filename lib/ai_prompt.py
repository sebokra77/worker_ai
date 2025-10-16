"""Funkcje pomocnicze do budowy promptów dla modeli AI."""

from typing import Any, Dict, Iterable, List, Optional


def build_correction_prompt(
    records: Iterable[Dict[str, Any]],
    user_rules: Optional[str] = None,
) -> str:
 
    rules: List[str] = [
        "- Każdy elemeny <INPUT> musi być w tablicy JSON <OUTPUT_FORMAT>.",
        "- Nie zmieniaj znaczenia zdań.",
        "- Każdy wpis ma mieć klucz \"remote_id\" zgodny z numerem zdania.",
        "- Nie dodawaj żadnych komentarzy ani tekstu poza JSON.",
        "- Każde zdanie traktuj jako osobną jednostkę.",
        "- Uwzględnij w odpowiedzi wszytskie <INPUT>. Jeżeli <INPUT> nie wymaga poprawy i ciąg zwracany jest identyczny, zwróć 'text_corrected' jako pusty string.",
    ]

    user_rules_value = (user_rules or '').strip()
    if user_rules_value:
        rules.append(f"- {user_rules_value}")

    lines: List[str] = [
        "<SYSTEM>",
        "Model: zachowuj ścisły format JSON wyjścia i nie dodawaj żadnych komentarzy ani tekstu poza JSON.",
        "</SYSTEM>",
        "<TASK>",
        "Dla każdego elementu z listy <INPUT> zrób korektę ortograficzną, interpunkcyjną lub stylistyczną jeśli wymaga.",
        "Nie usuwaj wyrazów tylko koreguj tekst. ",
        "Jeśli nie wymaga — pozostaw \"text_corrected\" jako pusty string \"\".",
        "</TASK>",
        "<RULES>",
    ]

    lines.extend(rules)

    lines.extend(
        [
            "</RULES>",
            "<OUTPUT_FORMAT>",
            "[",
            "  {\"remote_id\":1,\"text_corrected\":\"...\"}",
            "]",
            "</OUTPUT_FORMAT>",
            "<INPUT>",
        ]
    )

    for record in records:
        remote_id_value = record.get('remote_id')
        if remote_id_value in (None, ''):
            remote_id_value = record.get('id_task_item')
        if remote_id_value in (None, ''):
            remote_id_value = record.get('id')
        if remote_id_value in (None, ''):
            remote_id_value = '?'

        text_value = (record.get('text_original') or '').replace('\r', ' ').replace('\n', ' ').strip()
        lines.append(f"{remote_id_value}. {text_value}")

    lines.extend(
        [
            "</INPUT>",
        ]
    )

    return "\n".join(lines)

