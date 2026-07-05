# Main Directive: N-Drone Simulation Parameterization

## 总体要求

main agent 统一持有仿真规模参数 `N`。每次 AirSim 或质点仿真启动时，只通过 main 的 CLI 或场景配置设置 `N`，由 main 生成：

- `resource_vehicle_names`
- `camera_vehicle_names`
- `target_actor_specs`
- AirSim `settings.json`
- scenario metadata 中的 `drone_count`

各子智能体不得在算法路径中假设固定 `2v2` 或 `5v5`。历史 2v2/5v5 文档、fixture 和回归测试可以保留，但新增仿真入口必须按输入数组长度运行。

## D1 多传感器融合

- 输入观测数量由 main 场景决定。
- 按 `truth_objects`、`resources`、`camera_vehicle_names` 的实际长度生成观测。
- 不在 D1 内部写死 5 个目标或 5 个资源。

## D2 多目标关联

- 跟踪器按 `GlobalTrack[]` 和 observation 数量动态创建/删除航迹。
- `id_switch_count`、`track_continuity` 按实际目标数量统计。
- 5v5 只能作为基准场景名，不作为算法常量。

## D3 集中式分配

- AssignmentPlanner 输入为 `GlobalTrack[]` 和 `ResourceState[]`。
- Hungarian/Min-Cost Flow 的矩阵维度由输入长度决定。
- N 变化时，输出 `AssignmentPlan.assignments` 数量可小于、等于或大于目标数量，取决于资源约束和未分配代价。

## D4 分布式协同与降级

- 健康监测、二级节点接管和分布式协商按实际节点集合运行。
- 二级节点数量由 main 注入，默认不是算法常量。
- 主动降级仲裁只读取 D1/D2/D3/D5 的不确定性和一致性指标，不假设固定 5 个资源。

## D5 终端视觉配准

- `LocalVisualTrack[]`、`GlobalTrack[]` 和相机集合均由 main 输入决定。
- 几何配准使用 `GlobalTrack -> CameraModel -> bbox center`，不使用 AirSim truth ID 做在线关联。
- `ambiguous_count`、`association_accuracy` 等指标按实际 N 汇总。

## D6 评估指标

- 所有 rate 类指标按实际机会数归一化。
- 报告中记录 `drone_count`、目标数量、资源数量、二级节点数量。
- 2v2/5v5 报告模板可以保留，但 N-v-N 运行必须生成通用摘要。

## D7 比例导引

- 每个 resource-target assignment 独立持有 PN/PNG 状态。
- 不共享 terminal filter，不按固定 5 个 pair 初始化。
- main 为每个有效 pair 创建 D7 控制上下文，并把 D5/D4/D3 合同状态传入。

## Main 运行时实现约束

- 新增 `--drone-count N` 作为 AirSim runtime 的统一规模入口。
- 对 Multirotor/SimpleFlight 模式，main 动态生成 N 个 `Interceptor1..N`。
- 对 ComputerVision 模式，main 动态生成 N 个 `Interceptor_Cam_1..N` 或专项前缀相机名。
- main 动态生成 N 个 `MSM_TargetActor_1..N`。
- main 在输出目录保存本轮生成的 AirSim settings，便于复现实验。
