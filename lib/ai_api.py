"""Biblioteka pomocnicza do obsługi konfiguracji i zapytań modeli AI."""

from __future__ import annotations

from typing import Any, Callable, Dict

from openai import OpenAI
try:  # pragma: no cover - obsługa różnych wersji biblioteki
    from openai import APIConnectionError as OpenAIAPIConnectionError
except ImportError:  # pragma: no cover
    OpenAIAPIConnectionError = Exception
try:  # pragma: no cover
    from openai import AuthenticationError as OpenAIAuthenticationError
except ImportError:  # pragma: no cover
    OpenAIAuthenticationError = Exception
try:  # pragma: no cover
    from openai import NotFoundError as OpenAINotFoundError
except ImportError:  # pragma: no cover
    OpenAINotFoundError = Exception
import google.generativeai as genai
import anthropic


SUPPORTED_PROVIDERS = {
    'OpenAI',
    'DeepSeek',
    'Google',
    'Anthropic',
}

_JSON_INSTRUCTIONS = {
    'OpenAI': 'Zwróć wyłącznie poprawny JSON, bez komentarzy ani tekstu wokół. Wynik musi być czystym obiektem JSON.',
    'DeepSeek': 'Return only valid JSON, without code blocks or extra text.',
    'Google': 'Output only valid JSON. No markdown, no text outside the JSON.',
    'Anthropic': 'Respond only with valid JSON. Do not include explanations, markdown, or any text before or after the JSON.',
}

SUPPORTED_MODELS = {
    'OpenAI': {
        'gpt-4.1',
        'gpt-4o',
        'gpt-4o-mini',
        'gpt-3.5-turbo',
        'gpt-5',
    },
    'DeepSeek': {
        'deepseek-chat',
        'deepseek-coder',
    },
    'Google': {
        'gemini-pro',
        'gemini-1.5-pro',
        'gemini-1.5-flash',
    },
    'Anthropic': {
        'claude-3-opus',
        'claude-3-sonnet',
        'claude-3-haiku',
    },
}

DEFAULT_ENDPOINTS = {
    'OpenAI': None,
    'DeepSeek': 'https://api.deepseek.com/v1',
}

_PROVIDER_BUILDERS: Dict[
    str,
    Callable[[Dict[str, Any], str, Dict[str, Any]], Dict[str, Any]],
] = {}


def decrypt_api_key(encrypted_key: str | None) -> str:
    """Zwraca klucz API w formie możliwej do użycia."""

    if not encrypted_key:
        return ''
    # W tym miejscu należy podpiąć logikę deszyfrowania zgodną z systemem.
    return encrypted_key


def fetch_ai_model_config(cursor, id_ai_model: int) -> Dict[str, Any] | None:
    """Pobiera konfigurację modelu AI z bazy danych."""

    sql = (
        "SELECT id_ai_model, id_user, provider, model_name, api_key_encrypted, "
        "base_url, temperature, max_tokens, max_char_input "
        "FROM ai_model WHERE id_ai_model = %s AND is_active = 1"
    )
    cursor.execute(sql, (id_ai_model,))
    return cursor.fetchone()


def is_provider_supported(provider: str | None) -> bool:
    """Sprawdza czy dostawca modelu jest obsługiwany."""

    if not provider:
        return False
    return provider in SUPPORTED_PROVIDERS


def is_model_supported(model_config: Dict[str, Any]) -> bool:
    """Weryfikuje dostępność modelu u wskazanego dostawcy."""

    provider = model_config.get('provider')
    model_name = model_config.get('model_name')
    if not provider or not model_name:
        return False

    checker = _PROVIDER_MODEL_CHECKERS.get(provider)
    if not checker:
        return _fallback_model_check(provider, model_name)

    return checker(model_config)


