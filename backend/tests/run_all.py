"""Запуск всех проверок разом.

    .\\venv\\Scripts\\python.exe -W ignore tests\\run_all.py

Каждый тест — самодостаточный скрипт: он печатает отчёт и завершается
кодом 0 при успехе. Этот раннер запускает их по очереди в отдельных
процессах и печатает сводку.

Почему не pytest: в проекте его нет, а проверки самодостаточны —
подключать зависимость ради пяти файлов незачем.

ОСТОРОЖНО: проверки работают по настоящей базе и ходят в GitLab.
На боевой установке не запускать.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent

# Порядок от быстрых к медленным: если что-то сломано, дешёвое
# проверяется первым и не приходится ждать модель.
TESTS = [
    ("Каскадное удаление проекта", "test_cascade_delete.py"),
    ("Ветка по умолчанию", "test_branch_default.py"),
    ("Пользовательские эндпоинты", "test_users_endpoints.py"),
    ("Подтверждение предложения", "test_suggestion_confirm.py"),
    ("Фильтр предложений", "test_suggestions_filter.py"),
    ("Объём и честность прогресса", "test_progress_volume.py"),
    ("Тип задачи", "test_task_type.py"),
    ("Управление моделями", "test_admin_models.py"),
    ("Управление хранилищем", "test_admin_storage.py"),
    ("Поиск пользователей", "test_user_search.py"),
    ("Поиск задач", "test_task_search.py"),
    ("Запуск приложения", "test_startup.py"),
    ("Руководства", "test_docs_serving.py"),
    ("Файлы поставки", "test_repo_files.py"),
    ("Фон проекта", "test_project_background.py"),
    ("Отклонённая привязка", "test_rejected_link.py"),
    ("Фоновое дооболжение", "test_enrichment.py"),
]

# Итоговая строка каждого скрипта: «ИТОГ: 19/19 проверок пройдено»
TOTAL_RE = re.compile(r"ИТОГ:\s*(\d+)\s*/\s*(\d+)\s*проверок")


def run(title: str, filename: str) -> tuple[int, int, str]:
    path = HERE / filename
    if not path.exists():
        print(f"\n{'=' * 62}\n{title}\n  ! нет файла {filename}")
        return 0, 1, "нет файла"

    print(f"\n{'=' * 62}\n{title}\n{'-' * 62}")
    env = dict(os.environ)
    # PYTHONPATH нужен, чтобы app.* находился при запуске из tests/
    env["PYTHONPATH"] = str(BACKEND)
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.run(
        [sys.executable, "-W", "ignore", str(path)],
        cwd=str(BACKEND),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    output = proc.stdout or ""
    # Отчёты могут быть длинными — печатаем всё, кроме SQL-мусора
    for line in output.splitlines():
        if "sqlalchemy.engine" in line:
            continue
        print(line)

    match = TOTAL_RE.search(output)
    if match:
        return int(match.group(1)), int(match.group(2)), ""
    return 0, 1, (proc.stderr or "").strip().splitlines()[-1] if proc.stderr else "нет итога"


def main() -> int:
    print("=" * 62)
    print("Проверки AI-PM. Работают по настоящей базе и данным.")
    print("=" * 62)

    results = []
    for title, filename in TESTS:
        passed, total, err = run(title, filename)
        results.append((title, passed, total, err))

    print(f"\n{'=' * 62}\nСВОДКА\n{'=' * 62}")
    sum_passed = sum_total = 0
    for title, passed, total, err in results:
        mark = "OK  " if passed == total and total else "FAIL"
        line = f"  {mark} {title:<32} {passed}/{total}"
        if err:
            line += f"  — {err}"
        print(line)
        sum_passed += passed
        sum_total += total

    print(f"\n  ИТОГО: {sum_passed}/{sum_total} проверок пройдено")
    failed = [t for t, p, n, _ in results if p != n]
    if failed:
        print("\n  Не прошли:")
        for t in failed:
            print(f"    - {t}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
