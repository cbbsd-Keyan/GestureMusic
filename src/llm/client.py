import json
import os
import random
import re
import time
import urllib.request
import urllib.error

API_KEY = os.environ.get(
    "LLM_API_KEY",
    "",
)

BASE_URL = os.environ.get(
    "LLM_BASE_URL",
    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
)

MODEL = os.environ.get(
    "LLM_MODEL",
    "glm-4-flash",
)

TIMEOUT_S = 90.0

RETRIES = 1


# =========================
# Prompt
# =========================

SYSTEM_PROMPT = """你是一个严格遵守乐理规则的作曲引擎。用户给你一段肢体动作的统计画像(JSON)，\
你把它谱写成纯器乐钢琴曲。只输出JSON，不要任何其他文字。

输出JSON结构（字段名不可改）：
{"bpm":整数, "key":"C"或"Am", "bars":8到16, \
"chords":[{"bar":小节号从0,"symbol":"和弦名"}], \
"melody":[{"bar":小节号,"note":MIDI音高,"start":小节内0到15,"dur":1到4,"velocity":30到110}], \
"title":"中文曲名", "description":"50字内，必须提到动作特征"}

乐理规则：
1. 音阶白名单：key="C"时 note 只能取自
   [48,50,52,53,55,57,59,60,62,64,65,67,69,71,72,74,76,79,81]；
   key="Am"时 note 只能取自 A和声小调（含升G=68/80）
   [57,59,60,62,64,65,68,69,71,72,74,76,77,80,81]。
   白名单之外的音一个都不能出现。Am 的升G要主动使用在
   接近E和弦的小节，形成小调终止感。
2. 强拍和弦音：start=0 或 start=8 的音符必须是当小节和弦的和弦音
3. 相邻旋律音不超过7个半音；每小节最多一次超过4半音的跳进
4. 每4小节一乐句，句末音落和弦音；全曲最后一个音落主音
   （key="C"用60/72/48，key="Am"用57/69）
5. bpm用画像tempo.bpm；null或confidence=low时用90
6. 曲名和description必须与画像数值一致（剧烈动作不得配舒缓文案）

反同质化与织体规则（与乐理同等优先）：
7. 第一个旋律音不得是主音；前四音不得构成主和弦分解
   （禁止do-mi-sol式开头）
8. 严格使用用户指定的和弦模板与调性，不得自行更换
9. 相邻乐句的旋律轮廓方向要有变化（升/降/拱形交替），
   不得通篇只用一种节奏型
10. 每小节旋律3~6个音；禁止出现连续超过8格（两拍）的
    旋律空白；相邻音符允许连绵或切分，不要弹一下空两拍"""


TEMPLATES = [
    "C-G-Am-F",
    "Am-Dm-E-Am",
    "C-Am-F-G",
    "Am-G-F-E",
]

# 调性必须跟随模板：下标奇数=Am模板(含E属和弦,需G#)
# 绝不允许独立轮换，否则产生白名单自相矛盾


def template_key(index):

    return "Am" if index % 2 == 1 else "C"


def build_user_prompt(profile, variation):

    idx = variation % len(TEMPLATES)

    template = TEMPLATES[idx]

    key = template_key(idx)

    return (
        "动作画像：\n"
        + json.dumps(
            profile,
            ensure_ascii=False,
        )
        + "\n\n本次指定：和弦模板 "
        + template
        + "；调性 "
        + key
        + "。\n请作曲，只输出JSON。"
    )


# =========================
# JSON 提取与修复
# =========================

def extract_json(text):

    """
    从模型回复中提取JSON对象。
    依次尝试: 剥markdown代码块 -> 正则抽最外层大括号。
    """

    t = text.strip()

    if t.startswith("```"):

        t = re.sub(
            r"^```[a-zA-Z]*\s*",
            "",
            t,
        )

        t = re.sub(
            r"\s*```$",
            "",
            t,
        )

    try:

        return json.loads(t)

    except json.JSONDecodeError:
        pass

    match = re.search(
        r"\{.*\}",
        t,
        re.DOTALL,
    )

    if match:

        return json.loads(match.group(0))

    raise ValueError("回复中找不到JSON")


# =========================
# 调用
# =========================

def call_llm(
    profile,
    variation=None,
    temperature=0.8,
    timeout=TIMEOUT_S,
    retries=RETRIES,
    api_key=None,
    base_url=None,
    model=None,
):

    """
    画像 -> 乐谱JSON。
    variation: 变奏种子，决定和弦模板与调性轮换；
    None时自动随机。
    返回 (score, meta)；失败抛 RuntimeError。
    """

    key = api_key or API_KEY
    url = base_url or BASE_URL
    model = model or MODEL

    if variation is None:
        variation = random.randrange(64)

    if not key:
        raise RuntimeError(
            "缺少API key: 设置环境变量 LLM_API_KEY"
        )

    last_error = None

    for attempt in range(retries + 1):

        t0 = time.perf_counter()

        # 部分厂商不支持response_format，
        # 首次失败后自动去掉重试
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": build_user_prompt(
                        profile,
                        variation,
                    ),
                },
            ],
            "temperature": temperature,
        }

        if attempt == 0:

            payload["response_format"] = {
                "type": "json_object"
            }

        body = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        }

        try:

            req = urllib.request.Request(
                url,
                data=body,
                headers=headers,
                method="POST",
            )

            with urllib.request.urlopen(
                req,
                timeout=timeout,
            ) as resp:

                data = json.loads(
                    resp.read().decode("utf-8")
                )

            content = data["choices"][0][
                "message"
            ]["content"]

            score = extract_json(content)

            latency = time.perf_counter() - t0

            return score, {
                "latency_s": round(latency, 2),
                "attempts": attempt + 1,
                "model": model,
            }

        except urllib.error.HTTPError as e:

            last_error = f"http:{e.code}"

        except urllib.error.URLError as e:

            reason = getattr(
                e,
                "reason",
                "",
            )

            last_error = (
                "timeout"
                if "timed out" in str(reason)
                else f"network:{reason}"
            )

        except (KeyError, ValueError) as e:

            last_error = f"bad_response:{e}"

        except json.JSONDecodeError as e:

            last_error = f"bad_json:{e}"

    raise RuntimeError(
        f"LLM调用失败: {last_error}"
    )
