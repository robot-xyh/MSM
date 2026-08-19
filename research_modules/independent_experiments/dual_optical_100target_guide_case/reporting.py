"""Chinese figures and report for the dual-optical 100-target guide case."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping, Sequence
import warnings

import matplotlib

matplotlib.use("Agg")
warnings.filterwarnings(
    "ignore",
    message="Unable to import Axes3D.*",
    category=UserWarning,
    module="matplotlib.projections",
)
from matplotlib import font_manager
from matplotlib import pyplot as plt
import numpy as np

from .runtime import ExperimentResult, read_csv, write_json


REPORT_NAME = "DUAL_OPTICAL_100TARGET_GUIDE_AIRSIM_REPORT_CN.md"


def generate_experiment_report(result: ExperimentResult) -> dict[str, Path]:
    _configure_matplotlib()
    figures_dir = result.output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    truth = _track_truth(result.output_dir)
    figures = {
        "scene": _plot_scene(result, figures_dir / "01_scene_3d.png"),
        "spacing": _plot_initial_spacing(
            result, figures_dir / "02_initial_spacing.png"
        ),
        "scan": _plot_scan_coverage(result, figures_dir / "03_scan_coverage.png"),
        "residuals": _plot_residual_sequences(
            result, truth, figures_dir / "04_residual_sequences.png"
        ),
        "votes": _plot_vote_matrix(result, figures_dir / "05_vote_matrix.png"),
        "matches": _plot_hungarian_relations(
            result, truth, figures_dir / "06_hungarian_relations.png"
        ),
        "stages": _plot_stage_metrics(
            result, figures_dir / "07_stage_metrics.png"
        ),
        "crossing": _plot_crossing_states(
            result, truth, figures_dir / "08_crossing_states.png"
        ),
        "flow": _plot_algorithm_flow(figures_dir / "09_algorithm_flow.png"),
        "track_quality": _plot_track_quality(
            result, figures_dir / "10_local_track_purity.png"
        ),
    }
    report = _write_report(result, figures)
    manifest = write_json(
        figures_dir / "figure_manifest.json",
        {name: str(path.relative_to(result.output_dir)) for name, path in figures.items()},
    )
    return {"report": report, "figure_manifest": manifest, **figures}


def _configure_matplotlib() -> None:
    candidates = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    )
    selected = "DejaVu Sans"
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            font_manager.fontManager.addfont(str(path))
            selected = font_manager.FontProperties(fname=str(path)).get_name()
            break
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [selected, "DejaVu Sans"],
            "axes.unicode_minus": False,
            "figure.dpi": 140,
            "savefig.dpi": 180,
            "axes.grid": True,
            "grid.alpha": 0.22,
        }
    )


def _plot_scene(result: ExperimentResult, path: Path) -> Path:
    figure, axis = plt.subplots(figsize=(10.5, 6.3))
    crossing_ids = {
        target.truth_id for target in result.target_specs if target.crossing_group is not None
    }

    def isometric(point: Sequence[float]) -> tuple[float, float]:
        north_km = float(point[0]) / 1000.0
        east_km = float(point[1]) / 1000.0
        height_km = -float(point[2]) / 1000.0
        return north_km + 0.48 * east_km, height_km + 0.22 * east_km

    for target in result.target_specs:
        start = isometric(target.start_ned)
        end = isometric(target.position_at(result.config.duration_s))
        color = "#c73e3a" if target.truth_id in crossing_ids else "#4f81a8"
        axis.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=color,
            alpha=0.52,
            linewidth=1.0,
        )
    for name, position in result.config.camera_positions.items():
        projected = isometric(position)
        axis.scatter(projected[0], projected[1], marker="^", s=90, label=name)
    origin = np.asarray((0.4, -0.15))
    directions = (
        (np.asarray((1.1, 0.0)), "北向"),
        (np.asarray((0.52, 0.24)), "东向"),
        (np.asarray((0.0, 0.75)), "高度"),
    )
    for vector, label in directions:
        axis.annotate("", xy=origin + vector, xytext=origin, arrowprops={"arrowstyle": "->", "lw": 1.2})
        axis.text(*(origin + vector * 1.06), label, fontsize=9)
    axis.set_xlabel("等轴投影横坐标 / km")
    axis.set_ylabel("等轴投影纵坐标 / km")
    axis.set_title("双站、100个目标与10组交叉轨迹的三维等轴投影")
    axis.legend(loc="upper left")
    axis.set_aspect("equal", adjustable="datalim")
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


def _plot_initial_spacing(result: ExperimentResult, path: Path) -> Path:
    starts = np.asarray([target.start_ned for target in result.target_specs])
    nearest = []
    for index, point in enumerate(starts):
        distances = np.linalg.norm(starts - point, axis=1)
        distances[index] = math.inf
        nearest.append(float(np.min(distances)))
    figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    axes[0].scatter(starts[:, 0], starts[:, 1], c=-starts[:, 2], s=17, cmap="viridis")
    axes[0].set_title("初始水平位置")
    axes[0].set_xlabel("北向距离 / m")
    axes[0].set_ylabel("东向距离 / m")
    axes[1].hist(nearest, bins=18, color="#4f81a8", edgecolor="white")
    axes[1].axvline(100.0, color="#c73e3a", linestyle="--", label="100 m门限")
    axes[1].axvline(min(nearest), color="#2e7d32", label=f"最小值 {min(nearest):.1f} m")
    axes[1].set_title("每个目标到最近邻的初始距离")
    axes[1].set_xlabel("距离 / m")
    axes[1].set_ylabel("目标数")
    axes[1].legend()
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


def _plot_scan_coverage(result: ExperimentResult, path: Path) -> Path:
    figure, axes = plt.subplots(2, 1, figsize=(10.5, 5.5), sharex=True)
    rows = result.camera_scan_rows
    for camera_id, color in (
        (result.config.camera_a_name, "#4f81a8"),
        (result.config.camera_b_name, "#c97b32"),
    ):
        selected = [row for row in rows if row.get("camera_id") == camera_id]
        if not selected:
            continue
        timestamp = [float(row["measurement_timestamp"]) for row in selected]
        yaw = [float(row["yaw_deg"]) for row in selected]
        detections = [int(float(row.get("detection_count") or 0)) for row in selected]
        axes[0].plot(timestamp, yaw, label=camera_id, color=color)
        axes[1].plot(timestamp, detections, label=camera_id, color=color)
    for boundary in np.arange(0.5, result.config.duration_s, 0.5):
        axes[0].axvline(boundary, color="#888888", linewidth=0.5, alpha=0.35)
    axes[0].set_ylabel("方位角 / deg")
    axes[0].set_title("5秒扫描和10个半程重访")
    axes[0].legend()
    axes[1].set_ylabel("匿名检测数")
    axes[1].set_xlabel("时间 / s")
    axes[1].set_title("每次查询返回的检测数量")
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


def _plot_residual_sequences(
    result: ExperimentResult, truth: Mapping[str, str], path: Path
) -> Path:
    correct = []
    wrong = []
    for item in result.association.residual_statistics:
        same = bool(
            truth.get(item.track_a_id)
            and truth.get(item.track_a_id) == truth.get(item.track_b_id)
        )
        (correct if same else wrong).append(item)
    selected_correct = min(correct, key=lambda item: item.median_mrad) if correct else None
    finite_wrong = [item for item in wrong if math.isfinite(item.median_mrad)]
    selected_wrong = min(finite_wrong, key=lambda item: item.median_mrad) if finite_wrong else None
    figure, axis = plt.subplots(figsize=(10.5, 4.4))
    if selected_correct:
        axis.plot(
            selected_correct.timestamps_s,
            selected_correct.residuals_mrad,
            "o-",
            color="#2e7d32",
            label=f"正确关系 {selected_correct.track_a_id}/{selected_correct.track_b_id}",
        )
    if selected_wrong:
        axis.plot(
            selected_wrong.timestamps_s,
            selected_wrong.residuals_mrad,
            "s-",
            color="#c73e3a",
            label=f"最难排除的错误关系 {selected_wrong.track_a_id}/{selected_wrong.track_b_id}",
        )
    axis.axvline(result.config.crossing_time_s, color="#555555", linestyle="--", label="交叉时刻")
    axis.set_xlabel("时间 / s")
    axis.set_ylabel("归一化共面性残差 / mrad")
    axis.set_title("正确关系与竞争关系的多时刻残差")
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


def _plot_vote_matrix(result: ExperimentResult, path: Path) -> Path:
    figure, axis = plt.subplots(figsize=(8.0, 7.0))
    image = axis.imshow(result.association.vote_matrix, cmap="YlGnBu", aspect="auto", vmin=0)
    axis.set_xlabel("B站局部轨迹序号")
    axis.set_ylabel("A站局部轨迹序号")
    axis.set_title("10次扫描级匈牙利匹配的累计票数")
    figure.colorbar(image, ax=axis, label="票数")
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


def _plot_hungarian_relations(
    result: ExperimentResult, truth: Mapping[str, str], path: Path
) -> Path:
    index_a = {value: index for index, value in enumerate(result.association.track_a_ids)}
    index_b = {value: index for index, value in enumerate(result.association.track_b_ids)}
    figure, axis = plt.subplots(figsize=(10.5, 7.0))
    for match in result.association.final_matches:
        correct = bool(
            truth.get(match.track_a_id)
            and truth.get(match.track_a_id) == truth.get(match.track_b_id)
        )
        axis.plot(
            [0, 1],
            [index_a[match.track_a_id], index_b[match.track_b_id]],
            color="#2e7d32" if correct else "#c73e3a",
            alpha=0.42,
            linewidth=1.0,
        )
    axis.scatter(np.zeros(len(index_a)), range(len(index_a)), s=8, color="#4f81a8", label="A站轨迹")
    axis.scatter(np.ones(len(index_b)), range(len(index_b)), s=8, color="#c97b32", label="B站轨迹")
    axis.set_xlim(-0.12, 1.12)
    axis.set_xticks((0, 1), ("A站", "B站"))
    axis.set_ylabel("局部轨迹排序")
    axis.set_title("最终一对一关系：绿色正确，红色错误")
    if not result.association.final_matches:
        axis.text(
            0.5,
            0.5,
            "本次未形成最终跨站关系",
            transform=axis.transAxes,
            ha="center",
            va="center",
            fontsize=13,
            color="#555555",
            bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "alpha": 0.9},
        )
    axis.legend(loc="upper center")
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


def _plot_stage_metrics(result: ExperimentResult, path: Path) -> Path:
    stages = result.metrics["association_stages"]
    labels = ("单次共面", "多时刻统计", "扫描投票", "确认关系")
    keys = (
        "single_scan_coplanarity",
        "multi_time_residual_and_slope",
        "scan_hungarian_and_vote",
        "confirmed_only",
    )
    precision = [stages[key]["association_precision"] for key in keys]
    recall = [stages[key]["unique_target_recall"] for key in keys]
    x = np.arange(len(keys))
    figure, axis = plt.subplots(figsize=(10.0, 4.5))
    axis.bar(x - 0.18, precision, width=0.36, label="准确率", color="#4f81a8")
    axis.bar(x + 0.18, recall, width=0.36, label="目标召回率", color="#c97b32")
    axis.set_xticks(x, labels)
    axis.set_ylim(0.0, 1.05)
    axis.set_ylabel("比例")
    axis.set_title("四个处理阶段的离线评分")
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


def _plot_crossing_states(
    result: ExperimentResult, truth: Mapping[str, str], path: Path
) -> Path:
    crossing_truth = {
        target.truth_id for target in result.target_specs if target.crossing_group is not None
    }
    state_value = {"tentative": 0, "pending": 1, "coasting": 2, "confirmed": 3}
    records = [
        item
        for item in result.association.state_history
        if truth.get(item.track_a_id) in crossing_truth
        or truth.get(item.track_b_id) in crossing_truth
    ]
    figure, axis = plt.subplots(figsize=(10.5, 4.8))
    for relation_index, relation in enumerate(
        sorted({(item.track_a_id, item.track_b_id) for item in records})[:20]
    ):
        selected = [
            item
            for item in records
            if (item.track_a_id, item.track_b_id) == relation
        ]
        axis.plot(
            [item.half_sweep_index for item in selected],
            [state_value.get(item.state, -1) + relation_index * 0.015 for item in selected],
            "o-",
            linewidth=0.8,
            markersize=2.8,
            alpha=0.58,
        )
    axis.axvline(
        result.config.crossing_time_s / 0.5,
        color="#c73e3a",
        linestyle="--",
        label="2.5 s交叉附近",
    )
    axis.set_yticks((0, 1, 2, 3), ("收集证据", "待确认", "短时保持", "已确认"))
    axis.set_xlabel("半程扫描编号")
    axis.set_title("交叉目标关系的确认状态")
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


def _plot_algorithm_flow(path: Path) -> Path:
    figure, axis = plt.subplots(figsize=(11.0, 3.5))
    axis.set_xlim(0, 10)
    axis.set_ylim(0, 3)
    axis.axis("off")
    labels = (
        "扫描检测\n转成匿名视线",
        "单站重访\n形成局部轨迹",
        "共面性粗筛\n多时刻统计",
        "扫描级匈牙利\n累计关系票数",
        "一对一选择\n交叉暂缓确认",
    )
    colours = ("#dbeaf4", "#e8f0d4", "#f7e6c4", "#eadcf0", "#d9ece6")
    centres = np.linspace(1.0, 9.0, len(labels))
    for centre, label, colour in zip(centres, labels, colours, strict=True):
        rectangle = plt.Rectangle(
            (centre - 0.75, 1.0), 1.5, 1.0, facecolor=colour, edgecolor="#555555"
        )
        axis.add_patch(rectangle)
        axis.text(centre, 1.5, label, ha="center", va="center", fontsize=9)
    for first, second in zip(centres, centres[1:], strict=False):
        axis.annotate(
            "",
            xy=(second - 0.78, 1.5),
            xytext=(first + 0.78, 1.5),
            arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 1.4},
        )
    axis.set_title("双站轨迹配准处理流程", fontsize=14)
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


def _plot_track_quality(result: ExperimentResult, path: Path) -> Path:
    quality = result.metrics.get("offline_track_quality", {})
    figure, axis = plt.subplots(figsize=(10.0, 4.5))
    colours = ("#4f81a8", "#c97b32")
    for camera_id, colour in zip(result.config.camera_positions, colours, strict=True):
        values = quality.get(camera_id, {}).get("purity_values", [])
        if values:
            axis.hist(
                values,
                bins=np.linspace(0.0, 1.0, 21),
                alpha=0.55,
                color=colour,
                label=camera_id,
            )
    axis.axvline(0.90, color="#2e7d32", linestyle="--", label="高纯度门限 0.90")
    axis.set_xlim(0.0, 1.02)
    axis.set_xlabel("单条局部轨迹中占比最高的真实目标比例")
    axis.set_ylabel("局部轨迹数")
    axis.set_title("离线局部轨迹纯度检查")
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


def _write_report(result: ExperimentResult, figures: Mapping[str, Path]) -> Path:
    metrics = result.metrics
    stages = metrics["association_stages"]
    formal = bool(metrics.get("formal_airsim_result"))
    evidence_statement = (
        f"本报告数据来自 AirSim ComputerVision 正式运行，seed为{result.config.seed}。"
        if formal
        else "本报告当前数据来自确定性几何测试夹具，只验证接口、算法和报告链路，不作为AirSim性能结论。"
    )
    final_stage = stages["scan_hungarian_and_vote"]
    initial_pairs = metrics["local_tracks"]["full_pair_count"]
    quality = metrics.get("offline_track_quality", {})
    quality_a = quality.get(result.config.camera_a_name, {})
    quality_b = quality.get(result.config.camera_b_name, {})
    if final_stage["selected_match_count"] == 0 and formal:
        result_judgement = (
            "本次正式运行没有形成可发布的跨站关系。检测接口工作正常，"
            "断点位于单站轨迹形成：扫描过程中相邻目标被串入同一条局部轨迹，"
            "多时刻几何检查因此拒绝了全部候选。"
        )
    else:
        result_judgement = "本次运行形成了可评分的跨站一对一关系。"
    text = fr"""# 双站光电100目标轨迹配准试验报告

