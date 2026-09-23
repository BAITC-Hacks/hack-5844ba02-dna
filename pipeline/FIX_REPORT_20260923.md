# Pipeline handoff — 2026-09-23

Base: `d881a5d3a8abb6d557e0b958c4bee9d2f442be53` (`main`).  Рабочая
изменённая версия не закоммичена; чужие `api/`, `web/`, `out/` и bytecode не
включать в checkpoint.

| ID | Status | Evidence |
| --- | --- | --- |
| SCORE-001 | FIXED | `score_breakdown` содержит окончательные нормированные вклады; их сумма равна `priority_score` для всех узлов (допуск `1e-12`). |
| ROLE-001 | FIXED | Evidence больше не утверждает внешний источник средств или происхождение от seed: указывает наблюдаемое соотношение, направленные пути и модельную оценку потока. |
| DATA-002 | FIXED | `sanity_check` проверяет уникальность, endpoints, конечность/знак сумм, агрегированные суммы и `n_tx`; мутации `+12345 KZT` и `+7 n_tx` покрыты тестом. |
| TEST-001 | FIXED (pipeline scope) | Добавлены проверки breakdown, evidence, сходимости flow, защиты sanity-check и суммы совместимого fast-pass. |
| METHOD-001 | KEPT_WITH_EVIDENCE | Frontier по-прежнему использует согласованное правило роли из `config.yaml`; metadata теперь явно называет target proxy и запрещает трактовать оценку как наблюдаемое удержание денег. README-объяснение остаётся частью DOC-001. |
| METHOD-002 | FIXED (pipeline scope) | Fast-pass учитывает только минимальную совместимую сумму, а не весь вход; flow экспортирует convergence/residual и method. Это сигнал совместимости, не доказательство движения тех же денег. |

Проверки:

```text
python3 -m pipeline --data data --out /private/tmp/.../out  # 8.32 s
python3 -m pytest -q tests/test_pipeline.py                 # 7 passed, 27.67 s
git diff --check                                             # clean
```

Fresh output: 2,248 nodes, 3,119 edges; максимальная ошибка reconstruction
breakdown `2.22e-16`; flow converged (`9.9235e-7`, tolerance `1e-6`);
frontier AUC `0.6841486826426585`.

Open integration items: Aibek должен отразить новые flow columns/summary в
карточке только при необходимости и синхронизировать ROLE-001 wording в API;
необходимы его P0 `INT-001`, `DATA-001`, `UI-001` и общий browser smoke.
