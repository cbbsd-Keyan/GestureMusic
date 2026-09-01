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

TIMEOUT_S = 60.0

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

作曲规则（全部必须遵守）：
1. 音阶白名单：key="C"时 note 只能取自
   [48,50,52,53,55,57,59,60,62,64,65,67,69,71,72,74,76,79,81]；
   key="Am"时 note 只能取自
   [45,47,48,50,52,53,55,57,59,60,62,64,65,67,69,71,72,74,76,77,79,81]。
   白名单之外的音一个都不能出现。
2. 和弦进行从以下模板选一套，按小节循环填写 chords：
   [C,G,Am,F] / [Am,F,C,G] / [C,Am,F,G] / [F,G,Em,Am]
3. 强拍和弦音：start=0 或 start=8 的音符必须是当小节和弦的和弦音
   （C=[60,64,67]类推，可低/高八度）
4. 禁止大跳：相邻两个旋律音相差不超过7个半音；
   每小节最多允许一次超过4个半音的跳进，其余用级进
5. 收束：每4小节乐句的末音用和弦音；全曲最后一个音必须落主音
   （key="C"用60/72/48，key="Am"用57/69）
6. 乐句结构：以4小节为一乐句，后一乐句的节奏型是前一乐句的
   重复或微变，不要每小节都换节奏
7. 画像映射：bpm用画像tempo.bpm（null或confidence=low时用90）；
   energy高的画像每小节6~10个音、力度70~110；
   energy低每小节2~4个音、力度45~75
8. 曲名和description必须与画像数值一致（剧烈动作不得配舒缓文案）"""


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
                        profile
                    ),
                },
            ],
            "temperature": 0.8,
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
