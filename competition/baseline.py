#!/usr/bin/env python3
"""
Бейзлайн-решение: отвечает на вопросы по учебнику с помощью GigaChat-2-Max.

Это СТАРТОВАЯ точка. Запустите её как есть — получите рабочий сабмит,
а дальше улучшайте (промпт, поиск по учебнику/RAG, few-shot и т.д.),
чтобы поднять балл на лидерборде.

Как запустить:
  1. Получите токен GigaChat у организаторов и положите его в файл .env
     (скопируйте .env.example -> .env и впишите токен):
         GIGACHAT_CREDENTIALS=<ваш токен>
         GIGACHAT_SCOPE=GIGACHAT_API_CORP
  2. python baseline.py
  3. Появится answers.csv — загрузите его в задачу на платформе.

Что делает бейзлайн:
  - читает вопросы лидерборда (questions.csv) и открытый тренировочный
    набор с ответами (train.jsonl);
  - берёт из train.jsonl несколько примеров как few-shot (в т.ч. пример
    «темы нет в учебнике»);
  - по каждому вопросу спрашивает GigaChat-2-Max, прося честно ответить
    «нет в учебнике», если темы в учебнике нет (иначе за выдумку 0 баллов);
  - сохраняет answers.csv (колонки question_id, answer).

Разрешена ТОЛЬКО модель GigaChat-2-Max. Удачи!
"""
import csv, json, os, ssl, sys, time, uuid
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
MODEL = "GigaChat-2-Max"
MAX_WORKERS = 1


def load_env():
    if os.path.exists(".env"):
        for line in open(".env", encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config():
    if os.path.exists("task_config.json"):
        return json.load(open("task_config.json", encoding="utf-8"))
    return {"textbook": "учебнику", "not_covered": "В учебнике эта тема не рассматривается"}


load_env()
CFG = load_config()
CREDS = os.environ.get("GIGACHAT_CREDENTIALS", "").strip()
SCOPE = os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_CORP").strip()
if not CREDS:
    print("Укажите GIGACHAT_CREDENTIALS в .env (см. .env.example).", file=sys.stderr)
    sys.exit(1)

# GigaChat использует российский корневой сертификат; в учебном решении просто
# отключаем проверку TLS. На рабочем сервере лучше поставить корневой сертификат НУЦ Минцифры.
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE
_tok = {"v": None, "exp": 0.0}


def token():
    if _tok["v"] and time.time() < _tok["exp"] - 60:
        return _tok["v"]
    body = urllib.parse.urlencode({"scope": SCOPE}).encode()
    req = urllib.request.Request(OAUTH_URL, data=body, method="POST", headers={
        "Authorization": "Basic " + CREDS, "RqUID": str(uuid.uuid4()),
        "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    d = json.load(urllib.request.urlopen(req, context=_SSL, timeout=30))
    _tok["v"] = d["access_token"]
    _tok["exp"] = float(d.get("expires_at", 0)) / 1000.0
    return _tok["v"]


def ask(system, user, max_tokens=450):
    payload = json.dumps({"model": MODEL, "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.0, "max_tokens": max_tokens}).encode()
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(CHAT_URL, data=payload, method="POST", headers={
                "Authorization": "Bearer " + token(), "Content-Type": "application/json", "Accept": "application/json"})
            r = urllib.request.urlopen(req, context=_SSL, timeout=90)
            return json.load(r)["choices"][0]["message"]["content"].strip()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def few_shot(path, n_pos=2, n_neg=1):
    if not os.path.exists(path):
        return ""
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    pos = [r for r in rows if (r.get("metadata", {}) or {}).get("answerable")][:n_pos]
    neg = [r for r in rows if not (r.get("metadata", {}) or {}).get("answerable")][:n_neg]
    return "\n\n".join(f"Вопрос: {r['input']}\nОтвет: {r['expected_output']}" for r in pos + neg)


def main():
    shots = few_shot("train.jsonl")
    system = (
        f"Ты отвечаешь на вопросы по учебнику «{CFG['textbook']}». Отвечай кратко и по существу, "
        f"строго по содержанию этого учебника. Если темы в учебнике НЕТ — не выдумывай ответ, "
        f"а напиши: «{CFG['not_covered']}»."
        + (f"\n\nПримеры правильных ответов:\n{shots}" if shots else "")
    )
    questions = list(csv.DictReader(open("questions.csv", encoding="utf-8-sig")))
    answers = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(ask, system, q["question"]): q["question_id"] for q in questions}
        for f in as_completed(futs):
            qid = futs[f]
            try:
                answers[qid] = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"  вопрос {qid}: ошибка {e}", file=sys.stderr)
                answers[qid] = ""
    with open("answers.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["question_id", "answer"])
        for q in questions:
            w.writerow([q["question_id"], answers.get(q["question_id"], "")])
    print(f"Готово: {len(questions)} ответов сохранено в answers.csv. Загрузите answers.csv в задачу на платформе.")


if __name__ == "__main__":
    main()