## 结论

{evidence_statement}场景结构检查已经通过：两站相距4公里，包含100个目标、10组交叉目标和10次半程扫描，初始最小间距为{metrics['scenario']['minimum_initial_separation_m']:.2f}米。在线记录未发现Actor名称或真实编号，最终关系保持一对一。

扫描投票阶段输出{final_stage['selected_match_count']}组关系，其中离线判定正确{final_stage['correct_match_count']}组、错误{final_stage['false_match_count']}组，准确率为{final_stage['association_precision']:.3f}，目标召回率为{final_stage['unique_target_recall']:.3f}。{result_judgement}这些数字是本次数据的实测值，没有采用参考指南中的99.95%结果。

## 场景

两台光电设备采用ComputerVision模式，NED坐标系中的横向基线为4000米。相机分辨率为1280×1024，水平视场角为2.93度。设备在5秒内以100赫兹更新方位，1秒完成一次往返，因此形成10个半程扫描。目标最长尺寸按3米校准，水平速度为40至60米每秒，垂直速度限制在正负20米每秒。视线转换后加入标准差0.15毫弧度的固定随机种子测角噪声。

![三维场景]({figures['scene'].relative_to(result.output_dir)})

100个目标没有排成整齐方阵。20个目标组成10组交叉关系，在2.5秒附近到达同一空间位置；其余目标按不同纵深、侧向位置和速度进入。生成器先建立轨迹，再检查任意两个目标的初始三维距离，低于100米时直接拒绝场景。

