import json
import re

from ollama import Client


LLM_CODE_VERSION = "JARVIS-LLM-v0.7.1-PERMISSION-GUARD"


SYSTEM_CHAT = """
Ты JARVIS (Джарвис), локальный разговорный ассистент пользователя на Windows.
Отвечай пользователю напрямую на русском языке.

Правила:
- Выводи только готовый ответ.
- Не показывай внутренние рассуждения, анализ, план или служебный текст.
- Не пиши «пользователь спрашивает», «нужно ответить»,
  «сначала подумаю» и подобное.
- Обычно отвечай 1-2 короткими предложениями.
- Не повторяй одну мысль разными словами.
- Следи за русской грамматикой.
- Если можно ответить короче без потери смысла — отвечай короче.
""".strip()


SYSTEM_AGENT = """
Ты JARVIS (Джарвис), локальный Windows-ассистент пользователя.
Ты управляешь компьютером только через предоставленные инструменты.

Правила:
- Если запрос требует действия на компьютере, используй подходящие tools.
- Если запрос содержит несколько действий, выполни их по порядку.
- Можно вызвать несколько tools за один запрос.
- Если следующий шаг зависит от результата предыдущего,
  сначала вызови первый tool, дождись его результата,
  затем выбери следующий.
- «это окно», «активное окно», «текущее окно»
  означают foreground window Windows.
- Для «сверни это окно» используй minimize_window(target="active").
- Для «разверни это окно» используй restore_window(target="active")
  или maximize_window, если пользователь явно просит на весь экран.
- Для «закрой это окно» используй close_window(target="active"),
  а не close_app.
- Для переключения на уже открытое приложение используй focus_window.
- Для запуска Dota 2 используй open_app(app="dota2").
- Не придумывай успешное выполнение:
  учитывай фактический результат tool.
- Не используй произвольный shell: его у тебя нет.
- После успешных действий дай очень короткое подтверждение
  либо используй результаты tools.
- Не показывай внутренние рассуждения или план.
""".strip()


META_START_PATTERNS = (
    r"^\s*хорошо[,!. ]",
    r"^\s*итак[,!. ]",
    r"^\s*пользователь\b",
    r"^\s*нужно\b",
    r"^\s*надо\b",
    r"^\s*следует\b",
    r"^\s*сначала\b",
    r"^\s*я должен\b",
    r"^\s*мне нужно\b",
)


ACTION_HINTS = (
    "открой",
    "открывай",
    "запусти",
    "запускай",
    "включи",

    "закрой",
    "выключи",
    "выруби",

    "сверни",
    "разверни",
    "восстанови",

    "переключись",
    "покажи окно",
    "сделай активным",

    "активное окно",
    "это окно",
    "текущее окно",
    "какое окно",

    "сделай скрин",
    "скриншот",

    "поставь громкость",
    "установи громкость",

    "открой сайт",
    "найди в интернете",
    "поищи в интернете",
    "загугли",
    "перейди на",
    "открой ссылку",
)


