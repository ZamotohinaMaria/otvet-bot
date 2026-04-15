import logging
from config import LLM_PROVIDER, LLM_API_KEY

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Единый клиент для DeepSeek, OpenAI и Claude.
    Смена провайдера — только через LLM_PROVIDER в .env.
    """

    def __init__(self):
        self.provider = LLM_PROVIDER
        self._client = None
        self._model = None
        self._setup()

    def _setup(self):
        if self.provider in ("deepseek", "openai"):
            from openai import OpenAI
            if self.provider == "deepseek":
                self._client = OpenAI(
                    api_key=LLM_API_KEY,
                    base_url="https://api.deepseek.com",
                )
                self._model = "deepseek-chat"
            else:
                self._client = OpenAI(api_key=LLM_API_KEY)
                self._model = "gpt-4o-mini"

        elif self.provider == "claude":
            import anthropic
            self._client = anthropic.Anthropic(api_key=LLM_API_KEY)
            self._model = "claude-haiku-4-5-20251001"

        else:
            raise ValueError(f"Неизвестный LLM_PROVIDER: {self.provider!r}. Допустимые: deepseek, openai, claude")

    def classify(self, review_text: str, templates: dict) -> str | None:
        """
        Просит LLM выбрать категорию шаблона для отзыва.
        Возвращает ключ шаблона или None (если сложный).
        """
        categories = "\n".join(
            f"- {key}: {tpl['description']}"
            for key, tpl in templates.items()
        )

        prompt = (
            "Ты помогаешь выбрать шаблон ответа на отзыв покупателя интернет-магазина.\n\n"
            f"Доступные категории шаблонов:\n{categories}\n"
            "- skip: отзыв слишком сложный, требует индивидуального ответа\n\n"
            f'Отзыв покупателя:\n"{review_text}"\n\n'
            "Выбери ОДНУ категорию из списка выше. "
            "Ответь ТОЛЬКО ключом категории (например: positive_general или skip). "
            "Никаких объяснений."
        )

        try:
            if self.provider in ("deepseek", "openai"):
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=30,
                    temperature=0,
                )
                result = resp.choices[0].message.content.strip().lower()

            elif self.provider == "claude":
                resp = self._client.messages.create(
                    model=self._model,
                    max_tokens=30,
                    messages=[{"role": "user", "content": prompt}],
                )
                result = resp.content[0].text.strip().lower()

            if result == "skip":
                return None
            if result in templates:
                return result
            logger.warning("LLM вернул неизвестную категорию: %r", result)
            return None

        except Exception as e:
            logger.error("Ошибка LLM (%s): %s", self.provider, e)
            return None
