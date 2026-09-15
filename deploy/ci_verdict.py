"""Вердикт тестов GitHub Actions по коммиту — для deploy/pull-deploy.sh.

Читает из stdin ответ `GET /repos/{repo}/commits/{sha}/check-runs` и печатает
одно слово:
  success — хоть один прогон тестов от GitHub Actions зелёный;
  failure — все прогоны завершены, зелёного нет;
  pending — прогонов ещё нет или какой-то идёт.

⚠️ Засчитываются только проверки приложения `github-actions`. Check run может
создать любое приложение с правом checks:write, а выкатываем мы только то, что
прогнали наши собственные workflow.
"""
import json
import sys

TRUSTED_APP = "github-actions"


def verdict(payload: dict) -> str:
    runs = [
        run
        for run in payload.get("check_runs") or []
        if (run.get("app") or {}).get("slug") == TRUSTED_APP
    ]
    if any(run.get("conclusion") == "success" for run in runs):
        return "success"
    if runs and all(run.get("status") == "completed" for run in runs):
        return "failure"
    return "pending"


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        print("pending")  # битый ответ API — не решение, спросим на следующем тике
        return
    print(verdict(payload if isinstance(payload, dict) else {}))


if __name__ == "__main__":
    main()