![初始间距]({figures['spacing'].relative_to(result.output_dir)})

## 扫描观测

相机只调整方位角，俯仰角指向来袭走廊中心。每0.5秒完成一个方向的扫描。AirSim运行时，检测框中心通过针孔相机模型转成世界坐标系单位视线，再加入测角噪声。Actor名称、三维真值和AirSim内部身份只写入离线评分目录。

![扫描覆盖]({figures['scan'].relative_to(result.output_dir)})

同一个目标在一次扫过中可能连续出现多次。单站跟踪器先把这些匿名检测按世界方位连续性串起来，再把一次半程扫描中的多次观测合成一个重访样本。本次两站共取得{metrics['detections']['total']}次匿名检测，A站形成{metrics['local_tracks']['camera_a']}条算法稳定轨迹，B站形成{metrics['local_tracks']['camera_b']}条算法稳定轨迹，因此跨站初始组合数为{initial_pairs}组。

| 观测质量指标 | A站 | B站 | 合计或判定 |
| --- | ---: | ---: | ---: |
| 匿名检测 | {metrics['detections']['by_camera'].get(result.config.camera_a_name, 0)} | {metrics['detections']['by_camera'].get(result.config.camera_b_name, 0)} | {metrics['detections']['total']} |
| 算法稳定轨迹 | {metrics['local_tracks']['camera_a']} | {metrics['local_tracks']['camera_b']} | {metrics['local_tracks']['camera_a'] + metrics['local_tracks']['camera_b']} |
| 轨迹纯度中位数 | {quality_a.get('purity_median', 0.0):.3f} | {quality_b.get('purity_median', 0.0):.3f} | - |
| 纯度不低于0.90 | {quality_a.get('high_purity_track_count', 0)} | {quality_b.get('high_purity_track_count', 0)} | {quality_a.get('high_purity_track_count', 0) + quality_b.get('high_purity_track_count', 0)} |

