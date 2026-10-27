"""Interactive terminal interface for the OLX agent."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Optional

import anthropic

from .agent import AgentEvents, OlxAgent
from .config import Config
from .images import ImageError, prepare_image

HELP = """\
Napisz, czego szukasz, np. „Szukam iPhone'a 13 128 GB do 1900 zł, Kraków lub wysyłka”.
Możesz wkleić link do ogłoszenia, odpowiedź sprzedawcy albo poprosić o porównanie, plan negocjacji czy checklistę odbioru.

Komendy:
  /zdjecie <ścieżka> [komentarz]   dołącz zdjęcie z dysku (np. zrzut rozmowy, dodatkowe zdjęcia od sprzedawcy)
  /tracker                          pokaż śledzone ogłoszenia i preferencje
  /nowa                             nowa rozmowa (tracker i preferencje zostają)
  /koszt                            zużycie tokenów w tej sesji
  /pomoc                            ta pomoc
  /wyjdz                            zakończ (także Ctrl+D)
"""


class _Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text


class ConsoleEvents(AgentEvents):
    def __init__(self, style: _Style) -> None:
        self.style = style
        self._progress_open = False
        self._text_open = False

    def _close_progress(self) -> None:
        if self._progress_open:
            sys.stdout.write("\n")
            self._progress_open = False

    def on_text(self, text: str) -> None:
        self._close_progress()
        if not self._text_open:
            sys.stdout.write(self.style("Agent> ", "1;32"))
            self._text_open = True
        sys.stdout.write(text)
        sys.stdout.flush()

    def on_progress(self, text: str) -> None:
        if not self._progress_open:
            sys.stdout.write(self.style("  · ", "2"))
            self._progress_open = True
        sys.stdout.write(self.style(text.replace("\n", " "), "2"))
        sys.stdout.flush()

    def on_block_end(self, block_type: Optional[str]) -> None:
        self._close_progress()
        if block_type == "text" and self._text_open:
            sys.stdout.write("\n")
            self._text_open = False

    def on_tool_call(self, name: str, args: dict[str, Any]) -> None:
        self._close_progress()
        shown = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items() if v not in (None, [], ""))
        if len(shown) > 160:
            shown = shown[:157] + "..."
        print(self.style(f"  ⚙ {name}({shown})", "36"))

    def on_tool_result(self, name: str, is_error: bool, summary: str) -> None:
        mark, color = ("✗", "31") if is_error else ("✓", "2")
        print(self.style(f"    {mark} {summary}", color))


def _attach_image(agent: OlxAgent, args: str) -> Optional[list[dict[str, Any]]]:
    try:
        parts = shlex.split(args)
    except ValueError as exc:
        print(f"Błędna komenda: {exc}")
        return None
    if not parts:
        print("Użycie: /zdjecie <ścieżka> [komentarz]")
        return None
    path = Path(parts[0]).expanduser()
    try:
        prepared = prepare_image(path.read_bytes(), max_edge=agent.config.zoom_max_edge, quality=agent.config.jpeg_quality)
    except (OSError, ImageError) as exc:
        print(f"Nie mogę wczytać {path}: {exc}")
        return None
    if not agent.images.fits(prepared.encoded_bytes):
        print("Wyczerpany budżet obrazów tej rozmowy — użyj /nowa.")
        return None
    comment = " ".join(parts[1:]) or "Obejrzyj to zdjęcie i powiedz, co z niego wynika dla zakupu."
    return [
        {"type": "text", "text": f"Załączam zdjęcie: {path.name}"},
        prepared.block(),
        {"type": "text", "text": comment},
    ]


def _run_turn(agent: OlxAgent, content: Any, *, stream: bool, style: _Style) -> None:
    try:
        result = agent.ask(content, stream=stream)
    except KeyboardInterrupt:
        print(style("\n[przerwano — ta wymiana została pominięta]", "33"))
        return
    except anthropic.AuthenticationError:
        print(style("Brak lub niepoprawny klucz API. Ustaw ANTHROPIC_API_KEY.", "31"))
        return
    except anthropic.RateLimitError:
        print(style("Limit zapytań API — odczekaj chwilę i spróbuj ponownie.", "31"))
        return
    except anthropic.APIStatusError as exc:
        print(style(f"Błąd API ({exc.status_code}): {exc.message}", "31"))
        return
    except anthropic.APIConnectionError:
        print(style("Brak połączenia z API Claude. Sprawdź sieć.", "31"))
        return
    if not stream and result.text:
        print(style("Agent> ", "1;32") + result.text)
    for notice in result.notices:
        print(style(f"[{notice}]", "33"))


def _print_usage(agent: OlxAgent) -> None:
    u = agent.usage
    print(
        f"Zapytania: {u['requests']}, wejście: {u['input_tokens']} tok. (+ cache odczyt {u['cache_read_input_tokens']}, "
        f"zapis {u['cache_creation_input_tokens']}), wyjście: {u['output_tokens']} tok.; "
        f"obrazy w rozmowie: {agent.images.used / 1024 / 1024:.1f} MB"
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="olx-agent", description="Agent zakupowy OLX.pl (Claude).")
    parser.add_argument("prompt", nargs="*", help="jednorazowe polecenie (bez niego: tryb interaktywny)")
    parser.add_argument("--model", help="model Claude (domyślnie claude-opus-5-5)")
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], help="poziom wysiłku modelu")
    parser.add_argument("--no-stream", action="store_true", help="bez strumieniowania odpowiedzi")
    args = parser.parse_args(argv)

    config = Config()
    if args.model:
        config.model = args.model
    if args.effort:
        config.effort = args.effort
    style = _Style(sys.stdout.isatty())
    agent = OlxAgent(config, events=ConsoleEvents(style))
    stream = not args.no_stream

    if args.prompt:
        _run_turn(agent, " ".join(args.prompt), stream=stream, style=style)
        return 0

    try:
        import readline  # noqa: F401  (line editing and history for input())
    except ImportError:
        pass

    print(style("Agent OLX", "1") + f" — model {config.model}, dane: {config.home}")
    print("Napisz, czego szukasz. /pomoc — komendy.\n")
    while True:
        try:
            line = input(style("Ty> ", "1;34")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.startswith("/"):
            command, _, rest = line.partition(" ")
            command = command.lower()
            if command in ("/wyjdz", "/wyjdź", "/exit", "/quit"):
                break
            if command in ("/pomoc", "/help"):
                print(HELP)
            elif command == "/tracker":
                print(agent.tracker.render_summary())
            elif command == "/nowa":
                agent.reset()
                print("Nowa rozmowa. Tracker i preferencje zostały zachowane.")
            elif command == "/koszt":
                _print_usage(agent)
            elif command in ("/zdjecie", "/zdjęcie", "/img"):
                content = _attach_image(agent, rest)
                if content:
                    _run_turn(agent, content, stream=stream, style=style)
            else:
                print("Nieznana komenda. /pomoc — lista komend.")
            continue
        _run_turn(agent, line, stream=stream, style=style)
    agent.olx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