def build_api_request(
    model_config: Dict[str, Any],
    prompt: str,
    **options: Any,
) -> Dict[str, Any]:
    """Buduje strukturę danych potrzebnych do wykonania zapytania API."""

    provider = model_config.get('provider')
    if not is_provider_supported(provider):
        raise ValueError('Nieobsługiwany dostawca modelu AI.')

    builder = _PROVIDER_BUILDERS.get(provider)
    if builder is None:
        raise ValueError('Brak funkcji budującej zapytanie dla wskazanego dostawcy.')

    temperature_value = options.get('temperature')
    if temperature_value in (None, ''):
        temperature_value = model_config.get('temperature')

    max_tokens_value = options.get('max_tokens')
    if max_tokens_value in (None, ''):
        max_tokens_value = model_config.get('max_tokens')

    params = {'prompt': prompt}
    if temperature_value not in (None, ''):
        params['temperature'] = temperature_value
    if max_tokens_value not in (None, ''):
        params['max_tokens'] = max_tokens_value
    system_prompt = options.get('system_prompt')
    if system_prompt not in (None, ''):
        params['system_prompt'] = system_prompt

    prompt_with_instruction = _append_json_instruction(provider, prompt)

    return builder(model_config, prompt_with_instruction, params)


def execute_api_request(request: Dict[str, Any]) -> str:
    """Wysyła zapytanie do dostawcy AI i zwraca odpowiedź tekstową."""

    if not request:
        raise ValueError('Brak danych żądania API.')

    provider = request.get('provider')
    callable_object = request.get('callable')
    payload = request.get('payload', {})
    if callable_object is None:
        raise ValueError('Brak funkcji wywołującej API w strukturze żądania.')

    # Wysłanie zapytania bez zapamiętywania historii – każde żądanie zawiera tylko bieżący prompt
    response = callable_object(**payload)
    return _extract_response_text(provider, response)


def _fallback_model_check(provider: str, model_name: str) -> bool:
    """Zapewnia weryfikację modelu na podstawie statycznej listy."""

    supported = SUPPORTED_MODELS.get(provider, set())
    if model_name in supported:
        return True
    for pattern in supported:
        if model_name.startswith(f'{pattern}-') or model_name.startswith(f'{pattern}.'):
            return True
    return False


def _append_json_instruction(provider: str | None, prompt: str) -> str:
    """Dodaje instrukcję zwracania JSON do treści promptu.

    Args:
        provider: Nazwa dostawcy modelu wykorzystywanego w zapytaniu.
        prompt: Bazowa treść przekazywana do modelu.

    Returns:
        str: Treść promptu uzupełniona o instrukcję zwrócenia wyłącznie JSON.
    """

    instruction = _JSON_INSTRUCTIONS.get(provider or '')
    if not instruction:
        return prompt

    normalized_prompt = prompt.rstrip()
    if not normalized_prompt:
        return instruction
    return f"{normalized_prompt}\n\n{instruction}"


def _is_not_found_error(error: Exception) -> bool:
    """Sprawdza czy wyjątek oznacza brak modelu w API."""

    status_code = getattr(error, 'status_code', None) or getattr(error, 'http_status', None)
    if status_code == 404:
        return True
    message = str(error).lower()
    return 'not found' in message or 'does not exist' in message


def _create_openai_client(model_config: Dict[str, Any]) -> OpenAI:
    """Tworzy klienta OpenAI z opcjonalnym niestandardowym adresem bazowym."""

    api_key = decrypt_api_key(model_config.get('api_key_encrypted'))
    if not api_key:
        raise ValueError('Brak klucza API dla dostawcy OpenAI/DeepSeek.')
    # Przygotuj parametry klienta zależne od dostawcy.
    kwargs: Dict[str, Any] = {'api_key': api_key}
    base_url = model_config.get('base_url')
    if base_url:
        kwargs['base_url'] = base_url
    elif model_config.get('provider') == 'DeepSeek':
        kwargs['base_url'] = DEFAULT_ENDPOINTS['DeepSeek']
    return OpenAI(**kwargs)


def _check_openai_model(model_config: Dict[str, Any]) -> bool:
    """Sprawdza dostępność modelu w API OpenAI."""

    model_name = model_config.get('model_name', '')
    client = _create_openai_client(model_config)
    try:
        client.models.retrieve(model_name)
        return True
    except OpenAINotFoundError:
        return False
    except (OpenAIAuthenticationError, OpenAIAPIConnectionError):
        # Brak możliwości weryfikacji on-line, pozostaje lista statyczna.
        return _fallback_model_check('OpenAI', model_name)
    except Exception as error:  # pragma: no cover - zabezpieczenie przed nieznanymi wyjątkami
        if _is_not_found_error(error):
            return False
        return _fallback_model_check('OpenAI', model_name)


