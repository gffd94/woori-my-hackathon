"""시험 세트로 판정 방식 A·B·D를 LangSmith 실험으로 돌려 비교한다.

    .venv\\Scripts\\python.exe -m eval.run_experiments --ids K-006 --experiments D   # 시범 1건
    .venv\\Scripts\\python.exe -m eval.run_experiments                    # 전체
    .venv\\Scripts\\python.exe -m eval.run_experiments --experiments D --tag v2           # 수정 후 D만 재실행
    .venv\\Scripts\\python.exe -m eval.run_experiments --set validation --tag v2         # 검증 세트

- A llm_only : 같은 모델(OPENAI_MODEL)에 문자만 주고 스미싱 여부를 묻는다 (일반 챗봇 대표).
- B llm_db   : A에 악성 단서·공식 도메인 DB 조회를 더한다. 악성 일치면 LLM 없이 RISK.
- D service  : 실제 /analyze 흐름(DB 조회 + 수법 카드 검색 + LLM 신호 + 서버 규칙). 기록 저장은 하지 않는다.

LangSmith에는 마스킹한 문자와 ID만 올린다. 판정에 쓰는 원문은 로컬 eval/data/testset.jsonl에서 ID로 읽는다.
DB 대조 단계는 원래 값 대신 개수만 기록한다. 서버·테스트에서는 추적하지 않도록 이 스크립트에서만 켠다.
"""

import argparse
import json
import os
import urllib.request
from collections import defaultdict
from functools import partial
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ["LANGSMITH_TRACING"] = "true"

from langsmith import Client, evaluate, traceable  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.services import repository  # noqa: E402
from app.services.analyzer import Analyzer, _evaluate, _new_session  # noqa: E402
from app.services.embedding import request_embedding  # noqa: E402
from app.services.extractor import extract_entities  # noqa: E402
from app.services.llm_judge import judge as llm_judge  # noqa: E402
from app.services.masking import mask_text  # noqa: E402

RESULTS = ROOT / "eval" / "data"
# --set 이름 → (로컬 파일, LangSmith 데이터셋)
SETS = {
    "test": (RESULTS / "testset.jsonl", "smishing-testset-v1"),
    "validation": (RESULTS / "validation.jsonl", "smishing-validation-v1"),
}
TESTSET, DATASET_NAME = SETS["test"]
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

GENERAL_SYSTEM = (
    "너는 휴대폰 문자가 스미싱(문자 사기)인지 판단하는 도우미다. "
    '아래 JSON 하나로만 답한다: {"verdict": "RISK" 또는 "SAFE", "reason": "한 문장"}'
)

_RAW: dict[str, str] = {}


def _load_testset() -> list[dict]:
    rows = [json.loads(line) for line in TESTSET.read_text(encoding="utf-8").splitlines() if line]
    _RAW.update({row["id"]: row["text"] for row in rows})
    return rows


# --- 추적되는 외부 호출 ---

