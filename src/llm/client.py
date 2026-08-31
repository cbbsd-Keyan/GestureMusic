import json
import re
import time
import urllib.request
import urllib.error


# =========================
# 配置（环境变量可覆盖）
# =========================

import os

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

TIMEOUT_S = 15.0

RETRIES = 1


# =========================
# Prompt
# =========================

SYSTEM_PROMPT = """你是一个作曲引擎。用户给你一段肢体动作的统计画像(JSON)，\
你把它谱写成一段纯器乐钢琴曲，输出严格符合以下JSON结构：

{"bpm":整数, "key":"C", "bars":8到24的整数, \
"chords":[{"bar":小节号从0,"symbol":"和弦名如 Am"}], \
"melody":[{"bar":小节号,"note":MIDI音高36到84,"start":小节内位置0到15,\
"dur":时值1到4,"velocity":30到110}], \
"title":"曲名(中文)", "description":"50字内的乐曲解读，要提到动作特征"}

硬性规则：
1. 时值单位是十六分音符，每小节16格，start+dur不得超过16
2. note必须在36到84之间，优先使用和弦内音
3. bpm优先采用画像tempo.bpm；若为null用90
4. energy高的画像：音符密(每小节6-10个)、力度大、多用强进行；\
energy低：音符疏(每小节2-4个)、力度轻
5. 只输出JSON，不要任何其他文字"""


def build_user_prompt(profile):

    return (
        "动作画像：\n"
        + json.dumps(
            profile,
            ensure_ascii=False,
        )
        + "\n\n请作曲，只输出JSON。"
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
    timeout=TIMEOUT_S,
    retries=RETRIES,
    api_key=None,
    base_url=None,
    model=None,
):

    """
    画像 -> 乐谱JSON。
    返回 (score, meta)；失败抛 RuntimeError，
    meta.error 标明错误类别。
    """

    key = api_key or API_KEY
    url = base_url or BASE_URL
    model = model or MODEL

    if not key:
        raise RuntimeError(
            "缺少API key: 设置环境变量 LLM_API_KEY"
        )

    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": build_user_prompt(
                        profile
                    ),
                },
            ],
            "temperature": 0.8,
            "response_format": {
                "type": "json_object"
            },
        }
    ).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }

    last_error = None

    for attempt in range(retries + 1):

        t0 = time.perf_counter()

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
