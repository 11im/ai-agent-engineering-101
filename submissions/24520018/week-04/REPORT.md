# Week 04 — 자유, 태그, 구조화 메시지로 한 가격 협상

## 1. 설정

| 항목 | 값 |
|---|---|
| 제공자 / 호스트 | Anthropic, Claude Code CLI `claude -p` (2.1.283) |
| 모델 (본 제출) | `claude-haiku-4-5` |
| 모델 (추가 비교) | `claude-sonnet-4-5`, `claude-opus-4-5` (부록 A) |
| temperature | 설정 불가. `claude -p`에 temperature 옵션이 없어 CLI 기본값을 그대로 씀 |
| 턴 한도 | 10 메시지 (양쪽 합산, `protocol.MAX_TURNS`) |
| 시나리오 | `scenarios.json` 6개. 거래 가능 s1–s3, 불가능 s4–s6. 실행 전에 커밋함 (`661e394`) |
| 반복 | 조건마다 3회. 1회 실행 = 조건 1개 × 반복 1회 × 시나리오 6개 |

**호출 격리.** 에이전트와 reader는 매번 새 세션입니다. 저장소 밖 임시 디렉터리에서 다음 옵션으로 실행해서 CLAUDE.md, 프로젝트 설정, 도구, MCP가 들어가지 않게 했습니다 (`llm.py`).

```
claude -p --model <id> --system-prompt <system> --tools "" --setting-sources "" \
          --strict-mcp-config --no-session-persistence
```

CLI가 시스템 프롬프트 앞에 "You are a Claude agent, built on Anthropic's Claude Agent SDK." 한 줄과 작업 디렉터리, 날짜 같은 환경 정보를 붙입니다. 이 부분은 끌 수 없었고, 세 조건에 똑같이 들어갑니다.

**대화 전달.** `claude -p`는 한 번 부르고 끝나서, 매 턴 지금까지의 메시지를 번호와 화자를 붙인 텍스트로 만들어 user 메시지로 넣습니다 (`run.render`). 상대 메시지는 세 조건 모두 원문 그대로 보여 줍니다. 파싱 결과는 에이전트에게 보이지 않습니다.

**시스템 프롬프트.** `ROLE[role] + "\n\n" + FORMAT[condition]`입니다. `ROLE`은 세 조건이 같습니다. 네 가지 행동(가격 제시, 수락, 거절 후 계속, 협상 종료)을 일상어로 설명하고, "a counter-offer counts as a new price offer"를 넣었습니다. 전문은 `prompts.py`에 있습니다.

### 형식 문단 3개

- **free**: `Message format: write each message as a short plain-English chat message to the other side. No special formatting.`
- **tagged**: `Message format: begin every message with exactly one of these tags, in parentheses: (propose), (accept-proposal), (reject-proposal), (refuse). Use (propose) when you offer a price, and state that one price in the message. After the tag, write a short plain-English message. One tag per message, nothing before it.`
- **structured**: `Message format: reply with exactly one JSON object and nothing else: {"performative": P, "content": {"price": N}} P is one of "propose", "accept-proposal", "reject-proposal", "refuse". N is an integer number of dollars when P is propose, and null otherwise. No text outside the JSON object, no code fences.`

### Reader 프롬프트

free 조건의 `READER`(행위와 가격을 모두 읽음). `{speaker}`, `{message}`를 채웁니다.

```
Label one message from a price negotiation between a buyer and a seller.
Pick the single act the message performs, from exactly these four:
- propose: offers a specific price (a counter-offer is propose)
- accept-proposal: agrees to the other side's last offered price
- reject-proposal: declines the other side's offer without naming a new price, and keeps negotiating
- refuse: walks away and ends the negotiation
If the act is propose, also give the offered price.
Answer with one JSON object and nothing else: {"performative": "<act>", "price": <integer or null>}

Message from the {speaker}:
{message}
```

tagged 조건의 `PRICE_READER`(`(propose)` 메시지의 가격만 읽음).

```
The following negotiation message offers a price. Answer with that price as a plain integer
number of dollars, digits only. If the message does not state one single price, answer: none

Message:
{message}
```

reader의 시스템 프롬프트는 `You label negotiation messages. Follow the output format exactly.`입니다.

### 프로토콜 계층 규칙 (`protocol.py`)

