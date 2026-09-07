import argparse
import json
import random
import sys
from pathlib import Path

from score_player import load_score, play_score


def main():

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "files",
        nargs="+",
        help="乐谱JSON文件或目录",
    )

    parser.add_argument(
        "--device",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--key-out",
        default="reports/blind_key.json",
        help="匿名对照表输出路径(打分结束后才能看)",
    )

    args = parser.parse_args()

    paths = []

    for p in args.files:

        path = Path(p)

        if path.is_dir():

            paths.extend(
                sorted(path.glob("*.json"))
            )

        else:

            paths.append(path)

    paths = [
        p for p in paths
        if "summary" not in p.name
    ]

    if not paths:
        print("没有找到乐谱文件。")
        return

    order = list(range(len(paths)))

    random.shuffle(order)

    mapping = {}

    print("===== 盲听模式 =====")
    print("每首播完再回车播下一首。")
    print("打分表模板已生成，填 S 编号即可。")
    print("对照表在全部听完前不要打开！")
    print()

    template_path = Path("reports/blind_sheet.csv")

    with open(
        template_path,
        "w",
        encoding="utf-8",
    ) as f:

        f.write("编号,合格,旋律感,跑调,节奏,重复,情绪,可演示,备注\n")

        for i in range(len(paths)):

            f.write(f"S{i+1:02d},,,,,,,,\n")

    print(f"[打分表] {template_path}")
    print()

    try:

        for i, idx in enumerate(order):

            code = f"S{i+1:02d}"

            mapping[code] = paths[idx].name

            input(f"{code} 准备好了按回车播放...")

            score = load_score(paths[idx])

            play_score(score, args.device)

    except KeyboardInterrupt:

        print("\n中断。已听的编号已记录。")

    with open(
        args.key_out,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            mapping,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\n[对照表] {args.key_out} (打分结束后再打开)")


if __name__ == "__main__":

    main()