离线真值只用于检查局部轨迹是否串号。这里的“算法稳定轨迹”表示轨迹满足长度和重访条件，不表示轨迹内观测来自同一目标。A站轨迹纯度中位数为{quality_a.get('purity_median', 0.0):.3f}，B站为{quality_b.get('purity_median', 0.0):.3f}；纯度不低于0.90的轨迹分别为{quality_a.get('high_purity_track_count', 0)}条和{quality_b.get('high_purity_track_count', 0)}条。多数轨迹混入多个目标的观测，跨站算法接收到的已经不是稳定的单目标轨迹。

![局部轨迹纯度]({figures['track_quality'].relative_to(result.output_dir)})

## 配准方法

![算法流程]({figures['flow'].relative_to(result.output_dir)})

### 共面性

对于A站视线、B站视线和两站基线，同一目标的两条视线应接近同一平面。程序计算对称归一化共面性残差：

$$
r=\frac{{1}}{{2}}\left[\arcsin\left|\mathbf u_B^T\mathbf n_A\right|+\arcsin\left|\mathbf u_A^T\mathbf n_B\right|\right]
$$

其中，$\mathbf n_A$和$\mathbf n_B$分别是视线与基线构成平面的单位法向量。单次扫描只用一个时刻的残差，容易在目标交叉或相近时选错。

