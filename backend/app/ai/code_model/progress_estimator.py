"""
progress_estimator — модуль оценки прогресса задачи.

Использование:
    import sys
    sys.path.append("/content/drive/MyDrive/Github_dataset")
    from progress_estimator import calculate_progress_detailed, EXPECTED_VOLUME

    result = calculate_progress_detailed(task, diffs, subtasks)
"""
import re, os, ast

EXPECTED_VOLUME = 26


def percentile(values, p):
    """Линейная интерполяция по методу NIST, как numpy.percentile.

    values непустой. p — процентиль в диапазоне 0..100.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    k = (len(ordered) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    frac = k - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac

def compute_global_expected_volume(df_lr1, percentile=75):
    """
    Медианный объём изменений по всему датасету ЛР №1.
    Используется как независимая оценка V_i^{est} для всех задач —
    иначе expected_volume вычисляется из тех же диффов, что оцениваются,
    и volume_progress вырождается в константу 1.0.
    """
    def diff_size(d):
        lines = str(d).split("\n")
        return sum(1 for l in lines if l.startswith("+") or l.startswith("-"))
    all_sizes = [diff_size(d) for d in df_lr1["diff_clean"].dropna()]
    if not all_sizes:
        return 200
    # Свой перцентиль вместо numpy: модуль должен работать без numpy,
    # иначе он не запускается в приложении до установки тяжёлых пакетов.
    return int(percentile(all_sizes, percentile))


def get_done_ratio_from_checklist(body):
    """Доля отмеченных [x] пунктов чеклиста от общего числа.
    Возвращает None, если чеклиста нет — такие задачи будут
    пропущены при формировании контрольного набора."""
    done  = len(re.findall(r"- \[x\]",     body or "", re.IGNORECASE))
    total = len(re.findall(r"- \[[ x]\]", body or "", re.IGNORECASE))
    return done / total if total > 0 else None


def extract_checklist_items(body):
    pattern = r"- \[( |x)\] (.+)"
    items = re.findall(pattern, body or "", re.IGNORECASE)
    return [
        {"text": text.strip(), "done": mark.lower() == "x"}
        for mark, text in items
    ]


def extract_files_from_body(body):
    """Имена файлов с расширениями кода, упомянутые в описании задачи."""
    pattern = r'\b[\w/.-]+\.(?:py|js|ts|java|go|rb|cpp|c|h|cs|kt|rs|php)\b'
    return list(set(re.findall(pattern, body or "")))


def structural_progress(subtasks):
    """Доля завершённых подзадач.
    subtasks — список словарей вида {'text': ..., 'done': bool}.
    Возвращает None, если декомпозиция отсутствует —
    это сигнализирует вызывающему коду о необходимости
    исключить составляющую и перераспределить веса."""
    if not subtasks:
        return None
    done_count = sum(1 for s in subtasks if s.get("done", False))
    return done_count / len(subtasks)


def volume_progress(commits_diffs, expected_volume):
    """Нормированный объём внесённых изменений.
    commits_diffs — список текстов диффов привязанных к задаче фиксаций;
    expected_volume — медианный объём диффов по задаче в строках кода.
    """
    if not expected_volume or expected_volume <= 0:
        return None
    total_lines_changed = 0
    for diff in commits_diffs:
        lines = str(diff).split("\n")
        total_lines_changed += sum(1 for l in lines if l.startswith("+") or l.startswith("-"))
    return min(total_lines_changed / expected_volume, 1.0)


def semantic_progress(files_touched, files_mentioned):
    """Доля упомянутых в задаче файлов, реально затронутых фиксациями.
    files_touched   — список файлов из files_list коммитов (из ЛР №1).
    files_mentioned — список файлов из описания задачи.
    Сравниваем только по basename, чтобы не зависеть от пути.
    Возвращает None, если упомянутых файлов нет."""
    if not files_mentioned:
        return None
    touched_base   = {os.path.basename(f) for f in files_touched}
    mentioned_base = {os.path.basename(f) for f in files_mentioned}
    return len(touched_base & mentioned_base) / len(mentioned_base)


def calculate_progress_detailed(task, commits_diffs, subtasks=None):
    """Итоговый прогресс задачи.

    Формула изменена после того, как замер показал: при отсутствии
    подзадач метрика физически не выходила за пределы 50–65%. Половину
    балла давал сам факт затронуть файл, названный в описании задачи,
    независимо от объёма работы, — и 21 изменённая строка давала те же
    52%, что и 23.

    Теперь семантика — не слагаемое с весом, а множитель прицельности:

        completion = объём × прицельность,
        прицельность = 1,0, если файлы не упомянуты,
                     = 0,5 + 0,5·семантика, иначе.

    Смысл: попадание в нужные файлы не заслуживает баллов само по себе —
    оно лишь снимает половину штрафа за работу не по тем файлам.
    Без подзадач прогресс равен completion, с подзадачами структурная
    составляющая остаётся ведущей, но объём входит через completion,
    а не отдельно.

    Демпфирование объёма ×0,3 убрано: оно было призвано притормозить
    подготовительные коммиты, но в схеме с умножением вред от них и так
    ограничен тем, что подготовительные коммиты обычно трогают не те
    файлы, и коэффициент просто срезал объём до 15%.
    """
    struct = structural_progress(subtasks) if subtasks else None
    vol    = volume_progress(commits_diffs, task.get("expected_volume", 200))
    sem    = semantic_progress(
        task.get("files_touched", []),
        task.get("files_mentioned", [])
    )

    vol = vol if vol is not None else 0.0

    # Нет упомянутых файлов — нечем судить о прицельности, штрафовать
    # за отсутствие улик нельзя.
    if sem is None:
        targeting = 1.0
    else:
        targeting = 0.5 + 0.5 * sem

    completion = vol * targeting

    if struct is None:
        progress = completion
        struct = 0.0
    else:
        progress = 0.6 * struct + 0.4 * completion

    return {
        "progress_percent":     round(min(progress * 100, 100), 1),
        "structural_component": round(struct, 3),
        "volume_component":     round(vol,    3),
        "semantic_component":   round(sem if sem is not None else 0.0, 3),
        "targeting_component":  round(targeting, 3),
        "completion_component": round(completion, 3),
    }


def build_test_cases(df):
    """Преобразует строки дообогащённого датасета в контрольные примеры.
    Каждый пример содержит:
    - task:          словарь с expected_volume и files_mentioned
    - commits_diffs: список диффов привязанных коммитов
    - subtasks:      список {'text', 'done'} или None
    - true_progress: эталонный прогресс 0..1 из чеклиста"""
    cases = []
    for _, row in df.iterrows():
        try:
            subtasks = ast.literal_eval(str(row["subtasks"]))
        except Exception:
            subtasks = None
        try:
            files = ast.literal_eval(str(row["files_mentioned"]))
        except Exception:
            files = []
        try:
            touched = ast.literal_eval(str(row["files_touched"]))
        except Exception:
            touched = []
        try:
            diffs = ast.literal_eval(str(row["diffs"]))
        except Exception:
            diffs = []
        cases.append({
            "task": {
                "expected_volume": int(row.get("expected_volume", 200)),
                "files_mentioned": files,
                "files_touched":   touched,
            },
            "commits_diffs": diffs,
            "subtasks":      subtasks if subtasks else None,
            "true_progress": float(row["checklist_ratio"]),
        })
    print(f"Контрольный набор: {len(cases)} примеров")
    return cases


def evaluate_progress_model(test_cases):
    """test_cases — список словарей с полями task, commits_diffs,
    subtasks (может быть None) и true_progress (эталон 0..1)."""
    y_true, y_pred = [], []
    for case in test_cases:
        result = calculate_progress_detailed(
            case["task"], case["commits_diffs"], case.get("subtasks")
        )
        y_pred.append(result["progress_percent"] / 100.0)
        y_true.append(case["true_progress"])
    # Раньше здесь стоял mean_absolute_error из sklearn, но sklearn
    # нигде не импортировался — функция падала с NameError при первом вызове.
    mae = sum(abs(t - p) for t, p in zip(y_true, y_pred)) / len(y_true) if y_true else float("nan")
    print(f"MAE_π = {mae:.4f}")
    print(f"θ_full = 0.15, θ_partial = 0.25")
    if mae <= 0.15:
        print("Результат: a_i = 1 (полная автоматизация)")
    elif mae <= 0.25:
        print("Результат: a_i = 0.5 (частичная автоматизация)")
    else:
        print("Результат: a_i = 0 (порог применимости не достигнут)")
    return mae