def clean_answer(text: str) -> str:
    text = str(
        text or ""
    ).strip()

    # ---------------------------------------------------------
    # Убираем настоящий <think>...</think>
    # ---------------------------------------------------------

    text = re.sub(
        r"<think\b[^>]*>.*?</think\s*>",
        "",
        text,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    # Иногда модель отдаёт только </think>,
    # а всё полезное находится после него.
    if re.search(
        r"</think\s*>",
        text,
        flags=re.IGNORECASE,
    ):
        text = re.split(
            r"</think\s*>",
            text,
            flags=re.IGNORECASE,
        )[-1]

    # Незакрытый think.
    text = re.sub(
        r"<think\b[^>]*>.*$",
        "",
        text,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    # ---------------------------------------------------------
    # Служебный мусор
    # ---------------------------------------------------------

    text = re.sub(
        r"(?i)(?:^|\s)/no_think(?:\s|$)",
        " ",
        text,
    )

    text = re.sub(
        r"^\s*(?:final answer|answer|ответ)\s*:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return " ".join(
        text.split()
    ).strip()


def starts_like_internal_monologue(
    text: str,
) -> bool:
    low = str(
        text or ""
    ).lower()

    return any(
        re.search(
            pattern,
            low,
            flags=re.IGNORECASE,
        )
        for pattern
        in META_START_PATTERNS
    )


def looks_action_like(
    text: str,
) -> bool:
    low = str(
        text or ""
    ).lower()

    return any(
        hint in low
        for hint
        in ACTION_HINTS
    )


class LocalLLM:
    def __init__(
        self,
        config,
        tools,
        windows_allowed=None,
    ):
        self.model = config.get(
            "ollama_model",
            "qwen3:4b",
        )

        self.keep_alive = config.get(
            "llm_keep_alive",
            "10m",
        )

        self.max_tool_rounds = int(
            config.get(
                "llm_max_tool_rounds",
                4,
            )
        )

        self.client = Client(
            host=config.get(
                "ollama_host",
                "http://127.0.0.1:11434",
            )
        )

        # =====================================================
        # TOOLS AVAILABLE TO QWEN
        # =====================================================

        self.functions = {
            # Applications
            "open_app":
                tools.open_app,

            "close_app":
                tools.close_app,

            # Windows
            "get_active_window":
                tools.get_active_window,

            "minimize_window":
                tools.minimize_window,

            "maximize_window":
                tools.maximize_window,

            "restore_window":
                tools.restore_window,

            "focus_window":
                tools.focus_window,

            "close_window":
                tools.close_window,

            # Web
            "open_url":
                tools.open_url,

            "web_search":
                tools.web_search,

            # Other
            "take_screenshot":
                tools.take_screenshot,

            "set_volume":
                tools.set_volume,

            "get_time":
                tools.get_time,
        }

        self.windows_allowed = (
            windows_allowed
            if callable(windows_allowed)
            else lambda: True
        )

    # =========================================================
    # REQUEST
    # =========================================================

    def _chat_request(
        self,
        messages,
        use_tools=False,
        num_predict=160,
    ):
        kwargs = {
            "model":
                self.model,

            "messages":
                messages,

            "think":
                False,

            "stream":
                False,

            "keep_alive":
                self.keep_alive,

            "options": {
                "num_ctx":
                    2048,

                "num_predict":
                    num_predict,

                "temperature":
                    0.2,
            },
        }

        if use_tools:
            kwargs["tools"] = list(
                self.functions.values()
            )

        return self.client.chat(
            **kwargs
        )

    # =========================================================
    # TOOL EXECUTION
    # =========================================================

    def _tool_result(
        self,
        name,
        fn,
        arguments,
    ):
        try:
            allowed = bool(
                self.windows_allowed()
            )

        except Exception:
            allowed = False

        if not allowed:
            return (
                "Ошибка: Windows-команды отключены "
                "в панели управления."
            )

        try:
            return str(
                fn(
                    **(
                        arguments
                        or {}
                    )
                )
            )

        except Exception as exc:
            return (
                f"Ошибка: {exc}"
            )

    @staticmethod
    def _tool_message(
        name: str,
        content: str,
    ) -> dict:
        return {
            "role":
                "tool",

            "tool_name":
                name,

            "content":
                str(content),
        }

    @staticmethod
    def _assistant_message_for_history(
        message,
    ):
        """
        Превращает ответ Ollama в словарь,
        который можно вернуть модели
        следующим сообщением.

        Нужен для цепочек:
        assistant -> tool -> assistant -> tool.
        """

        content = str(
            getattr(
                message,
                "content",
                "",
            )
            or ""
        )

        tool_calls = (
            getattr(
                message,
                "tool_calls",
                None,
            )
            or []
        )

        item = {
            "role":
                "assistant",

            "content":
                content,
        }

        if tool_calls:
            serialized_calls = []

            for call in tool_calls:
                serialized_calls.append(
                    {
                        "function": {
                            "name":
                                call.function.name,

                            "arguments":
                                (
                                    call
                                    .function
                                    .arguments
                                    or {}
                                ),
                        }
                    }
                )

            item[
                "tool_calls"
            ] = serialized_calls

        return item

    # =========================================================
    # STRUCTURED FALLBACK
    # =========================================================

    def _structured_final(
        self,
        user_text: str,
    ) -> str:
        """
        Если Qwen опять начинает выводить
        внутренний черновик, просим вернуть
        строго JSON.
        """

        schema = {
            "type":
                "object",

            "properties": {
                "answer": {
                    "type":
                        "string"
                }
            },

            "required": [
                "answer"
            ],

            "additionalProperties":
                False,
        }

        messages = [
            {
                "role":
                    "system",

                "content": (
                    "Ответь на запрос пользователя "
                    "напрямую по-русски. "
                    "Верни только объект JSON "
                    "с единственным полем answer. "
                    "В answer должен быть только "
                    "готовый ответ, без анализа."
                ),
            },
            {
                "role":
                    "user",

                "content":
                    user_text,
            },
        ]

        try:
            response = (
                self.client.chat(
                    model=
                        self.model,

                    messages=
                        messages,

                    think=
                        False,

                    stream=
                        False,

                    format=
                        schema,

                    keep_alive=
                        self.keep_alive,

                    options={
                        "num_ctx":
                            1024,

                        "num_predict":
                            96,

                        "temperature":
                            0.0,
                    },
                )
            )

            raw = str(
                response
                .message
                .content
                or ""
            ).strip()

            # -----------------------------------------
            # Normal JSON
            # -----------------------------------------

            try:
                data = json.loads(
                    raw
                )

                answer = clean_answer(
                    data.get(
                        "answer",
                        "",
                    )
                )

                if answer:
                    return answer

            except Exception:
                pass

            # -----------------------------------------
            # JSON wrapped in garbage
            # -----------------------------------------

            match = re.search(
                r"\{.*\}",
                raw,
                flags=re.DOTALL,
            )

            if match:
                data = json.loads(
                    match.group(0)
                )

                answer = clean_answer(
                    data.get(
                        "answer",
                        "",
                    )
                )

                if answer:
                    return answer

        except Exception:
            pass

        return (
            "Не получил нормальный "
            "ответ от локальной модели."
        )

    # =========================================================
    # CONVERSATION MODE
    # =========================================================

    def _conversation(
        self,
        user_text,
        history,
    ):
        short_history = (
            history[-4:]
        )

        messages = [
            {
                "role":
                    "system",

                "content":
                    SYSTEM_CHAT,
            },

            *short_history,

            {
                "role":
                    "user",

                "content":
                    user_text,
            },
        ]

        response = (
            self._chat_request(
                messages,
                use_tools=False,
                num_predict=96,
            )
        )

        answer = clean_answer(
            response
            .message
            .content
            or ""
        )

        if (
            not answer
            or starts_like_internal_monologue(
                answer
            )
        ):
            return (
                self._structured_final(
                    user_text
                )
            )

        return answer

    # =========================================================
    # AGENT MODE
    # =========================================================

    def _agent(
        self,
        user_text,
        history,
    ):
        """
        Здесь JARVIS может делать
        несколько Windows-действий.

        Например:

        "сверни это окно и открой доту"

        Qwen может вызвать:

        minimize_window(active)
        open_app(dota2)

        либо сделать их в несколько rounds,
        если второй шаг зависит от первого.
        """

        short_history = (
            history[-4:]
        )

        messages = [
            {
                "role":
                    "system",

                "content":
                    SYSTEM_AGENT,
            },

            *short_history,

            {
                "role":
                    "user",

                "content":
                    user_text,
            },
        ]

        executed_results = []

        # -----------------------------------------------------
        # Ограниченный agent loop.
        #
        # Никаких бесконечных циклов,
        # даже если Qwen поедет кукухой.
        # -----------------------------------------------------

        for _ in range(
            max(
                1,
                self.max_tool_rounds,
            )
        ):
            response = (
                self._chat_request(
                    messages,
                    use_tools=True,
                    num_predict=128,
                )
            )

            calls = (
                response
                .message
                .tool_calls
                or []
            )

            # =================================================
            # MODEL FINISHED
            # =================================================

            if not calls:
                answer = clean_answer(
                    response
                    .message
                    .content
                    or ""
                )

                if (
                    answer
                    and not
                    starts_like_internal_monologue(
                        answer
                    )
                ):
                    return answer

                # Если tools уже реально
                # выполнялись, но Qwen не смог
                # сформировать хороший финал —
                # возвращаем фактические результаты.
                if executed_results:
                    return "\n".join(
                        executed_results
                    )

                return (
                    self._structured_final(
                        user_text
                    )
                )

            # =================================================
            # SAVE ASSISTANT TOOL CALLS
            # =================================================

            messages.append(
                self
                ._assistant_message_for_history(
                    response.message
                )
            )

            # =================================================
            # EXECUTE ALL REQUESTED TOOLS
            # =================================================

            for call in calls:
                name = (
                    call
                    .function
                    .name
                )

                fn = self.functions.get(
                    name
                )

                if fn is None:
                    result = (
                        "Неизвестный "
                        f"инструмент: {name}"
                    )

                else:
                    result = (
                        self._tool_result(
                            name,
                            fn,
                            call
                            .function
                            .arguments
                            or {},
                        )
                    )

                executed_results.append(
                    result
                )

                messages.append(
                    self._tool_message(
                        name,
                        result,
                    )
                )

        # -----------------------------------------------------
        # Safety stop:
        # max_tool_rounds закончились.
        # -----------------------------------------------------

        if executed_results:
            return "\n".join(
                executed_results
            )

        return (
            "Не смог выполнить команду."
        )

    # =========================================================
    # PUBLIC CHAT
    # =========================================================

    def chat(
        self,
        user_text,
        history,
    ):
        """
        Простые разговоры:
            Qwen без tools.

        Action-like запросы:
            Qwen + Windows tools.

        Большинство очевидных команд
        LocalRouter всё равно выполнит
        без запуска Qwen.
        """

        if looks_action_like(
            user_text
        ):
            return self._agent(
                user_text,
                history,
            )

        return self._conversation(
            user_text,
            history,
        )