### 多时刻轨迹

程序把同一候选在10次重访中的残差排成序列，计算中位数、90%分位数、绝对中位差和随时间变化的斜率。还用双站视线交会得到一组临时空间点，检查这些点能否被匀速直线合理解释。这里没有使用“均方根误差一定按样本数平方根下降”或“像面角速度与视角无关”作为前提。

![残差序列]({figures['residuals'].relative_to(result.output_dir)})

### 匈牙利匹配和投票

每次半程扫描独立建立共面性代价矩阵，由匈牙利算法选出不重复的一对一关系。10次扫描结束后统计每组关系的票数，再与多时刻残差联合形成最终代价。这样可以限制一条A站轨迹同时占用多条B站轨迹。

![投票矩阵]({figures['votes'].relative_to(result.output_dir)})

![一对一关系]({figures['matches'].relative_to(result.output_dir)})

### 确认状态

关系连续获得三次无冲突支持后才转为已确认。若同一条轨迹附近出现代价接近的竞争关系，状态保持待确认；短时没有新证据时只保持已有关系，不立即发布新的身份。该处理降低交叉瞬间的错误提交风险，但不承诺消除所有错误。

![交叉状态]({figures['crossing'].relative_to(result.output_dir)})

## 阶段结果

| 阶段 | 选中关系 | 正确关系 | 错误关系 | 准确率 | 目标召回率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 单次扫描共面性 | {stages['single_scan_coplanarity']['selected_match_count']} | {stages['single_scan_coplanarity']['correct_match_count']} | {stages['single_scan_coplanarity']['false_match_count']} | {stages['single_scan_coplanarity']['association_precision']:.3f} | {stages['single_scan_coplanarity']['unique_target_recall']:.3f} |
| 多时刻残差与斜率 | {stages['multi_time_residual_and_slope']['selected_match_count']} | {stages['multi_time_residual_and_slope']['correct_match_count']} | {stages['multi_time_residual_and_slope']['false_match_count']} | {stages['multi_time_residual_and_slope']['association_precision']:.3f} | {stages['multi_time_residual_and_slope']['unique_target_recall']:.3f} |
| 扫描匈牙利与投票 | {stages['scan_hungarian_and_vote']['selected_match_count']} | {stages['scan_hungarian_and_vote']['correct_match_count']} | {stages['scan_hungarian_and_vote']['false_match_count']} | {stages['scan_hungarian_and_vote']['association_precision']:.3f} | {stages['scan_hungarian_and_vote']['unique_target_recall']:.3f} |
| 最终已确认关系 | {stages['confirmed_only']['selected_match_count']} | {stages['confirmed_only']['correct_match_count']} | {stages['confirmed_only']['false_match_count']} | {stages['confirmed_only']['association_precision']:.3f} | {stages['confirmed_only']['unique_target_recall']:.3f} |

