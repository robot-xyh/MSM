"""Record main-owned provenance checks without executing research modules."""

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PRIOR = ROOT / "deliverables/project_audits/goal_resume_audit_20260926_v1"


def command(*args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=30)
    return {"args": list(args), "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}


def save(name, value):
    with (OUT / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    if (OUT / "MAIN_REVIEW.json").exists():
        raise SystemExit("Main review already recorded.")
    register = PRIOR / "GOAL_REQUIREMENT_EVIDENCE.csv"
    with register.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    root_docs = [
        "research_modules/scalable_3d_simulation/docs/SCALABLE_3D_GOAL_COMPLETION_AUDIT_20260803_CN.md",
        "research_modules/scalable_3d_simulation/docs/SCALABLE_3D_GOAL_PROGRESS_AND_NEXT_PLAN_20260807_CN.md",
        "deliverables/project_audits/goal_resume_audit_20260926_v1/原Goal逐项状态对照_CN.md",
        "deliverables/project_audits/goal_resume_audit_20260926_v1/STATIC_IMPORT_EVIDENCE.json",
    ]
    note = {
        "G01": "原专项分支仍为当前提交祖先，主控目录存在；完成只指分支和目录建立。",
        "G02": "模块目录分工及原规则框架保留；不据目录结构认证全部历史分工过程。",
        "G03": "原Goal文档明确为质点科研仿真；与后续独立AirSim接口或实机用途分别登记。",
        "G09": "保持历史软件合同范围内已完成判断。原主模块未变，本轮没有重跑坐标或动力学测试。",
        "G34": "十个正式分片的摘要与预期哈希可查，完整载荷仍未定位；后半450组无完成证据。",
        "G49": "522项是原日期的历史测试摘要，本轮没有执行新的接口回归或主线测试。",
        "G55": "原进展汇总已保存，但模块旧章节有历史时点未衔接，不能泛称所有文档已经一致。",
        "G56": "只确认已有按模块提交及文档记录；本轮没有逐条审查过去所有会话的分工纪律。",
        "G57": "版本合同存在。D2指出的哈希对象标签错配已由main重新计算小文件哈希确认；不恢复缺失载荷。",
        "G58": "本轮git tag --list仍为空；没有补建验收标签。",
        "G59": "历史权重指纹不等于当前长期制品可定位或远端LFS可用；未开展远端查证。",
        "G60": "现存进展文档明确总体未完成，独立报告和本次文字勘误不构成统一验收证据。",
    }
    reviews = []
    for row in rows:
        if "main" not in row["owner"]:
            continue
        reviews.append({
            "requirement_id": row["requirement_id"], "original_status": row["status"],
            "review_result": "限定认可", "suggested_status": row["status"],
            "evidence": root_docs,
            "reason": note.get(row["requirement_id"],
                "对照原审计、8月7日进展及本轮版本核对，保留主级登记；" + row["outstanding"] + "。本轮不替模块所有者认证算法。"),
            "remaining_evidence": row["outstanding"],
        })
    hashes = {}
    for relative in root_docs + [str(register.relative_to(ROOT))]:
        hashes[relative] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    folder = ROOT / "research_modules/d2_data_association/docs/formal_r0_identity_causal_pack_summary_20260731"
    hash_objects = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                    for name in ("ARTIFACT_SHA256SUMS", "artifact_inventory.json")}
    original = "98fd3978a6a6e9a0d1bc5ab341c5db8a77624214"
    checks = {
        "head": command("git", "rev-parse", "HEAD"),
        "original_ancestor": command("git", "merge-base", "--is-ancestor", original, "HEAD"),
        "unchanged_original_scopes": command("git", "diff", "--name-only", original, "HEAD", "--",
            "research_modules/scalable_3d_simulation", "research_modules/d1_sensor_fusion",
            "research_modules/d2_data_association", "research_modules/d3_assignment_planner",
            "research_modules/d4_distributed_fallback", "research_modules/d7_proportional_guidance"),
        "tags": command("git", "tag", "--list"),
        "module_worktree_changes": command("git", "diff", "--name-only", "--", "research_modules", "subagent_reviews"),
    }
    save("MAIN_REVIEW.json", {
        "module": "main", "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "scope": "主级既有材料和版本证据复核，不重新执行模块算法，不代替模块所有者技术认证。",
        "requirements": reviews, "source_hashes": hashes, "git_checks": checks,
        "d2_hash_objects": hash_objects,
        "documentation_checked": [{"path": p, "reason": "引用历史结论，不修改历史报告。"} for p in root_docs],
    })
    print(json.dumps({"main_requirements": len(reviews), "d2_hash_objects": hash_objects}, ensure_ascii=False))


if __name__ == "__main__":
    main()