- **free**: reader 응답에서 첫 `{`부터 마지막 `}`까지를 JSON으로 읽습니다. 행위가 네 개 중 하나가 아니거나, `propose`인데 가격이 없으면 format error로 셉니다.
- **tagged**: `(act)` 태그가 정확히 하나이고 메시지 맨 앞에 있어야 합니다. `propose`면 `PRICE_READER`를 한 번 부르고, 응답이 숫자 하나가 아니면 format error로 셉니다.
- **structured**: `json.loads`로 읽습니다. 바깥을 감싼 ```` ```json ```` 코드 블록 하나는 벗기고, 그 횟수를 `note`에 남깁니다. 이 규칙은 스모크 테스트에서 Haiku가 코드 블록을 붙여 10번 모두 실패한 뒤에 추가했습니다 (`smoke/v1`, 커밋 `9dcb956` → `7189803`).
- **종료 판정 `step()`**: `refuse`가 오면 결렬(`no_deal`)입니다. `accept-proposal`이 오면 **상대가 `propose`로 낸 마지막 가격**으로 거래(`deal`)가 성사됩니다. 상대가 낸 `propose`가 없으면 그 수락은 무시하고 `note`에 남깁니다. 파싱에 실패한 메시지는 행위가 없는 것으로 보고 협상을 이어 가며, 턴은 소모됩니다. 10번째 메시지 뒤에도 끝나지 않았으면 턴 한도(`open`)입니다.
- **점수**: 거래가 가능한 시나리오에서는 한도 안의 가격으로 거래했을 때만 `correct=1`입니다. 불가능한 시나리오에서는 거래하지 않았으면(`no_deal`, `open`) `correct=1`입니다. `violation=1`은 reserve 미만이나 budget 초과의 가격으로 거래한 경우입니다.

### 실행 방법

```bash
cd submissions/24520018/week-04
sh run_all.sh claude-haiku-4-5 results.csv logs 3        # 본 제출: 조건 3개를 병렬, 조건마다 반복 1..3 순차
sh run_all.sh claude-sonnet-4-5 extra/claude-sonnet-4-5/results.csv extra/claude-sonnet-4-5/logs 3
sh run_all.sh claude-opus-4-5   extra/claude-opus-4-5/results.csv   extra/claude-opus-4-5/logs 3
# 한 실행만: python run.py --condition tagged --repeat 2 --model claude-haiku-4-5
```

`results.csv`에 이미 있는 `(run, scenario)`는 건너뛰므로, 중간에 끊겨도 같은 명령으로 이어서 돌릴 수 있습니다. Claude Code에 로그인되어 있어야 하며 API 키는 쓰지 않습니다. Sonnet 비교 실행은 처음에 반복 1회로 시작했다가 멈추고 3회로 다시 돌렸습니다. 그래서 `extra/claude-sonnet-4-5/logs`에는 멈춘 시점의 에피소드가 중간까지 남아 있고, 이어서 다시 돌린 기록이 같은 파일 뒤에 붙어 있습니다.

## 2. 결과 (claude-haiku-4-5)

| condition | episodes | correct | violations | mean turns | format errors | reader calls | deal / no_deal / open |
|---|---|---|---|---|---|---|---|
| free | 18 | 18/18 | 0 | 8.9 | 1 | 160 (8.9/ep) | 9 / 2 / 7 |
| tagged | 18 | 18/18 | 0 | 9.0 | 8 | 109 (6.1/ep) | 9 / 3 / 6 |
| structured | 18 | 15/18 | 2 | 9.2 | 7 | 0 (0.0/ep) | 8 / 4 / 6 |

거래가 가능한 시나리오(조건마다 9개 에피소드)에서 한도 안 가격으로 거래한 수는 free 9, tagged 9, structured 6입니다. 거래가 불가능한 시나리오(조건마다 9개)에서는 세 조건 모두 거래가 한 번도 없었습니다.

**행위 분포** (로그 집계, 메시지 단위)

| condition | propose | accept | reject | refuse | 파싱 실패 | 가격을 담은 reject |
|---|---|---|---|---|---|---|
| free | 148 | 9 | **0** | 2 | 1 | — |
| tagged | 109 | 9 | 41 | 3 | 0 | 41 |
| structured | 120 | 9 | 26 | 4 | 7 | 25 |

### 에피소드별 결과 (`results.csv`)

| run | condition | scenario | deal_possible | outcome | price | correct | violation | turns | format_errors | reader_calls | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| free-1 | free | s1 | 1 | deal | 375 | 1 | 0 | 7 | 0 | 7 |  |
| free-1 | free | s2 | 1 | deal | 620 | 1 | 0 | 8 | 0 | 8 |  |
| free-1 | free | s3 | 1 | deal | 200 | 1 | 0 | 9 | 0 | 9 |  |
| free-1 | free | s4 | 0 | open |  | 1 | 0 | 10 | 0 | 10 |  |
| free-1 | free | s5 | 0 | open |  | 1 | 0 | 10 | 0 | 10 |  |
| free-1 | free | s6 | 0 | no_deal |  | 1 | 0 | 10 | 0 | 10 |  |
| free-2 | free | s1 | 1 | deal | 370 | 1 | 0 | 8 | 0 | 8 |  |
| free-2 | free | s2 | 1 | deal | 625 | 1 | 0 | 8 | 0 | 8 |  |
| free-2 | free | s3 | 1 | deal | 200 | 1 | 0 | 10 | 0 | 10 |  |
| free-2 | free | s4 | 0 | open |  | 1 | 0 | 10 | 0 | 10 |  |
| free-2 | free | s5 | 0 | open |  | 1 | 0 | 10 | 0 | 10 |  |
| free-2 | free | s6 | 0 | no_deal |  | 1 | 0 | 10 | 0 | 10 |  |
| free-3 | free | s1 | 1 | deal | 380 | 1 | 0 | 5 | 0 | 5 |  |
| free-3 | free | s2 | 1 | deal | 650 | 1 | 0 | 7 | 1 | 7 |  |
| free-3 | free | s3 | 1 | deal | 200 | 1 | 0 | 8 | 0 | 8 |  |
| free-3 | free | s4 | 0 | open |  | 1 | 0 | 10 | 0 | 10 |  |
| free-3 | free | s5 | 0 | open |  | 1 | 0 | 10 | 0 | 10 |  |
| free-3 | free | s6 | 0 | open |  | 1 | 0 | 10 | 0 | 10 |  |
| tagged-1 | tagged | s1 | 1 | deal | 387 | 1 | 0 | 8 | 1 | 7 |  |
| tagged-1 | tagged | s2 | 1 | deal | 650 | 1 | 0 | 10 | 0 | 8 |  |
| tagged-1 | tagged | s3 | 1 | deal | 200 | 1 | 0 | 9 | 0 | 6 |  |
| tagged-1 | tagged | s4 | 0 | open |  | 1 | 0 | 10 | 0 | 6 |  |
| tagged-1 | tagged | s5 | 0 | open |  | 1 | 0 | 10 | 0 | 10 |  |
| tagged-1 | tagged | s6 | 0 | no_deal |  | 1 | 0 | 8 | 1 | 4 |  |
| tagged-2 | tagged | s1 | 1 | deal | 390 | 1 | 0 | 8 | 2 | 6 |  |
| tagged-2 | tagged | s2 | 1 | deal | 630 | 1 | 0 | 8 | 0 | 4 |  |
| tagged-2 | tagged | s3 | 1 | deal | 200 | 1 | 0 | 10 | 0 | 6 |  |
| tagged-2 | tagged | s4 | 0 | open |  | 1 | 0 | 10 | 0 | 4 |  |
| tagged-2 | tagged | s5 | 0 | open |  | 1 | 0 | 10 | 0 | 7 |  |
| tagged-2 | tagged | s6 | 0 | no_deal |  | 1 | 0 | 9 | 2 | 6 |  |
| tagged-3 | tagged | s1 | 1 | deal | 360 | 1 | 0 | 7 | 0 | 5 |  |
| tagged-3 | tagged | s2 | 1 | deal | 635 | 1 | 0 | 6 | 0 | 4 |  |
| tagged-3 | tagged | s3 | 1 | deal | 200 | 1 | 0 | 10 | 0 | 7 |  |
| tagged-3 | tagged | s4 | 0 | open |  | 1 | 0 | 10 | 1 | 7 |  |
| tagged-3 | tagged | s5 | 0 | no_deal |  | 1 | 0 | 9 | 1 | 4 |  |
| tagged-3 | tagged | s6 | 0 | open |  | 1 | 0 | 10 | 0 | 8 |  |
| structured-1 | structured | s1 | 1 | deal | 360 | 1 | 0 | 8 | 0 | 0 | turn 7: accept with no offer from the other side; 8 fenced JSON message(s) |
| structured-1 | structured | s2 | 1 | deal | 650 | 1 | 0 | 7 | 0 | 0 | 7 fenced JSON message(s) |
| structured-1 | structured | s3 | 1 | open |  | 0 | 0 | 10 | 0 | 0 | 10 fenced JSON message(s) |
| structured-1 | structured | s4 | 0 | open |  | 1 | 0 | 10 | 0 | 0 | 10 fenced JSON message(s) |
| structured-1 | structured | s5 | 0 | open |  | 1 | 0 | 10 | 0 | 0 | 10 fenced JSON message(s) |
| structured-1 | structured | s6 | 0 | no_deal |  | 1 | 0 | 10 | 0 | 0 | 10 fenced JSON message(s) |
| structured-2 | structured | s1 | 1 | deal | 370 | 1 | 0 | 7 | 0 | 0 | 7 fenced JSON message(s) |
| structured-2 | structured | s2 | 1 | deal | 620 | 1 | 0 | 9 | 1 | 0 | 9 fenced JSON message(s) |
| structured-2 | structured | s3 | 1 | deal | 200 | 1 | 0 | 9 | 6 | 0 | 9 fenced JSON message(s) |
| structured-2 | structured | s4 | 0 | no_deal |  | 1 | 0 | 10 | 0 | 0 | 10 fenced JSON message(s) |
| structured-2 | structured | s5 | 0 | open |  | 1 | 0 | 10 | 0 | 0 | 10 fenced JSON message(s) |
| structured-2 | structured | s6 | 0 | open |  | 1 | 0 | 10 | 0 | 0 | 10 fenced JSON message(s) |
| structured-3 | structured | s1 | 1 | deal | 327 | 1 | 0 | 8 | 0 | 0 | 8 fenced JSON message(s) |
| structured-3 | structured | s2 | 1 | deal | 740 | 0 | 1 | 9 | 0 | 0 | 9 fenced JSON message(s) |
| structured-3 | structured | s3 | 1 | deal | 120 | 0 | 1 | 10 | 0 | 0 | 10 fenced JSON message(s) |
| structured-3 | structured | s4 | 0 | open |  | 1 | 0 | 10 | 0 | 0 | 10 fenced JSON message(s) |
| structured-3 | structured | s5 | 0 | no_deal |  | 1 | 0 | 10 | 0 | 0 | 10 fenced JSON message(s) |
| structured-3 | structured | s6 | 0 | no_deal |  | 1 | 0 | 9 | 0 | 0 | 9 fenced JSON message(s) |

## 3. FIPA-ACL과 세 조건 비교

| 항목 | FIPA-ACL (2002) | free | tagged | structured |
|---|---|---|---|---|
| 발화수반력이 있는 곳 | 필수 `performative` 필드 | 문장 전체. 명시적 표시가 없음 | 메시지 앞의 `(act)` 태그 | JSON `performative` 필드 |
| 내용 언어 | 형식 content language (SL 등)와 선언된 ontology | 영어 | 태그 뒤 영어 | `{"price": int}` 한 필드. ontology 선언 없음 |
| 내용을 해석하는 주체 | 수신 에이전트가 content language 문법으로 해석 | LLM reader가 행위와 가격을 모두 추측 | 행위는 regex, 가격은 LLM reader | `json.loads`. 모델이 관여하지 않음 |
| 대화가 끝나는 방식 | interaction protocol (예: FIPA Contract Net)이 정한 상태 전이 | reader가 `accept`/`refuse`로 읽은 메시지, 또는 턴 한도 | 태그가 `accept`/`refuse`인 메시지, 또는 턴 한도 | 필드가 `accept`/`refuse`인 메시지, 또는 턴 한도 |
| 성실성(sincerity)을 보장하는 것 | 의미론의 feasibility precondition. 검증은 하지 않고 전제로 둠 | 없음. 프롬프트의 역할 지시뿐 | 없음 | 없음. 가격이 한도 안인지도 하네스는 확인하지 않음 |
| 메시지를 읽는 비용 | 파서 한 번 | 메시지마다 LLM 호출 1회 (8.9회/에피소드) | `propose`에만 LLM 호출 1회 (6.1회/에피소드) | 0회 |
| 나타난 실패 | (해당 없음) | 네 행위 밖의 메시지(첫 턴 질문)를 reader가 `null`로 답함 1건. counter-offer는 모두 `propose`로 정규화돼서 `reject`가 한 번도 나오지 않음 | 가격 두 개가 들어간 `(propose)`에서 가격 reader가 `none` 8건. 가격을 담은 `(reject-proposal)` 41건 | 코드 블록 18/18 에피소드. 한 메시지에 `reject-proposal`과 `propose` 두 객체를 쓴 경우 7건(`Extra data`). 가격을 담은 `reject-proposal` 25건 → 잘못된 거래가로 인한 위반 2건 |

## 4. 해석

명시적 performative는 모든 곳에서 읽기 비용을 줄였습니다. reader 호출은 에피소드당 free 8.9회, tagged 6.1회, structured 0회입니다. 대신 형식 조건에서만 파싱 실패가 드러났습니다. tagged 8건, structured 7건이고 free는 1건입니다. 가장 큰 비용은 보낸 쪽이 행위를 직접 고르게 되면서 생겼습니다. 역할 프롬프트는 세 조건에 똑같이 "a counter-offer counts as a new price offer"라고 적었습니다. 그런데도 tagged와 structured의 Haiku는 역제안에 `reject-proposal`을 붙였습니다. tagged에서 41번, structured에서 25번입니다. 예를 들면 `logs/structured-3.txt:66`의 `{"performative": "reject-proposal", "content": {"price": 625}}`입니다. free에서는 같은 성격의 메시지를 reader가 모두 `propose`로 읽어서, `reject-proposal` 라벨이 한 번도 나오지 않았습니다. 이 불일치가 structured의 위반 2건을 만들었습니다. s2(reserve 620, budget 650)에서 seller는 거절 메시지에 625를 담았고 buyer가 수락했습니다. 하네스는 seller의 마지막 `propose`인 740으로 거래를 기록했습니다 (`logs/structured-3.txt:73`, `outcome=deal price=740 ... violation=1`). s3(reserve와 budget 모두 200)에서는 buyer의 거절 메시지에 담긴 200을 seller가 수락했습니다. 하네스는 buyer의 1턴 `propose` 120으로 기록했습니다 (`logs/structured-3.txt:108`, `:115`). 두 에이전트가 문장으로 합의한 가격은 한도 안이었습니다. 규칙대로 위반으로 집계했고, 원인은 에이전트가 거래를 잘못한 쪽보다 태그와 내용이 다른 말을 할 때 태그만 믿는 프로토콜 계층에 있습니다. FIPA가 content를 performative의 의미에 묶어 두는 이유가 이 지점입니다. 형식을 강제하자 새로운 실패도 생겼습니다. Haiku는 "no code fences"라는 지시에도 structured 18개 에피소드 전부에서 JSON을 코드 블록으로 감쌌습니다. structured의 파싱 실패 7건은 모두 한 메시지에 `reject-proposal`과 `propose` 두 JSON 객체를 이어 쓴 경우였습니다. FIPA라면 메시지 두 개로 보냈을 행위 두 개를 한 메시지에 넣은 것입니다. 처음 1건(`logs/structured-2.txt:42–50`)에는 두 객체 사이에 `Wait, let me reconsider - I should make a counter-offer, not just reject.`라는 문장이 있었습니다. 나머지 6건은 모두 `structured-2` s3의 2–7턴에서 나왔고, 양쪽이 이 두 객체 패턴을 번갈아 따라 했습니다 (`:81–128`). 이 에피소드는 파싱 실패 6건을 안고도 9턴째에 200으로 거래가 성사됐습니다 (`:137`). tagged의 가격 실패 8건은 모두 제 reader 프롬프트 때문입니다. `(propose) ... $450 is more than I'm looking to spend ... How about we meet somewhere in the middle at $375?`처럼 상대 가격을 인용한 메시지에서, "single price"라는 조건을 보고 `none`을 답했습니다 (`logs/tagged-1.txt:9–11`). README가 예상한 첫 턴 `refuse` 종료는 54개 에피소드에서 한 번도 나오지 않았습니다. free 조건의 Haiku buyer는 첫 메시지 18개 중 17개에서 가격을 제시했습니다. 질문으로 시작한 한 번(`logs/free-3.txt:30`, `What's the asking price?`)은 reader가 `refuse`를 고르지 않고 `{"performative": null}`에 "does not perform any of the four specified acts"라는 설명을 붙였습니다 (`:32–35`). 역할 프롬프트가 "on each message you do exactly one of four things"라고 요구해서 buyer가 질문을 피한 것으로 보입니다. 네 행위 어휘로 담을 수 없는 발화는 여전히 담기지 않았습니다. 형식이 바꾸지 못한 것도 있습니다. 거래가 불가능한 시나리오 s4–s6에서 거래는 한 번도 일어나지 않았습니다(27/27). 그곳의 결렬 9건은 모두 8–10턴째에 나왔습니다. 거래 가능한 시나리오의 거래가는 세 조건 모두 s1에서 327–390 범위였습니다.

## 부록 A. 모델 비교 (같은 시나리오, 프롬프트, 턴 한도, 반복 3회)

결과는 `extra/<model>/results.csv`, 로그는 `extra/<model>/logs/`에 있습니다. 세 모델 모두 4.5 세대이고, temperature는 설정할 수 없었습니다.

| model | condition | episodes | correct | violations | mean turns | format errors | reader calls | deal / no_deal / open |
|---|---|---|---|---|---|---|---|---|
| haiku-4-5 | free | 18 | 18/18 | 0 | 8.9 | 1 | 160 (8.9/ep) | 9 / 2 / 7 |
| haiku-4-5 | tagged | 18 | 18/18 | 0 | 9.0 | 8 | 109 (6.1/ep) | 9 / 3 / 6 |
| haiku-4-5 | structured | 18 | 15/18 | 2 | 9.2 | 7 | 0 (0.0/ep) | 8 / 4 / 6 |
| sonnet-4-5 | free | 18 | 16/18 | 0 | 9.4 | 0 | 169 (9.4/ep) | 7 / 9 / 2 |
| sonnet-4-5 | tagged | 18 | 16/18 | 0 | 9.6 | 0 | 144 (8.0/ep) | 7 / 5 / 6 |
| sonnet-4-5 | structured | 18 | 17/18 | 0 | 9.5 | 0 | 0 (0.0/ep) | 8 / 3 / 7 |
| opus-4-5 | free | 18 | 14/18 | 0 | 9.8 | 0 | 177 (9.8/ep) | 5 / 5 / 8 |
| opus-4-5 | tagged | 18 | 15/18 | 0 | 9.8 | 0 | 151 (8.4/ep) | 6 / 5 / 7 |
| opus-4-5 | structured | 18 | 14/18 | 0 | 9.9 | 0 | 0 (0.0/ep) | 5 / 5 / 8 |

- **형식 준수는 모델에 따라 크게 달랐습니다.** Sonnet과 Opus는 세 조건 모두 파싱 실패가 0건입니다. 코드 블록으로 감싼 structured 에피소드는 Haiku 18개, Sonnet 8개, Opus 0개입니다.
- **가격을 담은 reject는 tagged에서 모델과 관계없이 나왔습니다.** Haiku 41건, Sonnet 16건, Opus 14건입니다. structured에서 Sonnet과 Opus는 reject에 가격을 담지 않았고, 위반도 0건입니다. 같은 태그 어휘를 모델마다 다르게 썼습니다.
- **정답 수는 큰 모델일수록 줄었습니다.** 세 조건 합계로 Haiku 51, Sonnet 49, Opus 43입니다. Sonnet 오답 5건과 Opus 오답 11건은 모두 거래 가능한 시나리오에서 턴 한도(`open`)로 끝난 경우입니다. 대부분 s3(가격이 200 하나뿐)였고, Opus는 s2(구간 폭 30)에서도 2건이 나왔습니다. 평균 턴이 Opus 9.8–9.9로 가장 길어서, 조금씩 양보하는 전략에 10턴이 부족했던 것으로 보입니다.
- **reader 비용의 순서는 모델과 관계없이 free > tagged > structured(0)였습니다.**
