"""Создаёт новый каталог проекта из образца, не изменяя существующие каталоги."""

from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path
import re
import subprocess
import sys


BASE = Path(__file__).resolve().parents[1]
TEMPLATE = BASE / "template"


def single_line(value: str) -> str:
    """Подставляемые значения являются обычным текстом, а не командами или разметкой."""
    value = value.strip()
    if not value or any(ord(character) < 32 for character in value) or "{{" in value:
        raise argparse.ArgumentTypeError("Нужно непустое однострочное значение без полей образца.")
    return re.sub(r"([\\`*_{}\[\]<>])", r"\\\1", value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="новый каталог проекта")
    parser.add_argument("--name", type=single_line, required=True, help="название проекта")
    parser.add_argument("--purpose", type=single_line, default="Назначение пока не определено. Уточнить перед реализацией.", help="потребность, которую решает продукт")
    args = parser.parse_args()
    destination = args.destination.expanduser().resolve()
    if destination.exists():
        parser.error(f"Каталог уже существует и не будет изменён: {destination}")
    if destination.is_relative_to(TEMPLATE):
        parser.error("Нельзя создавать проект внутри копируемого образца.")

    # Ошибки самого образца обнаруживаются до создания каких-либо файлов проекта.
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    checked = subprocess.run(
        [sys.executable, str(TEMPLATE / "scripts/check_project.py"), "--template"],
        capture_output=True, text=True, encoding="utf-8", env=environment,
    )
    if checked.returncode:
        print(checked.stdout or checked.stderr, file=sys.stderr)
        return checked.returncode

    replacements = {
        "{{PROJECT_NAME}}": args.name,
        "{{PROJECT_PURPOSE}}": args.purpose,
        "{{CREATED_DATE}}": date.today().isoformat(),
    }
    planned: list[tuple[Path, str]] = []
    try:
        for source in sorted(TEMPLATE.rglob("*")):
            if "__pycache__" in source.parts:
                continue
            if source.is_symlink():
                raise ValueError(f"В образце обнаружена ссылка вместо обычного файла: {source}")
            if not source.is_file():
                continue
            content = source.read_text(encoding="utf-8-sig")
            # Один проход не обрабатывает подставленный пользовательский текст повторно.
            content = re.sub(r"\{\{(?:PROJECT_NAME|PROJECT_PURPOSE|CREATED_DATE)\}\}", lambda match: replacements[match.group()], content)
            planned.append((source.relative_to(TEMPLATE), content))

        destination.mkdir(parents=True, exist_ok=False)
        for relative, content in planned:
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            # Исключительное создание защищает от перезаписи и при появлении файла во время работы.
            with output.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Создание не завершено: {exc}", file=sys.stderr)
        print("Уже созданные файлы сохранены. Проверьте целевой каталог перед новой попыткой.", file=sys.stderr)
        return 1

    print(f"Проект создан: {destination}")
    print(f"Скопировано файлов: {len(planned)}. Начните с AGENTS.md.")
    print("После заполнения начальных сведений: python scripts/check_project.py --ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