def _check_deepseek_model(model_config: Dict[str, Any]) -> bool:
    """Sprawdza dostępność modelu DeepSeek (API kompatybilne z OpenAI)."""

    model_name = model_config.get('model_name', '')
    client = _create_openai_client(model_config)
    try:
        client.models.retrieve(model_name)
        return True
    except OpenAINotFoundError:
        return False
    except (OpenAIAuthenticationError, OpenAIAPIConnectionError):
        return _fallback_model_check('DeepSeek', model_name)
    except Exception as error:  # pragma: no cover - zabezpieczenie przed nieznanymi wyjątkami
        if _is_not_found_error(error):
            return False
        return _fallback_model_check('DeepSeek', model_name)


def _check_google_model(model_config: Dict[str, Any]) -> bool:
    """Sprawdza dostępność modelu Google Gemini."""

    api_key = decrypt_api_key(model_config.get('api_key_encrypted'))
    model_name = model_config.get('model_name', '')
    if not api_key:
        return False
    # Konfiguracja klienta Google.
    genai.configure(api_key=api_key)
    try:
        genai.get_model(model_name)
        return True
    except Exception as error:  # pragma: no cover - pakiet zwraca różne typy wyjątków
        if _is_not_found_error(error):
            return False
        return _fallback_model_check('Google', model_name)


def _check_anthropic_model(model_config: Dict[str, Any]) -> bool:
    """Sprawdza dostępność modelu Anthropic."""

    api_key = decrypt_api_key(model_config.get('api_key_encrypted'))
    model_name = model_config.get('model_name', '')
    if not api_key:
        return False
    client = anthropic.Anthropic(api_key=api_key)
    try:
        client.models.retrieve(model_name)
        return True
    except anthropic.NotFoundError:
        return False
    except anthropic.APIError:  # pragma: no cover - ogólny błąd API
        return _fallback_model_check('Anthropic', model_name)
    except Exception as error:  # pragma: no cover
        if _is_not_found_error(error):
            return False
        return _fallback_model_check('Anthropic', model_name)


