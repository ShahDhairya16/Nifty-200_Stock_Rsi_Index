import json
import re
import warnings
from typing import Any, Dict, List, Optional

from app.config import config
from app.services.market_context_service import MarketContextService


class GeminiError(RuntimeError):
    """User-facing Gemini integration error."""


class GeminiService:
    """Thin wrapper around the Google Gemini SDK.

    Supports both the current ``google-genai`` package and the older
    ``google-generativeai`` package so existing environments keep working.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = (api_key or config.GEMINI_API_KEY or "").strip()
        self.model = (model or config.GEMINI_MODEL or "gemini-3.5-flash-lite").strip()
        fallback_models = getattr(config, "GEMINI_FALLBACK_MODELS", "") or ""
        models = [self.model] + [item.strip() for item in fallback_models.split(",") if item.strip()]
        self.models = list(dict.fromkeys(models))
        self.active_model: Optional[str] = None
        self.temperature = float(config.GEMINI_TEMPERATURE)
        self._sdk: Optional[str] = None
        self._client: Any = None
        self._legacy: Any = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _load_sdk(self) -> None:
        if self._sdk:
            return
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore

            retry_options = None
            try:
                retry_options = types.HttpRetryOptions(attempts=1)
            except Exception:
                retry_options = None
            http_options = None
            try:
                options = {"timeout": 60000}
                if retry_options is not None:
                    options["retry_options"] = retry_options
                http_options = types.HttpOptions(**options)
            except Exception:
                http_options = None

            self._sdk = "google-genai"
            self._client = genai.Client(api_key=self.api_key, http_options=http_options)
            self._types = types
            return
        except Exception:
            pass

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                import google.generativeai as legacy  # type: ignore

            self._sdk = "google-generativeai"
            self._legacy = legacy
            legacy.configure(api_key=self.api_key)
            return
        except Exception as exc:
            raise GeminiError(
                "No Gemini SDK is installed. Run 'pip install google-genai' "
                "and restart the dashboard."
            ) from exc

    @staticmethod
    def _response_text(response: Any) -> str:
        text = getattr(response, "text", None)
        if callable(text):
            try:
                text = text()
            except Exception:
                text = None
        if text:
            return str(text).strip()

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                part_text = getattr(part, "text", None)
                if part_text:
                    return str(part_text).strip()
        return ""

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(token in message for token in ("503", "unavailable", "404", "not found"))

    def _friendly_error(self, exc: Exception) -> str:
        message = str(exc)
        lowered = message.lower()
        if "api key" in lowered or "api_key" in lowered or "401" in lowered or "403" in lowered:
            return "Gemini rejected the API key. Check GEMINI_API_KEY and try again."
        if "429" in lowered or "quota" in lowered or "resource_exhausted" in lowered:
            return (
                "Gemini quota or rate limit reached. The free tier allows only a few "
                "requests per minute/day; wait and retry, or use a key with higher quota."
            )
        if "503" in lowered or "unavailable" in lowered or "high demand" in lowered:
            return "Gemini is temporarily busy. Please try again in a minute."
        if "404" in lowered or "not found" in lowered:
            tried = ", ".join(self.models)
            return (
                f"None of the configured Gemini models are available ({tried}). "
                "Set GEMINI_MODEL in secrets/.env to an available model."
            )
        return f"Gemini request failed: {message[:400]}"

    def _generate(
        self,
        prompt: str,
        system_instruction: str,
        temperature: Optional[float] = None,
        max_output_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        if not self.is_configured:
            raise GeminiError(
                "Gemini API key is missing. Add GEMINI_API_KEY to Streamlit secrets "
                "or your local .env file."
            )
        self._load_sdk()
        temperature = self.temperature if temperature is None else temperature

        last_error: Optional[Exception] = None
        for model_name in self.models:
            try:
                if self._sdk == "google-genai":
                    config_kwargs: Dict[str, Any] = {
                        "system_instruction": system_instruction,
                        "temperature": temperature,
                        "max_output_tokens": max_output_tokens,
                    }
                    if json_mode:
                        config_kwargs["response_mime_type"] = "application/json"
                    response = self._client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=self._types.GenerateContentConfig(**config_kwargs),
                    )
                else:
                    generation_config: Dict[str, Any] = {
                        "temperature": temperature,
                        "max_output_tokens": max_output_tokens,
                    }
                    if json_mode:
                        generation_config["response_mime_type"] = "application/json"
                    try:
                        model = self._legacy.GenerativeModel(
                            model_name,
                            system_instruction=system_instruction,
                        )
                        response = model.generate_content(prompt, generation_config=generation_config)
                    except TypeError:
                        model = self._legacy.GenerativeModel(model_name)
                        response = model.generate_content(
                            f"{system_instruction}\n\n{prompt}",
                            generation_config=generation_config,
                        )

                text = self._response_text(response)
                if text:
                    self.active_model = model_name
                    return text
                last_error = GeminiError(f"Gemini model '{model_name}' returned an empty response.")
            except Exception as exc:
                last_error = exc
                if self._is_retryable(exc):
                    continue
                raise GeminiError(self._friendly_error(exc)) from exc

        if last_error is not None:
            raise GeminiError(self._friendly_error(last_error)) from last_error
        raise GeminiError("Gemini returned an empty response. Try rephrasing the question.")

    @staticmethod
    def _format_history(history: Optional[List[Dict[str, Any]]]) -> str:
        if not history:
            return "No previous messages."
        lines = []
        for item in history[-12:]:
            role = str(item.get("role", "user")).lower()
            label = "Assistant" if role in ("assistant", "model", "ai") else "User"
            content = str(item.get("content", "")).strip()
            if content:
                lines.append(f"{label}: {content}")
        return "\n".join(lines) if lines else "No previous messages."

    def chat(
        self,
        message: str,
        history: Optional[List[Dict[str, Any]]] = None,
        context_text: Optional[str] = None,
        portfolio: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        context_text = context_text or MarketContextService.build_context_text()
        portfolio_text = (portfolio or "").strip() or "Not provided."
        prompt = (
            "MARKET SNAPSHOT\n"
            f"{context_text}\n\n"
            "USER PORTFOLIO / PREFERENCES\n"
            f"{portfolio_text}\n\n"
            "CONVERSATION SO FAR\n"
            f"{self._format_history(history)}\n\n"
            "USER MESSAGE\n"
            f"{message.strip()}\n\n"
            "Respond as the dashboard assistant. Use the snapshot above. "
            "If the user asks for a purchase view, give an action and the evidence, "
            "plus the main risk. Do not invent data."
        )
        answer = self._generate(
            prompt,
            MarketContextService.SYSTEM_INSTRUCTION,
            temperature=temperature,
            max_output_tokens=2048,
        )
        if not answer:
            raise GeminiError("Gemini returned an empty response. Try rephrasing the question.")
        return answer

    def recommend(
        self,
        risk_profile: str = "Balanced",
        horizon: str = "Medium term (6-12 months)",
        max_picks: int = 5,
        budget: Optional[float] = None,
        holdings: Optional[str] = None,
        context_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        context_text = context_text or MarketContextService.build_context_text()
        budget_text = f"₹{budget:,.0f}" if budget else "Not specified"
        holdings_text = (holdings or "").strip() or "No existing holdings provided."
        prompt = (
            "MARKET SNAPSHOT\n"
            f"{context_text}\n\n"
            "USER PROFILE\n"
            f"Risk profile: {risk_profile}\n"
            f"Investment horizon: {horizon}\n"
            f"Budget: {budget_text}\n"
            f"Existing holdings / constraints: {holdings_text}\n\n"
            "TASK\n"
            f"Suggest at most {max_picks} NIFTY 200 stocks for the user to consider purchasing now. "
            "Mix actions sensibly for the risk profile. Every stock must appear in the snapshot. "
            "For each pick include the RSI evidence, the 30-day trend, an allocation percentage "
            "of the budget (total allocations must not exceed 100), and the main risk. "
            "Also include any names the user should avoid or watch and explain why in the rationale. "
            "Return ONLY this JSON object:\n"
            "{\n"
            '  "summary": "2-4 sentence market and strategy view",\n'
            '  "recommendations": [\n'
            "    {\n"
            '      "symbol": "RELIANCE",\n'
            '      "company_name": "Reliance Industries Ltd.",\n'
            '      "action": "BUY | ACCUMULATE | WATCH | AVOID | HOLD",\n'
            '      "confidence": 0,\n'
            '      "allocation_percent": 0,\n'
            '      "rationale": "evidence from RSI 22/44/66 and 30-day change",\n'
            '      "risks": "main risk"\n'
            "    }\n"
            "  ],\n"
            '  "portfolio_note": "diversification or rebalancing note",\n'
            '  "disclaimer": "short educational-use disclaimer"\n'
            "}"
        )
        raw = self._generate(
            prompt,
            MarketContextService.RECOMMENDATION_INSTRUCTION,
            temperature=min(self.temperature, 0.4),
            max_output_tokens=3072,
            json_mode=True,
        )
        return self._parse_json(raw)

    def assess_stock(
        self,
        symbol: str,
        company_name: str,
        stock_row: str,
        context_text: Optional[str] = None,
        holdings: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a compact purchase-view for one stock as structured JSON."""
        context_text = context_text or MarketContextService.build_context_text()
        holdings_text = (holdings or "").strip() or "No existing holdings provided."
        prompt = (
            "MARKET SNAPSHOT\n"
            f"{context_text}\n\n"
            "SELECTED STOCK\n"
            f"{symbol} | {company_name}\n"
            f"{stock_row}\n\n"
            "USER HOLDINGS / CONSTRAINTS\n"
            f"{holdings_text}\n\n"
            "TASK\n"
            f"Give an educational purchase view for {symbol} using only the snapshot. "
            "Balance the RSI 22/44/66 readings and the 30-day change. "
            "Return ONLY this JSON object:\n"
            "{\n"
            '  "symbol": "' + symbol + '",\n'
            '  "action": "BUY | ACCUMULATE | WATCH | AVOID | HOLD",\n'
            '  "confidence": 0,\n'
            '  "summary": "one short sentence",\n'
            '  "rationale": "2-3 sentences with RSI evidence",\n'
            '  "risks": "main risk",\n'
            '  "suitable_for": "investor style or horizon this may suit"\n'
            "}"
        )
        raw = self._generate(
            prompt,
            MarketContextService.SYSTEM_INSTRUCTION,
            temperature=min(self.temperature, 0.3),
            max_output_tokens=1024,
            json_mode=True,
        )
        result = self._parse_json(raw)
        if not result.get("symbol"):
            result["symbol"] = symbol
        return result

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        text = (raw or "").strip()
        if not text:
            raise GeminiError("Gemini returned an empty recommendation.")
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced:
            try:
                parsed = json.loads(fenced.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        return {
            "summary": text,
            "recommendations": [],
            "portfolio_note": "",
            "disclaimer": "",
        }