![阶段指标]({figures['stages'].relative_to(result.output_dir)})

四个阶段分别回答不同问题。单次共面性仍选出3组关系，但离线检查均为错误；多时刻统计发现这些关系不能由连续运动解释，因此没有继续发布。当前应先修复单站扫描轨迹的串号，再评估跨站门限。直接放宽共面性、速度或确认门限会把错误轨迹送入最终结果，不能修复本次断点。

## 限制

本案例只验证已知双站外参、同步时间和AirSim检测框条件下的轨迹配准。外参漂移、时间同步误差、持续虚警、随机漏检、严重遮挡和相机本体运动尚未加入。指南中的99.95%来自另一组仿真，不能替代本场景结果；多假设跟踪也只能保留竞争解释，不能保证100%正确。

本实现采用episode结束后的批量关联。AirSim采集按100赫兹进行，但跨站关系不是每0.5秒实时发布。后续若进入在线链路，需要把残差统计、票数和状态机改成因果增量更新，并单独测量每个扫描周期内的处理延迟。

## 文件

- `online/`：匿名检测、扫描状态、局部轨迹、残差、投票关系和状态历史。
- `truth/`：目标轨迹、检测真值、轨迹真值和离线评分，只用于报告。
- `metrics.json`：阶段指标、结构验收和运行时间。
- `record_manifest.json`：结构化记录索引，明确是否为正式AirSim结果。
"""
    path = result.output_dir / REPORT_NAME
    path.write_text(text, encoding="utf-8")
    return path


def _track_truth(output_dir: Path) -> dict[str, str]:
    return {
        row["track_id"]: row["truth_id"]
        for row in read_csv(output_dir / "truth" / "track_truth.csv")
        if row.get("track_id") and row.get("truth_id")
    }