def _prepare_openai_request(
    model_config: Dict[str, Any],
    prompt: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Przygotowuje strukturę zapytania dla klienta OpenAI."""

    client = _create_openai_client(model_config)
    messages = []
    if params.get('system_prompt'):
        messages.append({'role': 'system', 'content': params['system_prompt']})
    messages.append({'role': 'user', 'content': prompt})

    payload = {
        'model': model_config.get('model_name'),
        'messages': messages,
        'response_format': {'type': 'json_object'},
        'stream': False,
    }
    if 'temperature' in params:
        payload['temperature'] = float(params['temperature'])
    if 'max_tokens' in params:
        payload['max_completion_tokens'] = int(params['max_tokens'])

    return {
        'provider': 'OpenAI',
        'client': client,
        'callable': client.chat.completions.create,
        'payload': payload,
    }


def _prepare_deepseek_request(
    model_config: Dict[str, Any],
    prompt: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Przygotowuje strukturę zapytania dla klienta DeepSeek."""

    client = _create_openai_client(model_config)
    messages = []
    if params.get('system_prompt'):
        messages.append({'role': 'system', 'content': params['system_prompt']})
    messages.append({'role': 'user', 'content': prompt})

    payload = {
        'model': model_config.get('model_name'),
        'messages': messages,
        'response_format': {'type': 'json_object'},
        'stream': False,
    }
    if 'temperature' in params:
        payload['temperature'] = float(params['temperature'])
    if 'max_tokens' in params:
        payload['max_completion_tokens'] = int(params['max_tokens'])

    return {
        'provider': 'DeepSeek',
        'client': client,
        'callable': client.chat.completions.create,
        'payload': payload,
    }


def _prepare_google_request(
    model_config: Dict[str, Any],
    prompt: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Przygotowuje strukturę zapytania dla klienta Google Gemini."""

    api_key = decrypt_api_key(model_config.get('api_key_encrypted'))
    if not api_key:
        raise ValueError('Brak klucza API dla dostawcy Google.')

    # Konfiguracja klienta globalnego biblioteki Google.
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_config.get('model_name'))

    generation_config = {
        'response_mime_type': 'application/json',
    }
    if 'temperature' in params:
        generation_config['temperature'] = float(params['temperature'])
    if 'max_tokens' in params:
        generation_config['max_output_tokens'] = int(params['max_tokens'])

    kwargs: Dict[str, Any] = {
        'contents': [
            {'role': 'user', 'parts': [{'text': prompt}]},
        ],
        'generation_config': generation_config,
        'stream': False,
    }
    if params.get('system_prompt'):
        kwargs['system_instruction'] = {'parts': [{'text': params['system_prompt']}]} 

    return {
        'provider': 'Google',
        'client': model,
        'callable': model.generate_content,
        'payload': kwargs,
    }


def _prepare_anthropic_request(
    model_config: Dict[str, Any],
    prompt: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Przygotowuje strukturę zapytania dla klienta Anthropic."""

    api_key = decrypt_api_key(model_config.get('api_key_encrypted'))
    if not api_key:
        raise ValueError('Brak klucza API dla dostawcy Anthropic.')

    client = anthropic.Anthropic(api_key=api_key)

    kwargs: Dict[str, Any] = {
        'model': model_config.get('model_name'),
        'messages': [
            {
                'role': 'user',
                'content': prompt,
            }
        ],
        'stream': False,
    }
    if 'temperature' in params:
        kwargs['temperature'] = float(params['temperature'])
    if 'max_tokens' in params:
        kwargs['max_output_tokens'] = int(params['max_tokens'])
    if params.get('system_prompt'):
        kwargs['system'] = params['system_prompt']

    return {
        'provider': 'Anthropic',
        'client': client,
        'callable': client.messages.create,
        'payload': kwargs,
    }


def _extract_response_text(provider: str | None, response: Any) -> str:
    """Wydobywa treść odpowiedzi z obiektu zwróconego przez różne biblioteki."""

    if provider in {'OpenAI', 'DeepSeek'}:
        choices = getattr(response, 'choices', None) or response.get('choices') if isinstance(response, dict) else None
        if choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get('message') or {}
                content = message.get('content')
                if isinstance(content, list):
                    return ''.join(
                        part.get('text', '') if isinstance(part, dict) else str(part)
                        for part in content
                    )
                if content:
                    return content
                if 'text' in first_choice:
                    return str(first_choice['text'])
            else:
                message = getattr(first_choice, 'message', None)
                if message is not None:
                    content = getattr(message, 'content', None)
                    if isinstance(content, list):
                        return ''.join(
                            getattr(part, 'text', str(part))
                            for part in content
                        )
                    if content:
                        return str(content)
                text_value = getattr(first_choice, 'text', None)
                if text_value:
                    return str(text_value)
        content = getattr(response, 'content', None)
        if content:
            return str(content)

    if provider == 'Google':
        text_value = getattr(response, 'text', None)
        if text_value:
            return str(text_value)
        candidates = getattr(response, 'candidates', None) or response.get('candidates') if isinstance(response, dict) else None
        if candidates:
            candidate = candidates[0]
            if isinstance(candidate, dict):
                content = candidate.get('content', {})
                parts = content.get('parts') if isinstance(content, dict) else candidate.get('parts')
                if isinstance(parts, list):
                    return ''.join(
                        part.get('text', '') if isinstance(part, dict) else str(part)
                        for part in parts
                    )
            else:
                parts = getattr(candidate, 'parts', None)
                if parts:
                    return ''.join(getattr(part, 'text', str(part)) for part in parts)

    if provider == 'Anthropic':
        content = getattr(response, 'content', None)
        if isinstance(content, list):
            return ''.join(
                part.get('text', '') if isinstance(part, dict) else getattr(part, 'text', str(part))
                for part in content
            )
        if content:
            return str(content)
        completion = getattr(response, 'completion', None)
        if completion:
            return str(completion)

    # Fallback na reprezentację tekstową obiektu odpowiedzi
    return str(response)


_PROVIDER_MODEL_CHECKERS: Dict[str, Callable[[Dict[str, Any]], bool]] = {
    'OpenAI': _check_openai_model,
    'DeepSeek': _check_deepseek_model,
    'Google': _check_google_model,
    'Anthropic': _check_anthropic_model,
}


_PROVIDER_BUILDERS.update({
    'OpenAI': _prepare_openai_request,
    'DeepSeek': _prepare_deepseek_request,
    'Google': _prepare_google_request,
    'Anthropic': _prepare_anthropic_request,
})