@traceable(run_type="llm", name="openai_chat", metadata={"ls_provider": "openai", "ls_model_name": MODEL})
def _chat(messages: list[dict]) -> dict:
    body = {"model": MODEL, "messages": messages, "response_format": {"type": "json_object"}, "temperature": 0}
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    usage = data.get("usage") or {}
    return {
        "choices": data["choices"],
        "usage_metadata": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


def _llm_text(system: str, user: str) -> str:
    """llm_judge.call_openai와 같은 설정. 응답 본문만 돌려준다."""
    out = _chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
    return out["choices"][0]["message"]["content"]


def _count_entities(inputs: dict) -> dict:
    e = inputs.get("extracted")
    return {"urls": len(e.urls), "domains": len(e.domains), "phones": len(e.phones)} if e else {}


@traceable(name="lookup", process_inputs=_count_entities,
           process_outputs=lambda out: {"indicator_ids": [m.id for m in out.indicators],
                                        "official_domains": len(out.official_domains)})
def _lookup(extracted):
    return repository.lookup_indicators(extracted, session_factory=_new_session)


@traceable(name="embed", process_outputs=lambda out: {"dimensions": len(out)})
def _embed(masked: str) -> list[float]:
    return request_embedding(masked, settings=load_settings())


@traceable(name="search", process_inputs=lambda inputs: {"masked": inputs.get("masked")})
def _search(masked: str, vector: list[float]):
    return repository.search_cards(masked, vector, session_factory=_new_session)


@traceable(name="llm_judge")
def _judge(masked: str, cards: list[str], labels: dict):
    return llm_judge(masked, cards, _llm_text, entity_lookup=labels)


def _no_save(record) -> None:
    pass


# --- 실험 대상 ---

def _general_verdict(masked: str, db_lines: str | None = None) -> dict:
    user = f"다음 문자가 스미싱인지 판단해줘.\n<message>\n{masked}\n</message>"
    if db_lines:
        user = f"[URL·번호 DB 조회 결과]\n{db_lines}\n\n" + user
    try:
        answer = json.loads(_llm_text(GENERAL_SYSTEM, user))
        verdict = answer.get("verdict") if answer.get("verdict") in ("RISK", "SAFE") else "UNKNOWN"
        return {"verdict": verdict, "risk_level": None, "reasons": [str(answer.get("reason", ""))[:100]]}
    except Exception as exc:
        return {"verdict": "UNKNOWN", "risk_level": None, "reasons": [type(exc).__name__]}


def target_llm_only(inputs: dict) -> dict:
    return _general_verdict(mask_text(_RAW[inputs["id"]]))


def target_llm_db(inputs: dict) -> dict:
    raw = _RAW[inputs["id"]]
    masked = mask_text(raw)
    extracted = extract_entities(raw)
    try:
        elements = _evaluate(extracted, _lookup(extracted))
    except Exception as exc:
        return {"verdict": "UNKNOWN", "risk_level": None, "reasons": [f"DB {type(exc).__name__}"]}
    if elements.malicious_types or elements.conflict:
        return {"verdict": "RISK", "risk_level": "high", "reasons": ["DB 악성 일치"]}
    db_lines = "\n".join(f"- {value}: {label or '미등록'}" for value, label in elements.labels.items()) or None
    return _general_verdict(masked, db_lines)


_SERVICE = Analyzer(lookup=_lookup, embed=_embed, search=_search, judge=_judge, save=_no_save,
                    model_version=MODEL)


def target_service(inputs: dict) -> dict:
    result = _SERVICE.analyze(_RAW[inputs["id"]])
    return {"verdict": result.status.value, "risk_level": result.risk_level, "reasons": result.reasons,
            "matched_cases": result.matched_cases}


EXPERIMENTS = {
    "A": ("llm_only", target_llm_only),
    "B": ("llm_db", target_llm_db),
    "D": ("service", target_service),
}


# --- 채점 ---

def correct(outputs: dict, reference_outputs: dict) -> dict:
    """스미싱은 RISK, 정상은 SAFE가 정답. UNKNOWN은 오답이다."""
    want = "RISK" if reference_outputs["label"] == "smishing" else "SAFE"
    return {"key": "correct", "score": int(outputs["verdict"] == want)}


def rates(outputs: list[dict], reference_outputs: list[dict]) -> dict:
    smish = [o for o, r in zip(outputs, reference_outputs) if r["label"] == "smishing"]
    normal = [o for o, r in zip(outputs, reference_outputs) if r["label"] == "normal"]

    def share(items, cond):
        return round(sum(cond(o) for o in items) / len(items), 4) if items else None

    return {"results": [
        {"key": "탐지율", "score": share(smish, lambda o: o["verdict"] == "RISK")},
        {"key": "오탐률", "score": share(normal, lambda o: o["verdict"] == "RISK")},
        {"key": "오탐률_높은위험만", "score": share(normal, lambda o: o["verdict"] == "RISK" and o["risk_level"] != "low")},
        {"key": "보류율", "score": share(outputs, lambda o: o["verdict"] == "UNKNOWN")},
    ]}


# --- 실행 ---

def _ensure_dataset(client: Client, rows: list[dict]) -> None:
    if client.has_dataset(dataset_name=DATASET_NAME):
        if client.read_dataset(dataset_name=DATASET_NAME).example_count == len(rows):
            return
        raise SystemExit(f"LangSmith 데이터셋 {DATASET_NAME}의 건수가 로컬과 다릅니다. 이름을 바꾸거나 지운 뒤 다시 실행하세요.")
    dataset = client.create_dataset(DATASET_NAME, description="스미싱 판별 비교 시험 세트 (마스킹한 문자)")
    client.create_examples(
        dataset_id=dataset.id,
        examples=[{
            "inputs": {"id": row["id"], "text_masked": mask_text(row["text"])},
            "outputs": {"label": row["label"]},
            "metadata": {"group": row["group"], "source": row["source"]},
        } for row in rows],
    )


def _summarize(name: str, results, groups: dict[str, str]) -> None:
    table = defaultdict(lambda: [0, 0])
    saved = []
    for row in results:
        example, run = row["example"], row["run"]
        verdict = (run.outputs or {}).get("verdict", "ERROR")
        want = "RISK" if example.outputs["label"] == "smishing" else "SAFE"
        group = groups[example.inputs["id"]]
        table[group][0] += verdict == want
        table[group][1] += 1
        saved.append({"id": example.inputs["id"], "group": group, "label": example.outputs["label"],
                      **(run.outputs or {})})
    print(f"\n[{name}] 묶음별 정답률")
    for group, (ok, total) in sorted(table.items()):
        print(f"  {group:18} {ok}/{total} ({ok / total:.0%})")
    (RESULTS / f"results_{name}.json").write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiments", default="A,B,D")
    parser.add_argument("--limit", type=int, default=None, help="앞에서부터 N건만 (시범 실행)")
    parser.add_argument("--ids", default=None, help="이 ID만 실행 (쉼표 구분, 시범 실행)")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--set", choices=sorted(SETS), default="test", help="test(1차) 또는 validation(검증)")
    parser.add_argument("--tag", default="", help="실험 이름 뒤에 붙일 표시 (예: v2)")
    args = parser.parse_args()

    global TESTSET, DATASET_NAME
    TESTSET, DATASET_NAME = SETS[args.set]

    rows = _load_testset()
    groups = {row["id"]: row["group"] for row in rows}
    client = Client()
    _ensure_dataset(client, rows)
    examples = list(client.list_examples(dataset_name=DATASET_NAME))
    examples.sort(key=lambda e: e.inputs["id"])
    if args.ids:
        wanted = set(args.ids.split(","))
        examples = [e for e in examples if e.inputs["id"] in wanted]
    if args.limit:
        examples = examples[:args.limit]

    for key in args.experiments.split(","):
        name, target = EXPERIMENTS[key.strip()]
        if args.tag:
            name = f"{name}-{args.tag}"
        results = evaluate(
            target,
            data=examples,
            evaluators=[correct],
            summary_evaluators=[rates],
            experiment_prefix=f"{key}-{name}",
            metadata={"model": MODEL, "testset": DATASET_NAME, "count": len(examples)},
            max_concurrency=args.concurrency,
        )
        _summarize(f"{args.set}-{key}-{name}", results, groups)


if __name__ == "__main__":
    main()
