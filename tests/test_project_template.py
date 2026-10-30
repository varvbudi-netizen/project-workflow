"""Проверяет настоящий цикл создания проекта и обнаружение нарушений порядка."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEST_SPACE = (ROOT / ".verification").resolve()


class ProjectTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_SPACE.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="project-", dir=TEST_SPACE)
        self.sandbox = Path(self.temporary.name).resolve()
        self.project = self.sandbox / "Новый проект"

    def tearDown(self) -> None:
        # Удаление временной проверки разрешено только внутри выделенного каталога.
        self.sandbox.relative_to(TEST_SPACE)
        self.temporary.cleanup()

    def run_command(self, *arguments: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *arguments], cwd=cwd, capture_output=True,
            text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    def create(self, destination: Path | None = None) -> subprocess.CompletedProcess[str]:
        return self.run_command(
            "scripts/create_project.py", str(destination or self.project),
            "--name", "Проверочный проект", "--purpose", "Помочь редактору подготовить публикацию",
        )

    def check(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return self.run_command("scripts/check_project.py", *arguments, cwd=self.project)

    def test_created_project_is_portable_and_does_not_claim_readiness(self) -> None:
        created = self.create()
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertEqual(self.check().returncode, 0)
        readiness = self.check("--ready")
        self.assertNotEqual(readiness.returncode, 0)
        self.assertIn("требуется настройка", readiness.stdout)
        self.assertTrue((self.project / ".gitignore").is_file())
        self.assertTrue((self.project / ".github/workflows/hygiene.yml").is_file())
        for path in self.project.rglob("*.md"):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("{{PROJECT_", content)
            # Созданный проект не должен хранить пути компьютера, где лежит комплект.
            self.assertNotRegex(content, r"(?i)[a-z]:[/\\]+Users[/\\]")
            self.assertNotIn(ROOT.as_posix(), content)

    def test_existing_directory_is_preserved(self) -> None:
        self.project.mkdir()
        marker = self.project / "important.txt"
        marker.write_text("Работа пользователя", encoding="utf-8")
        result = self.create()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(marker.read_text(encoding="utf-8"), "Работа пользователя")
        self.assertEqual([path.name for path in self.project.iterdir()], ["important.txt"])

    def test_project_cannot_be_created_inside_template(self) -> None:
        destination = ROOT / "template" / "nested-test-project"
        self.assertFalse(destination.exists())
        result = self.create(destination)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(destination.exists())

    def test_broken_link_is_detected(self) -> None:
        self.assertEqual(self.create().returncode, 0)
        with (self.project / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("\n[Несуществующая инструкция](docs/missing.md)\n")
        checked = self.check()
        self.assertNotEqual(checked.returncode, 0)
        self.assertIn("missing.md", checked.stdout)

    def test_new_document_requires_registration(self) -> None:
        self.assertEqual(self.create().returncode, 0)
        document = self.project / "docs/EXTRA.md"
        document.write_text("# Решение\nСтатус: действующий. Обновлено: 2026-10-01.\n", encoding="utf-8")
        self.assertNotEqual(self.check().returncode, 0)
        with (self.project / "docs/README.md").open("a", encoding="utf-8") as handle:
            handle.write("\n[Дополнительный справочник](EXTRA.md)\n")
        self.assertEqual(self.check().returncode, 0)

    def test_active_task_must_be_visible_and_can_be_archived(self) -> None:
        self.assertEqual(self.create().returncode, 0)
        task = self.project / "docs/tasks/2026-10-01-example.md"
        task.write_text("# Задача\nСтатус: в работе.\n", encoding="utf-8")
        self.assertNotEqual(self.check().returncode, 0)
        status = self.project / "docs/STATUS.md"
        status.write_text(status.read_text(encoding="utf-8") + "\n[Задача](tasks/2026-10-01-example.md)\n", encoding="utf-8")
        self.assertEqual(self.check().returncode, 0)
        archived = self.project / "docs/archive/tasks" / task.name
        archived.parent.mkdir()
        task.resolve().relative_to(self.sandbox)
        archived.resolve().relative_to(self.sandbox)
        task.rename(archived)
        self.assertNotEqual(self.check().returncode, 0)
        status.write_text(status.read_text(encoding="utf-8").replace("(tasks/2026-10-01-example.md)", "(archive/tasks/2026-10-01-example.md)"), encoding="utf-8")
        self.assertEqual(self.check().returncode, 0)


if __name__ == "__main__":
    unittest.main()
