# D5 终端视觉配准与身份认证计划

## 2026-07-21 跨视角困难样本课程与准入视图

- [x] 只读审计冻结正式图语料的 99 条未标注边。194 个缺失端点中 95 条边两端缺失、4 条边缺
  source 端；冻结导出没有精确 offline observation truth lineage，同 tracklet 也无其他 evaluator
  label，可靠回填数为 0。99 条边继续 `unavailable`，未修改正式源，未采用最近邻、连续性或伪标签。
- [x] 新增独立 supplemental producer，使用与正式源分离的随机流、100 个训练 seed 和 45 个场景
  规模 cell，覆盖相机基线、密集交叉、遮挡进出、时间偏差、外参扰动、漏检、虚警和 tracklet
  重入。候选边仍使用默认时间、视场、极线、射线、重投影、协方差和度数门，不提供降低门限参数。
- [x] 保持在线节点匿名，truth 只在图构建后按精确 observation lineage 加入物理分离 evaluator
  制品。manifest 绑定 Git/config/schema/version、正式 manifest、training/shared registry、默认门
  配置、实现文件和全部制品 SHA-256；拒绝保留 seed、重复图/边、缺标签、hash 篡改、split 泄漏、
  候选门变化、负边伪造和正式源变化。
- [x] 实际生成 4,500 帧、66,726 节点和 245,032 边，正/负/未标注为
  `57292/187740/0`，标签可用率 100%，与正式源重复违规为 0。共享 seed 分桶为 `60/20/20`。
- [x] 建立 detached formal + supplemental canonical admission view，不复制或回写两类源数据。组合
  视图选入正式 472 帧和补充 4,500 帧；各 split 无边比例不超过 10.45%，负边支持均远高于
  `100/30/30`，候选召回分母均高于 100，标签可用率与双类 cell 比例均为 100%，数据支持门通过。
- [x] 本轮明确只闭合 producer 与数据支持，不训练新模型、不生成 `.pt`、不开放 G1/assist，D5 不
  创建、改写或换绑 `global_track_id`。专项 `12 passed in 5.49s`，全量 D5
  `498 passed in 124.90s`。
- [x] main 已基于 clean commit `79b2550ce2ef407c7cfcc653ce04a80fe2226c06` 在 detached worktree
  同配置复生。clean output 已归档到
  `outputs/tracklet_graph_supplemental_curriculum_20260721_clean_79b2550_r2`；补充 manifest/view SHA
  为 `4b9875fee86b5c425f683a6da23e6af1308bcf2383d3633d4fd6207fe2f25a32` 和
  `11e8acbdbe268574ead402f2be5c9aa8e3459a7e4147a18e0570df3402892415`。dirty=false，数据支持与
  `training_readiness` 均 pass，dirty provenance blocker 关闭。
- [ ] 当前 pass 只适用于训练数据来源和数据支持。仍需单独训练新模型、使用保留 seed 做独立评估
  并完成同 seed 影子对照，才可讨论 model promotion。当前没有 `.pt`，G1、assist 和在线/相机控制
  权限均为 false。
- [x] 主工作区严格复载 clean supplemental 与 composite view，实测 manifest/view SHA 命中、
  `data_support=pass`、`training_readiness=pass`、promotion 等待模型证据；专项测试
  `12 passed in 5.40s`。正式源全树指纹复载前后不变。

## 2026-07-21 Supplemental BC 全样本准入审计

- [x] 新增只读 fail-closed 审计入口，复用 strict lazy loader、canonical loader、既有 supplemental
  合同审计与 BC 候选特征 API；逐项复核 dataset 全文件 SHA/集合、1200 个样本、版本、中心 ID、
  truth/dirty/reserved、synthetic ACK 边界和四类 unavailable label。JSON/Markdown 只能原子写到
  supplemental 与 registry source root 之外；绑定错误仍写 `pending` 报告并由 CLI 返回非零。
- [x] 2026-07-21 对 clean commit `13e37286d2996a227924bb1a8e2766e52116a534` 的实际制品完成审计。
  接受阈值为 100 episode、1200 sample、canonical `60/20/20` 与 `720/240/240`、302/302 文件 SHA、
  1200/1200 有限特征和零违规；实测全部通过，7800 个候选特征行、1200/1200 唯一规则示范、
  truth/reserved/dirty=0。tracked JSON/中文报告已发布，内容 SHA 为
  `a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`；新增专项
  `4 passed in 35.72s`，D5 全量 `486 passed in 119.63s`。
- [x] 关闭 supplemental producer/canonical 之后的 behavior-cloning full-sample audit 子项；确认
  `400/400/400` 仅为 synthetic 故障覆盖，四类 label 均 `0/1200 available`。本轮没有训练、AirSim、
  `.pt` 权重或数据树写入，PPO/assist/authority=false，rule fallback required=true。
- [ ] 由 main/D6 完成跨模块学习准入审计；真实 runtime ACK/outcome、reward/counterfactual/causal、
  paired shadow 未完成前，不开启 PPO、assist、在线或相机命令 authority。

## 2026-07-21 主动视觉课程阶段 B1b2

**Clean evidence：** main 已在 detached clean worktree `13e37286d2996a227924bb1a8e2766e52116a534` 完成 100/800/1200 与 canonical `60/20/20`、`720/240/240` 的实际生成；dataset/view/config/training-registry/shared-registry/summary-content SHA 分别为 `0c474ee1b0bab34a46c2ebce328761983cf2ecc757da30c2d3d2e03a06cd1acf`、`0ab1a4a6bdd439f6c8a74df5059de3c4950791fba35a1b9514942e83779f72a8`、`e93ca6310338be5db4539fac195f5257e28d16a64b78b1a0351bf6aeca01fcee`、`2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`、`68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`、`0577c73810413ced6277e679477422f467cb2db094f1d376e39e4cbb2a3abd65`，正式树前后 SHA 同为 `8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`；clean producer/canonical evidence 已关闭，synthetic ACK 不作真实 ACK，PPO/assist 仍关闭。

- [x] 新增独立 100-seed producer。严格读取 training registry 的 100 个 seed 和 `1000-1019`
  保留目录，预检 shared registry schema/content/source binding，并在 canonical API 中完整复算 policy、
  assignment 与 `60/20/20`；两个 registry 文件 SHA256、dataset config、manifest、view/content 和
  readiness SHA 均进入 summary。
- [x] 每 seed 只调用 `build_active_vision_curriculum_episode()`，随后复用
  `stage_active_vision_episode_record()`、`unavailable_active_vision_offline_labels()`、
  `stage_active_vision_offline_labels()`、`finalize_active_vision_episode_dataset()` 和 lazy loader；未复制
  active-vision 在线/离线序列化合同。
- [x] 输出目录必须不存在。100 episode 在 sibling 临时目录完成全部生成、finalize、canonical、
  readiness、逐 episode 审计和重载复核后才用 `os.replace()` 发布；目的目录竞争出现或任一步失败均
  不发布并清理临时目录。
- [x] training/shared registry 各自的父目录均作为只读 source root；正式布局中 shared registry
  位于 training root 下时由外层根覆盖，二者分离时分别保护。output、tracked JSON/Markdown 等于或
  位于任一根下时，在创建目的、临时或 tracked 目录前失败关闭，并保持 registry 文件哈希不变。
- [x] 聚合合同固定为 100 episode、800 segment、1200 sample；canonical seed/episode
  `60/20/20`、sample `720/240/240`。四 intent、wide/zoom、interceptor/recon 和三 ACK 均逐 seed
  复核；`4/4/4` 只记为 executor 故障覆盖，不作为真实 ACK 分布或收益。
- [x] reward/outcome/counterfactual/causal label 全部显式 unavailable；synthetic、dirty、truth、
  reserved leakage、版本和中心 ID 均失败关闭。dirty 状态为 `fail_closed_dirty_source`；PPO、assist、
  在线 authority 和相机命令权为 false。
- [x] CLI required 参数为 `--output-dir --training-seed-registry --shared-seed-registry
  --created-at-utc --global-track-id`，默认读取 Git provenance，可选
  `--tracked-summary-json/--tracked-report-markdown`，Markdown 报告为中文。2026-07-21 新增专项
  `15 passed in 71.87s`，D5 全量 `482 passed in 83.05s`。
- [x] main 已在上述 clean revision 使用正式 registry 执行 CLI，归档 ignored output、tracked
  JSON/中文 Markdown 及实际 SHA；正式 900-episode 输入树未修改。
- [x] 已对绑定 dataset/view/config/registry 执行 supplemental BC 全样本审计并发布零违规证据。
- [ ] 由 main/D6 做跨模块准入审计；真实
  runtime ACK/outcome、reward/counterfactual/causal label 和 paired shadow 未完成前，不开启
  PPO/assist/在线或相机命令权。

## 2026-07-21 主动视觉课程阶段 B1b1

- [x] 新增 `active_vision_curriculum.py` 的单-seed、纯内存 supplemental curriculum builder。
  调用方必须显式提供 `ActiveVisionSourceIdentityV1`、配置和中心拥有的 `global_track_id`；builder
  只读复制该 ID，不创建、改写或换绑中心身份，任意非负整数 seed 均可确定性构造，负 seed 拒绝。
- [x] 固定 8 个片段形成 1 个合法 `ActiveVisionEpisodeRecordV2`、12 个连续样本。intent 精确为
  `hold=2 / observe_target=6 / reacquire=2 / search_sector=2`，FOV 为 `wide=10 / zoom=2`，角色为
  `interceptor=6 / recon=6`；每个角色都覆盖四类 intent、`wide/zoom` 和三类 ACK 结果。
- [x] 全部 effective action 都由按片段隔离状态的 `DeterministicLookAtScanPolicy` 经
  `ActiveVisionControllerV1` 产生，再进入 `DeterministicCameraCommandExecutor`；未手填 decision 或
  非法 effective action。两个三帧 observe 片段分别通过既有稳定门自然产生 `WIDE/WIDE/ZOOM`。
- [x] ACK 精确为 `applied=4 / rejected=4 / missing=4`。producer 调用执行器时始终令
  `command_version == action.communication_version`；accepted ACK 与反馈最近接受版本一致，rejected
  和 missing 对执行器输入反馈保持对象不变且不推进最近接受版本。该分布是确定性故障输入覆盖，
  不是 main/runtime 的真实 ACK 频率证据。
- [x] sample timestamp 严格递增，sequence index 为 `0..11`；plan/coalition 按片段单调推进、
  communication 按样本严格递增，snapshot/action/sample/ACK 版本逐项一致。在线 record 通过 truth
  guard，不含 evaluator identity；builder 不生成 reward、outcome、counterfactual 或 causal label，
  不写磁盘、不接 canonical/CLI/报告。
- [x] 同 seed 的 record 对象和规范 JSON、summary 对象和 JSON 均确定；调用方 source/config 输入不变。
  2026-07-21 新定向测试 `12 passed`，主动视觉关联回归 `56 passed`，D5 全量
  `467 passed in 10.40s`，`py_compile` 通过。
- [x] B1b2 已复用该 builder 完成独立 100-seed 生成、detached finalization、canonical
  `60/20/20`、CLI 和严格统计接口；clean producer/canonical evidence 后续已由 `13e3728` 实际制品
  关闭。supplemental BC 全样本审计也已关闭；开放项仅为 main/D6 跨模块准入、真实 runtime
  ACK/outcome、reward/counterfactual/causal、
  paired shadow 及 PPO/assist/authority 准入。

## 2026-07-21 主动视觉相机执行器阶段 B1a

- [x] 新增无隐藏状态的 `DeterministicCameraCommandExecutor`。输入沿用现有 snapshot、action 和
  camera feedback，并显式携带执行时刻、期望计划/联盟/通信版本及可选故障注入。
- [x] 每个动作先通过 `validate_active_vision_action_v1()`；随后只允许反馈态和运行时故障增加拒绝，
  不允许绕过或放宽既有版本、身份、投影、友方、云台和 FOV 门。
- [x] 冻结三态结果：`applied` 生成 `accepted=true/status=applied` ACK 并更新动作后反馈；
  `rejected` 生成稳定拒绝 ACK 且原反馈不变；`missing` 保持 `runtime_ack=None`、反馈不变且
  `applied=false`。
- [x] 成功 ACK 的 `command_version` 与反馈 `last_accepted_command_version` 一致；ACK 的计划、联盟和
  通信版本沿用已验证 action，可直接通过现有 episode sample 合同。旧命令版本失败关闭。
- [x] 2026-07-21 定向测试 `18 passed`，D5 全量 `455 passed in 12.18s`。覆盖 WIDE/ZOOM/HOLD、
  过期、三类版本错、相机忙/不可用、FOV 不支持、非法动作、ACK 缺失、truth guard、确定性和输入不变。
- [x] 阶段 B1b2 已接 supplemental curriculum producer、canonical `60/20/20` 和统计接口。
- [x] main 已在 clean revision `13e3728` 生成 detached supplemental 制品并归档实际 SHA，关闭 clean
  producer/canonical evidence。
- [x] supplemental BC 全样本审计已完成并绑定 clean 数据 SHA。
- [ ] main/D6 跨模块准入、真实 runtime ACK/outcome、reward/counterfactual/causal、paired shadow 和
  PPO/assist/authority 准入仍未完成；B1a/B1b2 与本审计均未运行 AirSim。

## 2026-07-21 主动视觉宽视场稳定门阶段 A

- [x] 在 `DeterministicLookAtScanPolicy` 内建立按相机、中心目标、计划版本和联盟版本隔离的状态键，
  默认连续 3 帧稳定后才允许由宽视场切入窄视场；`N=1` 保留即时缩放兼容选项。
- [x] 稳定帧继续复用既有新鲜度、可见概率、遮挡、关联置信度、`in_fov`、当前分配、版本、通信、
  友方保留和云台包络门，不降低任一安全阈值。
- [x] 对计划/联盟/目标变化、时间回退、证据回退、低置信/投影失效、通信异常、友方冲突和相机忙
  清空相机局部计数；重复同一帧不累计，不同相机不串状态。
- [x] 多个当前分配投影的质量间隔小于默认 `0.05` 时按歧义处理，输出
  `REACQUIRE + WIDE`；重捕获和扫描选择 `WIDE`。云台忙时保持当前 FOV，恢复后从宽视场窗口重计。
- [x] 新增 8 项稳定门专项；主动视觉定向组合 `47 passed`，D5 全量
  `437 passed in 10.28s`。未运行 AirSim，未训练或晋级模型。
- [x] 阶段 B1b2 已建立 supplemental curriculum producer 接口，覆盖
  hold/observe/reacquire/search、两相机角色和视场边界，且不修改正式 900 episode。
- [x] 软件阶段 tmp_path fixture 保留为历史验收；main 后续已在 clean revision `13e3728` 生成实际
  supplemental 制品并归档 SHA，正式 900-episode 输入树哈希前后不变。
- [ ] main/runtime 将真实 applied/rejected/missing ACK 以现有 episode 合同回灌后，再决定是否把 ACK
  纳入稳定门。当前 snapshot 不含 ACK，本阶段不得伪造或扩 DTO。
- [ ] 只有在阶段 B 数据覆盖和准入门通过后才重训 development bundle。旧 v5 bundle 绑定阶段 A
  之前的实现 SHA256，严格加载应失败关闭，不得沿用旧权重解释新规则候选。

## 2026-07-21 共享 canonical seed 视图

- [x] 为 tracklet graph 与 active-vision episode 分别实现 strict、detached、只读的 canonical
  split view；复用原 strict loader，不改原 manifest，不复制或重写在线/离线样本。
- [x] 独立复算 training/shared registry 的 file/content/assignment SHA256、D3-compatible 数值 seed
  策略和 `60/20/20` 分桶；缺失、多余、重复、错桶、schema/policy 变化及 seed `1000-1019` 均失败关闭。
- [x] 冻结 source manifest/content、registry、consumer/source schema、canonical split/training-set
  hash 和 episode/sample/edge 计数，并生成两类 tracked detached manifest 与中文 readiness 报告。
- [x] 图 readiness、图开发训练/评估和主动视觉 BC 增加显式 canonical 参数；三个路径参数必须成组
  提供。默认不带参数时继续使用原 split，避免静默改变既有开发模型语义。
- [x] 正式图视图为 seed `60/20/20`、episode `7715/2574/2562`、edge `281/116/83`；正式主动视觉
  视图为 seed `60/20/20`、episode `540/180/180`、sample `695705/229651/227886`。保留 seed 泄漏为 0。
- [x] 验证原数据树前后内容哈希不变；2026-07-21 新增 15 项 canonical 专项，D5 全量
  `429 passed`。未运行耗时完整模型训练。
- [ ] graph producer 继续补 edge-bearing frame、真实困难负边和完整 candidate-recall 分母；canonical
  对齐不改变 `12532/12851` 无边事实，G1/assist 保持失败关闭。
- [ ] active-vision producer 补 hold/observe/recon、applied-action runtime ACK、独立 reward/
  counterfactual/causal label 与 paired shadow。旧 v5 bundle 不因重分桶自动晋级或改绑。
- [ ] main 更新 VERSIONING，登记 view schema、两类正式 view/hash 和 D4/D5 split 视图已对齐；D5
  owner 不修改 main-owned 文件。

## 2026-07-20 主动视觉行为克隆准入

- [x] 对正式 900-episode、1,153,242-sample 数据执行严格 loader、逐制品 SHA256、schema、整 seed
  原子分割和保留 seed 隔离检查；train/validation/test 唯一 seed 为 `60/20/20`，交集为 0。
- [x] 运行可复现容量探针并采用流式特征缓存。候选动作数为 4-7，完整缓存含
  `4,669,959/1,625,596/1,565,555` 条 train/validation/test 候选行，未把全数据驻留内存。
- [x] 固定 seed `20260720` 在完整 train split 上运行 5-epoch 行为克隆；每 epoch 使用 685,005
  样本，总样本呈现次数 3,425,025，未抽样冒充正式训练。
- [x] 输出总体、逐意图、逐相机类型、逐规模指标和 CPU P50/P95/P99。test 精确动作准确率
  `0.955978`，但 `observe_target` 召回/F1 为 0、`hold` 无正样本、recon 精确动作仅 `0.621823`。
- [x] 完成只读温度校准审计。`T=0.906731` 只轻微降低 test NLL，ECE 反而增加，因此不写回 bundle。
- [x] 生成 v5 development bundle，绑定 dataset/split/training/config/code/weight SHA256；shadow 可
  加载，assist 必须以 `bundle_assist_not_admitted` 拒绝，PPO=false，规则回退必需，相机命令权=false。
- [x] 权重与完整 bundle 只保存到 ignored `outputs/`；tracked results 只保存命令、配置、指标、哈希
  和本地定位。2026-07-20 D5 全量 `414 passed`。
- [ ] producer 以独立场景和 seed 补充 hold、observe_target、recon、不同 FOV 及动作边界示范，避免
  `reacquire` 占比 92.16% 造成多数类假高分。
- [ ] 在 shadow 模式真实产生 requested action，记录 runtime ACK、执行后 outcome、时延和规则回退，
  建立动作归因。无动作归因的相邻观测不得作为 reward。
- [ ] 至少 20 个完全未见 seed 完成 paired shadow 非退化评估后，再讨论 assist；在此之前保持
  `development_shadow_only`。PPO 需独立 reward/counterfactual/causal label，本阶段不启动。
- [x] 2026-07-21 通过共享 canonical seed 只读视图关闭 D4/D5 split 身份不一致。联合模型仍因标签、
  准入和运行合同未满足而关闭；main 在 VERSIONING 中登记 active-vision bundle v5、view schema
  及无 git-lfs 时权重仅位于 ignored outputs 的规则。

## 2026-07-20 正式跨视角图数据准入与补数

- [x] 对 `learning_generation_v1_multibatchfix` 的 12851 个 D5 图帧执行只读严格加载；逐文件验证
  graph/label SHA256、schema、feature version/order、split hash、training-set hash 和 class balance。
- [x] 复核整 seed 分割：train/validation/test 唯一 seed 为 `60/20/20`，交集为 0；保留评估 seed
  `1000-1019` 未进入训练。
- [x] 冻结训练准入门：各分割 edge-free 比例 `<=0.90`；训练正/负边至少 `100/100`，验证和测试
  正/负边至少 `50/30`；candidate recall 标签可用率为 1.0 且每分割 pair 分母至少 100；至少
  80% 场景规模 cell 同时具备正负边；测试至少 20 个唯一 seed。
- [x] 审计结果失败关闭：总 edge-free 为 `12532/12851 (97.52%)`，仅 319 帧有边；三分割边为
  `286/99/95`，负边为 `11/4/4`；partial candidate recall 分母只有 `4/1/1`。15 个数据门失败。
- [x] 新增显式 `development-only` 训练路径。正式训练对不完整验证真值仍失败关闭；开发模式只使用
  已标注 candidate edge，误合并率和 candidate recall 保持 unavailable，不允许用零代替。
- [x] 将图模型 bundle 升为 v3，绑定 readiness audit、数据/split/training/config、节点/边特征和
  实现代码 SHA256；开发 bundle 固定 `default_model=false`、`g1_assist_eligible=false`。
- [x] 固定 seed `20260720` 完成 40 epoch 开发训练：最佳 epoch 38，权重 SHA256
  `9bbe53d6...35cbf2d`；验证/测试 F1 为 `0.9804/1.0`，但各只有 4 条负边，promotion 继续
  `fail_closed`。两次固定 seed 运行权重哈希一致。
- [x] 权重和完整 bundle 只保存到 ignored 的 D5 `outputs/`；`results/` 仅保存命令、配置、指标、
  哈希和本地定位，不复制权重。
- [x] 2026-07-20 验证：图训练专项 `16 passed`，D5 全量 `412 passed`，语法检查通过。
- [ ] main 更新 `research_modules/scalable_3d_simulation/VERSIONING.md`：登记 D5 tracklet bundle v3，
  并明确无 git-lfs 时开发权重不进入普通 Git。本 D5 owner 不修改 main-owned 文件。
- [ ] producer 增加新独立 seed 的相机重叠、密集交叉、遮挡进出、时延重捕获、有界外参扰动和
  epipolar/投影上可混淆的异目标；不得通过复制样本或降低在线安全门补足负边。
- [ ] 补齐评价帧全部 camera-local tracklet 的离线标签及候选裁剪前同目标跨相机 pair 总表，使
  candidate recall 在 validation/test 上具备可审计分母。补数后重新生成新版本数据集并重跑审计。

## 2026-07-20 同相机多批次阻塞修复与正式数据复跑

- [x] 核对正式失败语义：`learning_generation_v1_oosmfix` 已保存 209 条完成记录
  （sequence 0-208），下一项 `communication_degraded` 200v200 因同一次 D5 调用包含同相机多个
  已到达批次而失败。该输入是通信队列积压后的合法排空，不是相机串流或规模配置错误。
- [x] 将 `adapt_batches()` 改为两阶段事务。全部 batch 先完成 truth-free、有限性、来源唯一性和
  per-stream 暂存高水位预检，再按 arrival、resource、camera、measurement 规范顺序提交；任一
  duplicate arrival、已提交 arrival rollback 或 duplicate measurement 均不允许产生部分状态更新。
- [x] 保持既有 OOSM 语义：合法迟到 measurement 保留原双时间戳和几何，只增加 OOSM 计数并推进
  arrival 高水位，不更新或老化 tracker，不生成局部轨迹。
- [x] `process()` 的 `camera_batches` 保留全部到达批次；关联图和 source-observation link 只取每个
  camera stream 最后一次有效状态更新，防止稳定 local track key 的历史版本重复进入一个图快照。
- [x] 对每流登记全部已接收 measurement 时间戳，较早正常帧和已忽略 OOSM 的重传也判为 duplicate；
  登记仅用于去重，不改变运动状态、身份或中心绑定。
- [x] 新增同流两正常批次、同流正常/OOSM 混合、历史 measurement 重传、duplicate arrival/
  rollback/measurement 原子拒绝、多相机多批次确定性与不串流回归。2026-07-20 定向
  `31 passed`、D5 全量 `410 passed in 11.68s`，语法和 `git diff --check` 通过。
- [ ] main 按 `VERSIONING.md` 在同时包含 D5 与 runner 修复的新干净提交上，使用新输出目录从
  sequence 0 开始重建正式 900 episode，并完成 900 条进度、45 cell × 20 seed、finite、clean、
  online truth use=0、checkpoint 和数据最终化审计。绑定 `c5a9f6d` 的旧 209 条目录只保留为故障
  证据，不得恢复、续写或与新数据集拼接。

## 2026-07-20 通信退化 OOSM 修复与正式 resume

- [x] 定位 sequence 29 失败：main 已按 arrival 顺序交付，D5 camera-local tracker 错把 measurement
  时间作为流接收顺序，并在更新时覆盖当前状态时间。
- [x] 按 camera stream 分离 arrival 高水位和 measurement 高水位。合法 OOSM 保留双时间戳并以
  `oosm_ignored` 接收，但不回退、创建、老化或更新 tracker 状态；累计计数随批次 metadata 输出。
- [x] 对 arrival 回退、重复 arrival 和同 measurement 重传在状态变化前失败关闭；不按 measurement
  重排接收语义、不改写时间戳、不使用 truth ID、不创建或改写 `global_track_id`。同一次调用的多个
  已到达批次现按 arrival 主键规范排序，具体见上节。
- [x] 新增 arrival 单调/measurement 乱序正例，以及 arrival 回退、原样重复和同 measurement 重传
  负例。2026-07-20 定向 `24 passed`、D5 全量 `403 passed in 9.74s`，零失败。
- [x] 原 `learning_generation_v1` 保留为旧 revision 失败证据。main 在修复提交的新目录
  `learning_generation_v1_oosmfix` 完成首个 45-episode 分块，原 sequence 29 对应 OOSM cell 已通过。
- [x] main 在同一 clean revision 上完成 checkpoint resume；新目录累计 209 条完成进度
  （sequence 0-208），未把旧版输出混入该正式集。随后阻塞属于同相机多批次，见上节。
- [ ] 正式分块结束后统计 `oosm_measurement_ignored_count`。若 OOSM 占比或信息损失不可接受，再单独
  设计有界固定时滞历史与确定性重放；当前不以未验证回放替代保守失败关闭路径。

## 2026-07-20 200v200 clean-tree 复测与下一热点

- [x] main 在提交 `4052d9411363c39d52100c0e3a4f60ee88443cab` 上完成 nominal 200v200、
  2 s、seed 930-932 clean-tree 复测；三场 `repository_dirty=false`、online truth use 为 0。
- [x] 确认重复 finalization 审计热点关闭：总 finalization 由 `116.5624 s` 降至 `7.7377 s`；
  D5 graph staging 为 `0.0250/0.0259/0.0290 s`，且 graph dataset 正常最终化。
- [x] 确认端到端收益与边界：artifact staging `225.9243→126.4682 s`，总生成
  `467.8007→262.2866 s`；episode run `125.2205→127.9871 s`，不宣称在线仿真加速。
- [x] 完成 D5-owned active-vision sample/writer 性能修复。剖析确认 gzip level 6 只占少量时间，
  主因是共享 snapshot 被每个 camera sample 重复执行中心引用与递归 truth-free 审计，以及 writer
  重复规范化对象。200-camera/400-track fixture 构造 `2.3597→0.1097 s`、materialized load
  `2.3948→0.1802 s`；既有 3,536-sample 制品 writer `3.5529→0.7313 s`。gzip/解压字节和 SHA256
  修改前后完全相同，采样、特征、在线/离线分流、版本/ACK、只读和失败关闭合同保持。
- [x] main 在提交 `45b36500dc3c6935b1f116614993e291041eb12d` 上完成同一 nominal 200v200、
  2 s、seed 930-932 的 clean-tree postopt2 复跑。三场均 finite、`repository_dirty=false`、online
  truth use=0，D5 graph 正常最终化；active-vision staging 从历史
  `41.5623/43.2639/41.2271 s` 降至 `4.0494/3.9898/3.9995 s`。总 staging
  `126.4682→12.4372 s`，总生成 `262.2866→144.5513 s`。该系统级证据关闭 D5 writer P1，
  但不构成在线实时性或模型准入结论。
- [ ] 生成并最终化正式 900-episode corpus，随后运行正式 BC/PPO、checkpoint 制品、paired shadow
  与 assist 准入。当前仅 3 个 seed，因不足 20 个未见测试 seed 返回
  `insufficient_unseen_test_seeds`，该失败关闭状态符合合同但不构成训练准入。

## 2026-07-20 200v200 主动视觉容量与跨视角 seed 隔离

- [x] 将 active-vision online record 升为 record/sample v2：确定性 `.online.jsonl.gz` 按 SHA256 key
  去重 snapshot/camera feedback，sample 只保存稳定引用；全部动作、版本、反馈和 ACK 字段保留。
  `ActiveVisionEpisodeRecordV2/SampleV2` 为正式名称，V1 Python 名称仅是源码兼容别名。
- [x] 新增 `stage_active_vision_episode_record()` 与 `stage_active_vision_offline_labels()`：在线
  `online/*.online.jsonl.gz` 逐行拒绝 truth/actor/object identity，evaluator reward/outcome/
  counterfactual/causal label 只存在于物理独立 `offline/*.offline.json`，并在 episode 结束后按
  `sample_key + observation_key` 精确连接。
- [x] offline staging 改为 SHA+逐行 contract audit，只保留一个当前 snapshot 和紧凑 key/index；
  不调用完整 record loader。非物化 sample 使用合同摘要校验，不再重复遍历共享 snapshot；episode UID、
  source identity、对象哈希/引用、动作/版本/反馈/ACK 和 sample join 仍完整校验，online 字节篡改以
  `online_sha_mismatch` 失败关闭。
- [x] finalize 的 staged audit 改为逐 episode `materialize=False`，不调用兼容全量 dataset loader，
  不跨 episode 累积 record/sample；同一次 finalization 的最终结构复核复用仍匹配文件指纹的 stream/
  SHA 证据，避免二次解压、反序列化和哈希。公共 lazy/audit API 不接受内部证据，仍从磁盘独立完整
  复核。公共 lazy handle 提供逐 split 的 episode、BC 和 PPO iterator。
  BC 只物化当前 online 规则示范，PPO 只物化当前 episode 并逐项核验离线 reward availability。
- [x] reward 固定 `[-1,1]` 并带 availability/provenance；无 outcome 时 reward 为 unavailable/null，
  无 outcome+counterfactual 时 causal label 为 unavailable/null，禁止用 `0` 伪装缺失值。
- [x] finalize/loader 保持完整 `(scenario_version, seed)` group，并把共享同一数值 seed 的所有
  scenario/scale group 原子分到同一 split；数量按唯一 seed 计算。少于三个唯一 seed、少于声明
  unseen seed、group/seed 跨 split、未知中心 ID、局部换绑、版本回退、SHA/schema/source identity/
  offline join 错误均失败关闭；正式默认 minimum unseen seed 为 20。
- [x] manifest 固化 schema/version、dataset config、逐文件/split/training-set SHA256、source Git
  commit/dirty 与 source config SHA、availability 和共享 seed 原子策略；`SHA256SUMS` 精确覆盖目录，
  finalize 后文件只读。
- [x] loader 输出不可变对象；BC 视图只取规则示范且不加载 evaluator label，PPO 视图只取 effective
  action 并要求每个样本 reward available。`ActiveVisionTransition.reward=None` 是唯一缺失表达。
- [x] active learning dataset 保持 v2；episode dataset 升 v3、descriptor/record/sample 升 v2、主动
  视觉 bundle 升 v4。旧 v1 嵌套 record 返回稳定 unsupported-schema，snapshot/action/feedback/
  ACK/offline-label 保持 v1；没有正式 admission report 时仍不能 assist。
- [x] 复核并修复 tracklet split：共享数值 seed 的跨 scenario/scale group 原子分配，test seed 对
  train/validation 完全未见；tracklet dataset/bundle 均升 v2，少于三个唯一 seed 失败关闭。
- [x] D5 最终复核：相对 dataset root 可完成 staging/finalize/load；非 assist mode 只能落盘规则
  effective action；resource/camera/local tracklet ID 全部拒绝 truth/actor/object-like 命名。
- [x] 2026-07-20：16→64 camera fixture 的旧嵌套字节 `302709→4336869`，v2 去重解压
  `59617→234721`，gzip `3995→13084`；200-camera/400-track 单 snapshot 为
  `731412/37004` 字节（解压/gzip）。12 episode × 48 camera × 96 track 回归共 `576` samples，
  finalize/audit 的完整 record/dataset loader 调用为 0。
- [x] 2026-07-20 开销收敛：6 episode × 48 camera × 96 track 的确定性计数中，finalize stream/offline
  parse 从 `12/12` 降至 `6/6`，SHA256 从 `67` 降至 `20`，20 个制品各哈希一次；独立 public audit
  仍另做 `6/6` 次 parse 和每制品一次哈希。200-camera/400-track 合成 stream audit 辅助墙钟约
  `9.81→0.37 s`；已有 nominal/dense 200v200 文件独立 audit 约 `2.08/2.21 s`。墙钟不是硬门。
  数据管线 `18 passed`、D5 全量 `400 passed in 9.74s`，接受阈值为零失败。
- [x] main 容量复测：nominal seed 91、每档 2 s 的 5/20/50/100/200v200 总制品约
  `0.086/0.295/0.733/1.543/2.884 MB`；200v200 online/offline 为 `1.064/1.818 MB`、`3536`
  samples、RSS 约 `1.04 GB`、online truth=0。该结果关闭单 episode 去重容量门。
- [ ] 正式 corpus 验收：使用真实 source Git/config identity 与独立 evaluator label 生成约
  900 episode 数据集，实测 finalize/lazy 训练的峰值 RSS、吞吐和故障恢复。本轮没有修改
  main/scalable runtime，也没有完成该 corpus 级压力验收。
- [ ] 正式数据与准入：收集代表性 train/validation/test、至少 20 个完全未见 seed、真实 outcome/
  counterfactual、困难场景和 paired shadow；完成正式 BC/PPO、冻结指标门与 checkpoint 审批。

本轮已关闭 D5 软件/容量合同、split 泄漏和 writer 的三 seed clean-tree 系统级复跑项，不关闭
nominal 200v200 正式 corpus/训练验收。postopt2 是 3 个 2 s episode 的离线制品计时，不是正式
训练、20-seed 实验、AirSim 运行、可见率/重捕获收益、在线实时性或 assist 准入。模块内
`docs/MODULE_PRINCIPLES_CN.md`、
`docs/ALGORITHM_AND_IMPLEMENTATION.md`、`docs/AIRSIM_INTEGRATION_PLAN.md` 和
`docs/EXPERIMENT_REPORT.md` 已按相同边界同步。

## 2026-07-20 主动视觉学习研究路径与 source observation 审计

- [x] 定义 `d5.active-vision-snapshot.v1` / `d5.active-vision-action.v1`；输入只含中心航迹和
  AssignmentPlan 只读引用、相机/云台/FOV、投影不确定度、可见/遮挡、通信和版本信息，递归
  拒绝 truth/actor/object identity。
- [x] 动作限制为 observe/search/hold/reacquire、有限 yaw/pitch 增量和 wide/zoom；无飞行控制、
  D3 分配、处置或授权字段，目标 ID 只能引用当前候选与相机分配交集。
- [x] 实现确定性 look-at/reacquire/scan 基线及统一 safety projection，覆盖 plan/coalition/
  communication version、候选成员、证据 age、FOV、机械角/当前与请求速率、slew、友方冲突、
  timeout、低置信、OOD、非有限输出和 bundle SHA/schema 错误。
- [x] 实现 library `disabled` 默认、CLI `shadow` 默认和 `disabled/shadow/assist` 决策输出；输出
  包含 requested/effective mode、fallback、latency、fingerprint 和三个版本。shadow 不改变规则动作。
- [x] 实现完整 `(scenario_version, seed)` group split，并把共享数值 seed 的跨场景 group 原子
  分配；提供原生 PyTorch behavior cloning 和 clipped PPO，学习模型只对有限安全动作候选评分，
  不增加 `torch_geometric` 依赖。
- [x] 实现主动视觉 manifest/state_dict/SHA256 bundle 与 `weights_only=True` 严格加载；paired
  shadow report 绑定模型、dataset manifest、split 和 training-set SHA。
- [x] assist 门固定为至少 20 个完全未见 seed、正式非合成证据，以及逐 episode/总体 safety、
  visibility、reacquisition delay 非退化；20-seed 合成 fixture 正例明确拒绝正式准入。
- [x] scalable adapter 只读传播 `source_observation_id`，同帧一 observation 对一 tracklet；新增
  evaluator-only observation label join，缺失假目标标签时 `labels_complete=false`。该键不参与
  tracker、图特征、tracklet/global ID 或 binding。
- [x] 2026-07-20：主动视觉专项 `17 passed`，D5 全量 `376 passed in 9.94s`；BC/PPO 为 8 个
  合成 seed 的 1-epoch smoke，checkpoint/bundle 只在 `tmp_path` 生成。
- [x] main 已将 snapshot 接到统一三维 episode 的 recon/interceptor 模拟相机状态和调度；输入
  包含实际 yaw/pitch/FOV、最近接受版本、D2 中心航迹、D3 计划和 D5 几何证据。规则动作经
  plan/coalition/communication version、有效期和资源一致性复核后在下一视觉帧应用，并发布
  `runtime.camera_command_ack`。5v5 开发冒烟为 `84/84` applied，200v200 seed 17、1.2 s 为
  `1872/1872` applied；两者仅是单 seed、脏工作树接口证据。
- [ ] 收集代表性 train/validation/test 和至少 20 个完全未见 seed 的正式 paired shadow 结果；
  当前无正式 checkpoint、无 assist 准入，不得把单测 fixture 写成性能或晋级证据。
- [ ] 在真实 AirSim 云台和后续实机上验证命令/ACK、机械速率、时延、reset 和失败回退；当前
  模拟相机接线不得写成真实执行或主动视觉因果收益。

`docs/AIRSIM_INTEGRATION_PLAN.md` 已同步“统一三维模拟接线已完成、真实 AirSim/实机仍待接入”
的边界；`docs/EXPERIMENT_REPORT.md` 已同步代码级 smoke 和“不构成正式准入”的口径。本阶段
没有新增 AirSim episode、settings、detector、相机外参来源或真实云台/FOV/ACK 证据。

## 2026-07-20 版本化数据、训练、校准与制品管线

- [x] 新增 `tracklet_dataset.py`：在线匿名图和 evaluator label 分文件写入；图归档不保存
  `truth_entity_id`/`shared_global_track_ids`，标签只在独立 evaluator JSON 中出现。
- [x] 固化 dataset/graph/label schema、节点/边 feature version 与精确顺序、generation config
  SHA256、class balance、candidate-recall availability、hard-negative provenance、split hash 和
  training-set hash；加载时以 `allow_pickle=False` 校验 SHA、shape、有限值、版本和 feature order。
- [x] 切分固定以 `(scenario_version, seed)` 为 group，完整 episode 随 group 进入
  train/validation/test；禁止 edge-level random split，同 seed 跨 split 直接失败关闭。
- [x] 新增多图梯度累积训练：固定 Python/NumPy/PyTorch seed，按 geometry gate score 选择
  hard negative，BCE `pos_weight` 处理类别不平衡；validation 独占模型选择、temperature
  calibration 和 F1 threshold selection，test 不参与调参。
- [x] test 输出 precision/recall/F1、constrained-cluster false-merge rate、candidate recall、
  Brier/ECE、P50/P95 inference latency 和 model size；完整真值不足时相应指标明确
  `unavailable/value=null`，不得补零。
- [x] 新增 `manifest.json + weights.pt + SHA256SUMS` bundle；manifest 固化模型语义版本、
  graph/node/edge feature 版本与顺序、hidden dim、message steps、训练数据/split hash、
  validation-only temperature/threshold 和验证结果。加载只允许 `torch.load(weights_only=True)`。
- [x] 在线 bundle scorer 仍只输出 candidate-edge same-target probability。bundle 缺失/损坏、
  SHA/schema/feature/version/state mismatch、非有限或越界输出、超时、低 certainty、无效阈值均
  回退现有 deterministic geometry rule；受约束聚类、同相机唯一、中心投影/Hungarian 和
  `global_track_id` 所有权不变。
- [x] 2026-07-20 验证：新管线 `12 passed`，稀疏图/adapter/新管线组合 `46 passed`，D5 全量
  `355 passed in 9.48s`；checkpoint 只在 `tmp_path` 生成，没有提交正式 checkpoint。
- [ ] P1 数据与准入仍开放：按本合同收集代表性 train/validation/test，test 至少包含
  20 个未见 seed，并覆盖近邻交叉、遮挡、时延和外参漂移；冻结门限后才能形成候选准入报告。
- [ ] 默认 checkpoint 仍开放：本轮只关闭训练/制品代码管线，不授予默认模型资格，不改变
  几何规则默认路径。

该阶段未改变 AirSim runtime；本轮新增主动视觉/source-observation 合同后，
`docs/AIRSIM_INTEGRATION_PLAN.md` 已在文首同步下一轮接线边界，仍未新增 AirSim 运行证据。

## 2026-07-20 匿名稀疏 tracklet 图与主动视觉接口

- [x] 新增严格匿名 `CameraLocalTracklet`：节点仅使用 camera-local namespace、双时间戳、
  bbox/中心、像素协方差、角速度、尺度变化和置信度；metadata 与本地 ID 中的
  truth/actor/object/global identity 失败关闭；构造器和递归 payload guard 另拒绝
  `TGT-0001`、`TargetDrone_1`、`Target_UAV_7`、`intruder-003` 等 truth-like local ID，
  并保留 `cam01-track-0001` 等正常 camera-local sequence。
- [x] 新增 `scalable_3d_adapter.py` duck-typed 在线入口：直接消费真实
  `OnlineSensorBatch`/`vision_bbox` 字段形状，不导入 main/D2/evaluator 类型；在 tracker 更新前
  拒绝 truth/actor/object/target/entity 字段和 truth-like 字符串，local ID 仅由 per-camera
  tracker 产生；`observation_id` 只读传播为审计键，不用于身份、匹配或 binding。
- [x] 按 `(resource_id,camera_id)` 隔离 IoU/中心门 tracker，输出双时间戳、中心/bbox 协方差、
  角速度和 bbox 尺度变化；支持有限漏检、空扫描、stream/episode reset。相机 metadata 生成
  `K/R/t` 及外参协方差；缺失独立 pose covariance 时只允许显式 configured fallback 并标源。
- [x] 六维 D2 center track 只读转换为现有 D5 `GlobalTrack` 投影假设；在线封装完成
  构图、确定性规则/注入模型边概率、同相机互斥聚类和中心 Hungarian binding。模型缺失、
  异常或低 certainty 有明确 fallback 状态，D5 不加载默认 checkpoint、不创建/改写中心 ID。
- [x] 新增时序、视场、极线、射线交会、重投影、像素马氏、中心 GlobalTrack 投影和
  外参/航迹协方差逐级门控；按 `max_neighbors_per_node` 确定性截断，避免构造全连接图。
- [x] 在几何门前增加相机 overlap/index：由位姿、截断视锥 AABB、量测时间窗和三维覆盖桶
  生成相机对；用 `camera_pair_budget` 限制实际检查数。预算后同桶间隔轮转和跨桶对角线轮转
  保持确定性和相机覆盖，未检查对保持 unbound。
- [x] 增加 `max_tracklet_candidate_edges_per_node`，优先按中心投影支持/时间近邻构造有界
  tracklet 候选，再执行极线、射线和重投影；不再构造每相机对 `n_left x n_right` 矩阵。
- [x] 边特征覆盖时间差、像素马氏距离、重投影误差、射线最近距离、bbox 尺度/变化、
  角速度、基线、外参协方差，并补充极线误差、交会角和中心投影支持。
- [x] 使用原生 PyTorch 实现 `NativeTrackletEdgeClassifier`，通过 `index_add_` 聚合消息；
  forward 只输出同目标边概率，不引入或依赖 `torch_geometric`。
- [x] 独立 `OfflineTrackletTruthLabel` 仅在在线图完成后构造训练标签；困难负样本按几何
  gate score 选择，BCE 使用正类权重处理不平衡。
- [x] 最终决策保持分层：受约束聚类保证每相机每簇最多一个 tracklet，中心 Hungarian
  binding 只能引用输入 `GlobalTrack.global_track_id`，运行时检查输出 ID 是输入集合子集。
- [x] 主动视觉动作域限制为观察目标、搜索扇区、云台增量、FOV/变焦；超时、低置信和
  无效中心 binding 回退确定性规则扫描。接口不包含飞行、分配、处置或授权动作。
- [x] 2026-07-20 seed 200 压力回归：200 目标、4 相机、800 节点，240000 可能跨相机对
  经两级索引形成 3050 个 tracklet 候选、2953 个最终 cap 前候选和 1923 条最终边，密度
  `0.006017`、最大度 6，本次 `0.442 s`；接受门为密度 `<0.01`、最大度 `<=6`、运行 `<15 s`。
- [x] seed 4 小样本 smoke：8 目标、3 相机、24 节点/192 边，24 正样本与 72 困难负样本，
  60 epoch loss `1.038521 -> 0.011535`、训练集准确率 1.0。
- [x] adapter 专项保持通过，训练/制品同步后 D5 全量 `355 passed in 9.48s`；覆盖 2/3/4 相机
  部分可见、跨帧 ID、假目标/漏检、7 类真值污染、中心 ID 不变、reset、空扫描与模型回退。
- [x] 5/20/50/100/200 相机结构矩阵：每相机 1 个匿名 tracklet、相机对预算 `2C`；200 相机
  的 19900 个总对只检查/保留 400，对预算丢弃 19500，tracklet 候选为 397，全部相机至少进入
  一个候选对。测试只约束结构上界，不使用易抖动的窄绝对时延阈值。
- [ ] P1：main scalable module stack 已调用 D5 adapter；main 需把新增扁平诊断
  `association.diagnostics` 持久化到 episode/D6，并在真实 scalable 3D 多 seed 下报告相机对预算
  命中率、漏配率、内存峰值和 P50/P95。camera pose covariance 仍应显式放入在线 metadata，
  evaluator truth 流继续物理分离。
- [ ] P1 数据/准入：独立整 episode 切分、困难负样本、校准、阈值和指标的软件管线已完成；
  仍需真实代表性数据、至少 20 个未见 seed、近邻交叉与遮挡/漂移场景及 CPU/GPU 时延预算。
  当前没有默认 checkpoint，不替换既有几何 Hungarian 主线。
- [x] main-owned scalable runtime 已接入模拟相机/FOV 命令、版本门控、下一帧应用和 ACK/timeout
  记录；规则 fallback 保持默认。
- [ ] P2：接入真实 AirSim 云台和实机执行反馈；BC/PPO 软件流程已有合成 smoke，但学习型主动
  视觉策略尚未用正式数据训练、验证或验收。

## 2026-07-16 ComputerVision 5+1 独立专项状态

- [x] 完成 5 个 `1920x1080`/60 度局部相机、1 个 `3840x2160`/75 度侦察相机、
  5 个 `Quadrotor1` actor 的真实 AirSim 运行；样本为 12 秒、49 帧、seed 7。
- [x] AirSim detect 与 YOLOv8 + 原生 ByteTrack 两路均按每个相机 batch 的
  `measurement_timestamp` 投影，并保持 online truth use=0、
  `global_track_id` rewrite=0。
- [x] detect 几何基线达到召回/配准/稳定/联合覆盖/侦察全覆盖/IDSW =
  `1.000/1.000/0.975/1.000/0.918/0`，通过全部专项门限。
- [x] 记录 YOLO+ByteTrack 的 `0.622/0.996（严格 0.966）/0.955/1.000/0.878/25`，
  P50/P95 约 `10.42/12.37 ms`；召回、侦察全覆盖和 IDSW 未过门限，保持 optional。
- [ ] 提升 YOLO 召回、降低 ByteTrack IDSW、恢复侦察全覆盖，并完成多 seed
  confirmation；单 seed 不允许作为默认主线晋级依据。

本专项门限为 detect/YOLO 召回分别 `>=0.95/>=0.90`、严格配准 `>=0.95`、
稳定配准 `>=0.90`、联合覆盖 `>=0.95`、侦察全覆盖 `>=0.90`、IDSW 分别
`<=0/<=5`，且 truth use/rewrite 均为 `0`。专项分支不替换默认 D1-D7 流程；
本轮只同步真实证据，不修改 D5 算法、默认 backend 或安全阈值。

本隔离专项未运行 D1/D2。main 使用 actor truth 运动学合成带中心
`global_track_id` 的 `GlobalTrack` fixture，truth 同时用于离线评分。
`online_truth_identity_use=0` 的边界仅覆盖 D5 的 local bbox 到 fixture
关联代价、Hungarian 选择和稳定窗口不读取 actor/object/truth identity；它不表示
整个专项完全不读取 truth。

## 2026-07-16 人工轨迹局部观测适配器（已完成）

- [x] 在离线 `manual_video_tracker` 子模块公开
  `manual_records_to_local_image_observations()`，参数固定包含 `sensor_id`、
  `stream_id`、`image_size`、`spectral_band="visible"`、`local_epoch=0`、
  `arrival_delay_s=0.0`、`confidence=1.0`。
- [x] measured 将 `xywh` 转为 `xyxy`，复用
  `adaptive_pixel_covariance_px()` 生成 `2x2` 像素协方差，保留双时间戳、
  camera-local ID、frame index、tracker/association backend 和逐 local ID
  连续 measured history；lost 不携带 stale center/bbox/covariance，confidence 固定为 0。
- [x] 转换前运行整批 identity audit；`duplicate_measurement_count > 0` 时拒绝转换，
  不输出部分结果。
- [x] 从包根移除 `manual_video_tracker` 强制导入；CLI/测试使用显式子模块导入，
  根包在 manual OpenCV/SciPy 依赖不可用时仍可导入。
- [x] 2026-07-16 复核既有 95 帧、5 local ID、475 条记录，转换结果为
  `470 measured / 5 lost`、重复量测 0。D5 全量 `288 passed`，接受阈值为零失败、
  lost 无 stale 量测且重复坍缩必须 fail closed。
- [ ] 保持该能力为人工初始化单相机离线支线；不接入默认 AirSim，不将 local ID
  提升为 `global_track_id`，不据此关闭通用 detector/MOT、多视角或物理闭环 GAP。

`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查：本任务没有 AirSim 输入、runtime episode、
默认 detector 或 handoff 接线变化，因此不修改该文件。

## 2026-07-15 人工初始化本地视频 MOT（已完成）

- [x] 新增首帧 `selectROIs` 和无界面 `--rois`，目标数量由输入决定，选择顺序固定为 `local-001...`。
- [x] 新增每目标独立 CSRT 默认路径和 KCF 可选路径；重复 tracker 框失败关闭，不把同一量测写给多个 ID。
- [x] 新增亮目标正对比峰 + 常速度预测 + Hungarian 一对一关联选项，用于 `b.mp4` 中五个相邻亮目标。
- [x] 输出 MP4、逐帧 CSV、JSON summary；lost 帧的 bbox/center 为 null/空，不沿用旧框伪造量测。
- [x] 2026-07-15 无界面运行 `b.mp4` 95 帧：五 ID 有效/丢失为 `92/3`、`95/0`、`93/2`、`95/0`、`95/0`；`duplicate_measurement_count=0`，最小中心间距 `5 px`，最大 bbox IoU `0.4118`。
- [x] 单元测试覆盖 ROI 解析/边界、ID 稳定、lost 语义、合成 MP4 和一对一亮点关联。
- [x] 2026-07-15 验证：D5 全量 `284 passed`，`py_compile` 和 owned-path `git diff --check` 通过，接受阈值为零失败。
- [ ] 后续仅在独立 benchmark 中增加人工重选事件日志、外观模板或通用检测器比较；不得把本工具的 local ID 直接注册为 GlobalTrack。

本工具是离线人工初始化 local MOT，不是敌我识别、GlobalTrack 注册、跨相机关联、D7 视觉 PNG 授权或 ByteTrack/BoT-SORT 准入证据。它不改变 AirSim detect-first 默认路径，因此 `docs/AIRSIM_INTEGRATION_PLAN.md` 已检查但无需修改。

## 2026-07-15 M5N2 20-case 复核与停止状态

- [x] 只读复核 baseline seed 001-010 与 `candidate_soft_prediction_trend_coast` seed 001-010；共 20 个真实 AirSim M5N2 case。TERM 生效前额外完成 `png_ttc_2v2_seed001`，但不进入 M5N2 统计；其余 tuned case 与 dropout case 均未执行。
- [x] 每场从最终 active-primary 合同动态确定第二 primary；19 场为 `INT-03`，candidate seed 002 为 `INT-02`，避免把 standby reserve 错计为第二 primary。
- [x] 确认 `3725/3725` 个 D5-available tick 具备第二 primary runtime record、decision state 和 live first-failure stage/reason；D5 warmup not-applicable 为 `80` tick。实际 execution artifact 为 `20/20` available，online identity/state truth use 为 `0/0`。
- [x] 输出实测漏斗：`locked/ambiguous/reacquire/hold=1721/795/1209/0`；bbox-stability/live-detection/visual-association/geometry/complete 为 `1283/1209/764/204/52`；measured bbox `2516`、bbox stable 与 handoff-ready 各 `161`。
- [x] 保留物理结果独立分母：第二 primary 5 m 为 `0/20`，最近物理距离 `8.843-14.740 m`；T001 coalition completion `0/20`。snapshot locked 或短时 consensus 不替代物理闭环。
- [x] 保留停控原因责任边界：20 个第二 primary 最终均记录为 `collision_stop`，但这只是 D7 停控证据；碰撞对象未持久化，不能把该状态或 `0/20` 单独归因于 D5。
- [ ] P1：由 main/D6 在后续报告接线中直接持久化 `failure_category` envelope。本批只有 `first_failure_stage/reason` available，不能声称真实分类字段已经验收。
- [ ] P1：继续校准第二 primary 当前 measured bbox 连续性、bbox 尺度、visual freshness、候选唯一性和几何搜索恢复；目标仍是提升 5 m 结果且不放宽 global-ID、friend、duplicate、版本和时间门控。
- [ ] P1：candidate 仅有 handoff-ready snapshot 比例上升，locked/freshness/consensus 与物理结果未一致改善；默认路径维持不变。candidate seed 002 发生 primary membership 变化，后续公平对照应冻结或显式分层成员合同。

本轮没有代码修改、没有运行 AirSim，也不把 truth ID 作为在线输入。

## 2026-07-15 第二 primary 被动诊断（代码级已完成）

- [x] 复用现有 `TerminalAssociation` 与 `d5_live_visual_funnel_v1`，在 `summarize_cooperative_visual_funnel()` 中增加逐资源 `failure_category`、全 active-primary 分类计数和第二 primary 分类计数，不新增重复 DTO。
- [x] 区分不可见、投影无效、几何门拒绝、bbox 不稳定/边缘裁切、候选不唯一、量测陈旧、计划/版本/全局 ID 合同不一致、友方/重复锁定冲突和稳定锁定未完成；冲突全局 ID 只作为合同错误证据，不换绑中心 ID。
- [x] 保持全部 locked/hold/reacquire 与身份安全门不变；2026-07-15 专项 11 case、D5 全量 `272 passed`，接受阈值为零失败。
- [ ] 由 main 在真实 AirSim 2v2/M5N2 至少 10 seeds 中持久化并聚合该分类，验收每个失败样本恰有一个分类、online truth use/global ID rewrite 为 0，并量化第二 primary 的主要断点。该项未由确定性测试关闭。

本批未启动 AirSim，也未调整 PNG、bbox、几何、唯一性、友方、版本或时效阈值。M5N2 第二 primary 5 m/联盟完成、真实几何 drift、detect/YOLO/MOT 和二级同 tick freshness 仍为 P1。

## 2026-07-14 actual-v2 真实 AirSim 证据同步

- [x] 只读同步两个真实 AirSim seed-1 case：tuned 2v2（8 s、`png_ttc`）与 M5N2（35 s、`png_vm`）；actual-execution canonical artifact 为 `2/2` available，在线 identity/state truth use 为 `0/0`。
- [x] 分层记录末端事实：canonical actual 五层均独立 available，contract/control/terminal-switch/mode/physical 总计 `102/26/26/2/4`。`terminal_switch_allowed_count` 从最终 `control_commands.csv` 独立统计，2v2/M5N2 为 `26/0`，不从 control 层推断；2v2 visual/mode switch 为 `2/2`，M5N2 为 `0/0`。
- [x] 保留物理结果的独立分母：M5N2 active pair `2/3`、target `2/2`、coalition `0/1`，T001 第二 primary 最近约 `11.02 m`。不得以 target 成功替代第二 primary 或联盟完成，也不得以 lock acquisition 替代视觉控制接管。
- [x] 保持 AirSim detect 默认在线路径、online truth use 为 0 和 center-owned `global_track_id` 只读合同；本任务不修改代码、算法、阈值或默认 backend。
- [ ] P1 继续完成 visual acquisition/registration/gate 分层闭环、第二 primary 5 m/联盟完成、30/50 m 召回、1-5 帧 dropout 与 YOLO/native-MOT 至少 10 seeds confirmation。M5N2 既有视觉完成门仍为至少 `8/10`，与 physical coalition `0/1` 分母独立；D6 本批 formal overall status=`fail`，不得因 actual artifact `2/2` available 提前关闭。

本节仅同步 2026-07-14 运行证据。来源为 `p0_actual_v2_validation_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md` 和 main actual-execution 报告；不新增 AirSim episode。

## 2026-07-14 postbatch live visual evidence 收尾

- [x] 审计最新 M5N2 baseline/candidate：相机作用域为各自 `InterceptorN:0`，没有跨资源串用或在线 truth；baseline/candidate 分别为 `330/311` 条控制记录、`151/120` 条几何 locked，两组均仅 INT-03 有 `40` 条控制 bbox 非零。
- [x] 扩展 truth-free DTO：`local_visual_evidence` 和 `d7_handoff_input` 携带 bbox、中心、资源、camera/stream/backend、双时间戳及 measured/stability 状态。
- [x] 分离 geometric association lock 与 execution lock：`execution_lock_allowed` 必须同时通过 own-camera measured bbox、scope、合同、稳定 lock、bbox 稳定/尺度及原有安全门；scope 冲突 fail closed 为 `hold`。
- [x] 新增 bbox 缺失、相机 scope 冲突、小稳定框和完整 handoff 回归；2026-07-14 `py_compile` 通过，D5 全量 `261 passed`，零失败为接受阈值。
- [ ] main 在真实 AirSim 至少 10 seeds 校准多相机持续 detection、进入 30 m 后的当前 bbox、`640x480` 小框尺度和异常大框来源；D5 不通过降低 bbox、identity、friend、duplicate、version 或 calibration 门获得通过率。

本批代码级 DTO/执行锁定语义 P1 已关闭。没有新增 AirSim 运行；真实终端可见性和多 seed 准入仍开放。

## 2026-07-14 semantics_v2 seed-1 live funnel 历史诊断

- [x] 逐资源复核最新 M5N2 baseline/candidate：INT-02 measured detection 为 `195/193`，raw visual lock 为 `140/142`，final execution lock 为 `18/18`，两组 T001 consensus 均为 `14`，稳定锁定最大连续计数均为 `17`。
- [x] 确认主要时序断点：execution gate 只在 `0.4-2.2 s` 通过；INT-02 bbox 到 `19.0/18.6 s` 才稳定，此时已由 `arrival_window_expired` fail closed。该结论不支持降低任何 D5 安全门限。
- [x] 增加 `d5_live_visual_funnel_v1`、连续 measured execution-lock streak、首断点/责任域和显式 `d7_handoff_input`；运行记录顶层提供 main/D6 可直接消费的字段。
- [x] 覆盖正常连续 lock、raw lock 被到达窗口阻断、M-to-N committed membership 缺失三类确定性回归；2026-07-14 D5 全量 `258 passed`，接受阈值为零失败。
- [x] postbatch 在 `arrival_coordination_required=false` 时不再生成共同到达窗口；D5 对显式协调场景仍只读并拒绝已过期合同。
- [x] postbatch 已确认 main 能把当前 D5 local track 送入 D7；其他资源控制 bbox 为零来自末端阶段缺少当前 measured detection，不再归类为相机串线或简单 DTO 丢失。顶部 DTO 补丁仍需由 main 在后续 AirSim rerun 验证。

该历史批次没有修改 lock、bbox、identity、friend、duplicate、timestamp、calibration、plan/version gate，也没有修改或换绑 `global_track_id`。顶部 postbatch 章节给出当前开放项。

## 2026-07-14 bbox 稳定历史/共同视觉证据 P1 闭合（已完成）

- [x] 审计 postfix seed-1 的 `bbox_stable=false` 与 T001 `13/347`、`12/347` 共同视觉证据，定位 D5 consumer 与 main producer 的字段断点。
- [x] 将 bbox/MOT/stable-lock 历史绑定到 resource-target-local track-camera-backend-stream 身份；仅 plan version 刷新且该身份及 committed/current coalition membership 未变时继承历史。
- [x] 对 membership、resource-target binding、local track、camera/backend/stream、identity/friend/duplicate 冲突变化执行 fail-closed reset，并输出 history length、CV、reset reason、key/signature 和 measured/predicted source 审计字段。
- [x] 共同视觉证据只采纳 committed/current coalition 成员；保持锁定门限、center-owned `global_track_id` 和 YOLO/MOT 准入状态不变。
- [x] 增加 D5 合同/回归测试并同步 README、PLAN、D5 GAP/review 及受影响的 D5 docs；2026-07-14 D5 全量 `255 passed`，接受阈值为零失败，owned-path `git diff --check` 通过。

只读基线为 postfix seed-1：M5N2 baseline/candidate 的 `bbox_stable=true` 均为 `0/1388`，T001 consensus 分别为 `13/347`、`12/347`；2v2 PNG/TTC 为 `0/52`。每条旧 runtime 记录的 `visible_frame_count <= 1`，原因是 main 每 tick 只把当前 `scoped_local_tracks` 交给 stateless handoff；T001 另有 `326/347` tick 的真实 primary membership 变化，必须继续阻断共同连续证据。本轮没有新增 AirSim 运行。

D5-owned 历史/合同 P1 已关闭。canonical actual 已消费 committed coalition、pre-decision duplicate hint 及 camera/stream/backend/local-track transition/MOT 字段，并独立持久化五层 metric envelope；不再把这部分列为 main 未接线。当前开放 P1 收敛为 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness。

## 2026-07-14 原生 MOT 历史累计 P1 子缺口闭合

- 已完成：为 Ultralytics ByteTrack/BoT-SORT 增加 `(resource_id, camera_id, backend, native id)` 作用域的连续实测命中历史，不再把 `Results.boxes.id` 每帧固定解释为 `mot_history_length=1`。
- 已完成：一次空帧即中断连续 measured history，恢复帧从 1 重计；状态只在 `max_track_age_frames` 内保留，长期复用 ID 不继承稳定证据。
- 已完成：`reset_stream()`、`reset_all_streams()`/`reset_episode()`、native model 失败重建以及 native/fallback backend 切换均清理对应错误历史；IoU fallback 与 native 历史相互隔离。
- 验证：2026-07-14 Results-like 确定性回归覆盖双 backend、连续帧、跨资源/相机、ID 切换、空帧/遮挡、两类 reset 和 native-fallback-native，D5 全量 `241 passed`，接受阈值为零失败。
- 保持开放：真实 AirSim/真实图像至少 10 seeds 的 detector precision/recall、IDSW/continuity、P95、bbox/时间对齐和 30/50 m 召回准入。该代码修复不晋级 ByteTrack/BoT-SORT，不改变 detect 默认路径，也不降低任何终端安全门控。

## 2026-07-14 D3 feedback 分级 P1 复核

本轮关闭 D5 输出语义混淆子缺口，未增加公共 API。`TerminalAssociation` 的 `decision_state/friend_conflict_state/duplicate_terminal_lock_risk` 与 `TerminalConsistencySummary` 的 `consistency_state/recommended_d4_action` 已足够表达分级：

- 普通 `ambiguous/hold/reacquire`、geometry gate、bbox/时序不稳定保持 pair 级视觉不确定性，只能 `unknown + observe/request_secondary_cue`；连续帧不会再被自动升级为 `conflict/arbitrate`，且没有 resource-unavailable 含义。
- verified friend、spoof suspected、duplicate lock、assignment 授权/版本和 local/global ID conflict 保持 fail closed，并输出 `conflict/inconsistent + report_conflict/arbitrate`，供 D3/main 选择 hard planner feedback。
- 未验证/过期身份和 unknown category 保持待确认，不推断 hostile；`global_track_id` 不改写，online truth use 为 0。

2026-07-14 专项 52 项和当时 D5 全量 235 项测试全部通过，门槛为 0 failure；本日后续原生 MOT 历史修复后最新全量为 `241 passed`。当前 P1 为 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness；P2 为 Deep SORT/ReID、真实身份 adapter 和完整在线 PnP，IBVS/ROS 2 保持 P3。本次没有新增 AirSim 物理证据，也不改变这些开放项。

## 2026-07-13 M5N2 与原生 MOT 实测状态

- M5N2 实测已形成 `120` 条 active-primary 证据，`visible=120`，其中 D5 关联/锁定证据为 `74`；最佳参数组合的 coalition completion 为 `5/10`，未达到 `8/10` 验收线。主要失败原因是 `d5_not_locked` 和 `terminal_detection_acquisition_timeout`，因此该系统级 P1 仍未闭合。
- `per_primary + arrival_coordination_required=false` 只解除同帧/同时到达要求，不解除 D3 plan/owner/version、D4 coalition commit、友方、duplicate、measured evidence 和 reserve standby 门控。实测中 `global_track_id` rewrite 为 `0`、online truth use 为 `0`，安全合同继续保持。
- 原生 MOT screening 使用 `1920x1080`、FOV `90`，覆盖距离 `20/30/50 m`、confidence `0.1/0.2/0.3` 和 ByteTrack/BoT-SORT，共 `18` 个 case。20 m 时两种后端的 native active rate/continuity 均为 `1.0`、IDSW 为 `0`，P95 约为 `7.4/16.2 ms`；但离线 precision/recall 仅约 `0.26-0.33`，30/50 m 均无检测。
- 原生 MOT screening 的准入候选数为 `0`，因此 two-camera confirmation 执行数为 `0`。不得把 20 m 的 tracker 连续性解释为 detector 或跨视角关联已达标，默认在线路径保持 AirSim `simGetDetections` 不变。
- 当前 D5 P1 收敛顺序为：第二 primary 稳定获取与锁定、YOLO/AirSim bbox 口径和尺度诊断、30/50 m 远距召回、候选配置多 seed 标定。任何调参都不得降低 identity、版本、唯一性、友方冲突和 `global_track_id` 不变式门控。
- 2026-07-13 当日 D5 全量回归为 `232 passed`；2026-07-14 原生 MOT 历史修复后最新全量回归为 `241 passed`。本文中的 `235 passed`、`229 passed`、`204 passed`、`200 passed` 及更早数字均为对应实现阶段的历史基线，不代表当前测试总数。

## 1. 范围与安全边界

D5 只面向科研仿真、离线回放和保守的终端视觉配准评估。模块不实现真实飞控、硬件驱动、火控参数、毁伤逻辑、自动处置流程，也不绕过人工或中心授权。

局部终端节点必须遵守一个硬约束：不得改写、重建或重新分配 `global_track_id`。D5 只能基于中心分配的 `assigned_global_track_id`，报告本地视觉轨迹是否与该全局航迹匹配。

### 1.13 2026-07-13 类别同义词与高分辨率推理配置

- 对象类别比较统一经过 D5 taxonomy：`uav/drone/intruder` 及常见分隔变体均按 `uav` 比较，避免 detector 的 `intruder` 与 GlobalTrack 的 `uav` 产生 16 分错误惩罚。
- 原 detector 标签同时写入 track/frame metadata；类别字段不产生 affiliation，友方、未知和可疑身份仍由 `IdentityClaim` 独立处理。
- `YoloMotAdapterConfig.inference_imgsz` 接受正整数或 `(height, width)`，原样传给 Ultralytics native track/predict；`None` 保持旧默认调用兼容。
- per-camera tracker、online truth 隔离和 center-owned `global_track_id` 合同不变。该实现阶段的历史回归基线为 `229 passed`；2026-07-13 当日全量为 `232 passed`，2026-07-14 最新全量为 `241 passed`。
- 下一步由 main/runtime 为主相机和高空侦察相机分别选择推理尺寸，运行真实 AirSim 多 seed，对显存、P95 延迟、20-50 m recall 和 fallback 进行标定；本次实现不关闭该系统级 P1。

### 1.11 2026-07-13 混合 1080p/4K 分辨率闭合

- AirSim 场景合同记录拦截相机 `1920x1080`、高空侦察相机 `3840x2160`；main 仍负责把这些参数写入真实 settings。
- `CameraModel` 和投影结果携带各相机 `image_size`，YOLO/MOT 从每帧数组读取尺寸，检测适配器把尺寸写入无 truth 的本地元数据。
- 以 `640x480` 为参考像素尺度缩放 friend/recon/reacquire/rate 固定像素项；马氏门仍由对应相机的 K、投影协方差和检测协方差决定。
- 二级 detect 自适应协方差的最小/最大 sigma 随分辨率缩放；完全无中心跨视角比较在计算中心差、协方差迹和 bbox 面积差前转换到参考像素尺度。
- 模块单测为 `204 passed`。该项关闭 D5 内部“所有相机默认同一像素尺度”的缺陷；目标 Actor 扩大和真实 AirSim 重跑由 main/runtime 执行。

### 1.12 2026-07-13 YOLO 与 AirSim detect 双路评价合同

- 在线顺序固定为 `YOLO/MOT process_frame(no truth) -> main 获取 simGetDetections -> monitor.observe(post-online truth)`；后到 reference 只作用于 evaluator state，不修改已生成的 result、local ID 或任何 `global_track_id` 绑定。
- 汇总显式区分在线 detector bbox、在线 local MOT track、离线参考框 matched/missed/unmatched-online，以及 native/fallback tracker 帧。拦截相机 `1920x1080`、侦察相机 `3840x2160` 的 `image_size` 均由 frame result 和 local track 独立携带。
- 保留 legacy inline offline-evaluation 兼容入口，但本轮真实 AirSim 双路模式必须使用 post-online monitor 路径；报告以 `post_online_truth_frame_count` 审计实际执行顺序。

### 1.9 2026-07-12 原生 MOT 准入与 per-primary 证据

- 新增 `NativeMotAdmissionMonitor`，按 resource/camera stream 汇总 native active frame rate、fallback frame count、accepted detections、warmup-excluded P95 latency、local continuity、terminal local IDSW 和 offline detector precision/recall。标准 sweep metadata 覆盖 confidence `0.1/0.2/0.3` 与目标距离 `20/30/50 m`。
- ByteTrack/BoT-SORT 只有实际原生 tracker 产生 local ID 时才计 native active；deterministic IoU fallback 是失败基线，不进入 native MOT 准入。默认准入还要求至少 100 帧、native active rate >= 0.95、fallback=0、continuity >= 0.90、IDSW <= 1、precision >= 0.90、recall >= 0.80、去预热 P95 <= 100 ms。
- truth bbox/identity 只在 online `YoloMotFrameResult` 形成后做离线 detector 与 local-ID scoring；summary 不输出 truth identity，tracker ID 仍只属于相机本地命名空间。
- 严格 runtime 顺序固定为 `process_frame(no truth) -> main 获取 offline truth -> NativeMotAdmissionMonitor.observe()`。frame result 只暴露不含身份的 detector bbox；public post-online evaluator 计算 TP/FP/FN、precision/recall 且不回写 result。legacy metadata 评分保留兼容，但 post-online truth 优先且同帧不双计数。
- 新增 `per_primary_terminal_evidence()`。`per_primary` 只取消“必须等待另一个 primary 同帧 locked”的 D5 证据依赖，不取消 plan/coalition version、active role、friend、duplicate、measured local track 和 execution gate。输出明确 `grants_control_authority=false`，最终控制仍由 D3/D4/D7 仲裁。
- D5 `Assignment`、registration `GlobalTrackBinding` 和 `TerminalAssociation` 已新增同名只读字段 `terminal_authorization_scope`、`arrival_coordination_required`。旧合同默认 `coalition + true`；main 复制 D3 显式 `per_primary + false` 后，字段通过 metadata/runtime record 原样下发。调用参数不能把 coalition association 临时改成 per-primary。
- D5 单元回归在该实现任务时为 `200 passed`；当时未启动真实 AirSim。2026-07-13 的最新实测见本计划顶部和 1.10 节：screening 已执行，但没有候选晋级，默认 detect 主线不变。

### 1.10 2026-07-13 真实 AirSim 原生 MOT 标定状态与后续计划

本轮严格 screening 已完成 `18` 个 AirSim case，参数为 `1920x1080`、FOV `90`、距离 `20/30/50 m`、confidence `0.1/0.2/0.3`、ByteTrack/BoT-SORT。20 m 已关闭“原生 tracker 无法连续运行或延迟超预算”的子问题：两种后端 native active rate/continuity 均为 `1.0`，IDSW 为 `0`，P95 约为 ByteTrack `7.4 ms`、BoT-SORT `16.2 ms`。但 precision/recall 只有约 `0.26-0.33`，30/50 m 均无检测；`native_mot_admitted=false`、候选数 `0`、confirmation 数 `0` 均为正确结果，默认 detect 主线不变。

剩余 P1 分为三个可证伪假设：远距模型尺度/渲染域上限、YOLO 与 AirSim bbox 定义差异、在线结果与后到 truth bbox 的时序偏差。不能通过直接下调 IoU、confidence 或 D5 在线安全门限得出准入结论；应先保存并对齐逐帧在线 bbox、离线 reference bbox、时间戳、目标像素尺度和零检测原因。

下一轮标定矩阵：

| 维度 | 取值 | 必记证据 |
|---|---|---|
| 距离/尺度 | `20/25/30/40/50 m` | YOLO bbox 宽高/面积、置信度、目标是否在图、AirSim bbox 是否返回 |
| detector confidence | 主网格 `0.1/0.2/0.3`，诊断点 `0.05` | raw/accepted detection、precision/recall 与零检测原因 |
| tracker | ByteTrack、BoT-SORT | native active、fallback、continuity、local IDSW、去预热 P95 |
| bbox 评分 | IoU `0.1-0.5`，中心归一化误差、宽高/面积比、containment | 区分框定义差异与真正误检 |
| 时间对齐 | same frame、`-1/0/+1` frame | truth RPC timestamp、缺框/异常原因、最佳对齐偏移 |
| 重复性 | 候选配置至少 10 seeds、每组 >=100 帧 | 分 seed 指标、均值/区间、失败原因分布 |

验收保持分层。runtime 层要求 native rate >=0.95、fallback=0、continuity >=0.90、IDSW <=1/episode、P95 <=100 ms；评分可用性要求 truth 帧覆盖率 >=0.99 且未评分帧均有原因；检测层在已验证的 bbox 定义下要求 20 m precision >=0.90、recall >=0.80。30/50 m 必须先取得非零稳定检测后才可谈准入。任何离线 IoU 口径调整都不得传播到 D5 在线马氏门、唯一性/友方/版本/duplicate/authorization gate，也不得让 truth 进入在线 local track 或 `global_track_id` binding。

### 1.1 2026-07-11 实施前状态基线

以下内容只保留 `research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_liveness_batch_20260711/M_TO_N_AIRSIM_CONVERGENCE_REPORT_CN.md` 的实施前历史基线。ComputerVision 模式只验证状态机与导引合同，不执行 SimpleFlight 动力学控制，因此下列结果不能解释为当前状态、物理拦截或命中：

- seeds 7/17/27 均为 6 次重规划请求、6 次 `no-change` 确认、0 次应用、0 次过期；需求满足率为 1.0，错误重复锁定为 0。
- 普通目标 T002 的视觉共识帧为 4/5/4，D7 每个 seed 获得 2 次终端合同许可，说明 D3-D4-D5-D7 的单 primary 状态链可重复闭合。
- 高威胁目标 T001 的双 active-primary 视觉共识在三个 seed 中均为 0。D5 的 M-to-N DTO、快照作用域、合法协同锁和两帧稳定汇总接口已完成，但共同可见和连续锁定的真实 AirSim P1 验收尚未完成。
- D5 当时回归基线为 `152 passed`。P0 无 blocker，truth ID 在线隔离、保守决策和 `global_track_id` 不变式继续作为强制回归项。

### 1.2 2026-07-11 验收历史状态（已由 1.6 节更新）

当时的证据为 `research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`。P1 合同层已经闭合：ComputerVision 10 seeds 的 T001 双 active-primary 当前计划授权与视觉共识为 `8/10`；10/10 的错误 duplicate 为 0，计划内合法协同多锁与错误重复锁已分离。commit-aware gate 的二级接管、完全分布式完整 ACK 正例均通过，缺 ACK 场景保守阻断 consensus/visual PNG authority 并 fail closed。

P1 物理/长期标定仍开放，而不是 D5 合同 DTO 未完成。ComputerVision 的 `control_allowed_count=0`；SimpleFlight 15 s 仅为诊断，30 个 active pair 均未命中，其中 24 个触发 `terminal_detection_timeout`。后续 P1 应定位持续 detection、D5 lock、D7 control gate 和闭合速度各层断点，并用长时真实多 seed 物理验收，不得把 `8/10` 合同验收写成控制切换或拦截成功。

能力层级仍需分开：`YoloMotAdapter` 是图像/MOT adapter，6 episode x 2 帧只算 smoke 且 accepted detection 为 0；IoU fallback 只提供确定性本地连续性；`TerminalCrossViewFusion` 仍是 metadata-only 研究近似，不是三维重投影、三角化或 bundle adjustment。它们均未替换默认在线关联路径。

P2 optional benchmark 已完成到隔离式离线合成对照：`p2_geometry_benchmark.py`/CLI 执行 OpenCV calibration/`solvePnP`，默认样本将后投影 RMSE 从约 24.0 px 降至 1.63 px，PnP 重投影 RMSE 约 0.43 px。它不进入在线 D5 默认路径，不写回 `CameraModel`，也不替代真实相机标定、PnP RANSAC、AirSim 外参漂移或硬件验收；默认在线路径仍是中心航迹投影、像素马氏门控、本地视觉轨迹和保守关联，未被 P2 替换。

### 1.3 本轮 detect-first / truth-isolated P1

- 在线探测保持 `simGetDetections` bbox，association source 为 `geometric_detect`；AirSim actor/object/truth/global 字段不参与 local ID、category、cost 或 binding，`truth_identity_used` 固定为 `false`。
- `LocalVisualTrack.local_track_state` 显式支持 `measured/predicted/lost`。predicted 只作为匿名 camera-local `reacquire` 证据，不计入几何 assignment 或稳定帧，不得输出 `locked/registered`。
- detection 暂失后，即使 MOT local ID 未变化，也必须重新通过几何门限并积累 measured stable frames；predicted 帧会打断稳定窗口。任何重捕只继续核对上游现有 `assigned_global_track_id`。
- `TerminalAssociation`/`TerminalObservation` 强类型保留 measurement/arrival 双时间戳、measurement/prediction age、local state、association confidence/reason，并通过 `to_runtime_record()`/`runtime_records()` 供 main/D6 直接消费。
- 本轮模块回归为 `157 passed`。P2 YOLO/ByteTrack 数据集标定保持 deferred；已有 OpenCV geometry benchmark 仅复核隔离状态，不接入默认在线路径。

### 1.4 2026-07-12 真实 AirSim 2v2 pilot 复核

证据 `research_modules/airsim_runtime/outputs/p1_5m_2v2_pilot_fix2_20260712/episode_006_full_flow` 共 96 条 D5 association：36 `locked`、48 `ambiguous`、12 `reacquire`。离线 truth 仅用于事后审计，36 个 lock 全部命中各自真实目标；ambiguous 中 37 个最佳候选为真实目标、10 个为本机拦截机、1 个为另一目标，均未被错误升级为 lock。ambiguous 原因为 37 次 `insufficient_best_second_margin`、9 次 `best_cost_exceeds_lock_threshold` 和 2 次首帧 `mot_history_too_short`；无 friend/duplicate 硬冲突。当前 `min_lock_margin=3.0`、`max_lock_cost=14.0` 和 3 帧窗口至少 2 次 measured 支持不应因单轮 pilot 放宽。

12 个 reacquire 均为分配航迹预测投影 `outside_image/behind_camera`，输出 `association_source=geometric_detect`、`truth_identity_used=false`、匿名上一 local ID、最后 measurement timestamp 和 `prediction_age_s=0.1-0.7 s`，属于可供 D4/D7 grace 的丢检/出视场证据，不是本地换绑或硬冲突。复核发现 handoff 注释在 `local_track_id=None` 时曾借用同相机其他检测的 timestamp/LOS/bbox，使 2.2 s 帧的真实 prediction age 0.6 s 被覆盖为 measurement age 0.0。现已修复为只沿用当前 association 的 measurement/prediction age，并在无 local ID 时禁止借用其他轨迹的 LOS/bbox。建议 D4/D7 短时 grace 先与 D5 `max_measurement_age_s=0.35 s` 对齐，即 10 Hz 下约 3 帧；超过该值继续 radar PN/fail closed，不把 0.6-0.7 s lost 证据当作新鲜视觉测量。

### 1.5 2026-07-12 D7 视觉证据合同补齐

D5 已完成 truth-free 视觉证据 DTO 与 adapter 接线：`CameraGeometryEvidence` 强类型携带 K、camera-to-NED rotation/position、measurement/arrival timestamp、attitude timestamp/age/validity；`LocalVisualTrack` 携带稳定 local ID、MOT history、迁移/reset、detect source 和 bbox edge clipping。关联输出/runtime record 原样透传这些证据，并保留 friend/duplicate/locked-hold-reacquire 门控。缺失几何明确为 unavailable，MOT coast 不产生授权。模块回归为 `161 passed`。

后续由 main/runtime 接入真实 AirSim 曝光时间、camera pose 与同步机体姿态；D7 在这些字段完整前只能使用现有 2D 图像证据，6D LOS 保持 replay-only/unavailable。D5 不实现导引 KF、TTC 或 LOS 滤波。

### 1.6 2026-07-12 commit 33e6fa0 后历史状态同步

本节保留 commit `33e6fa0` 时的 P0/P1 历史状态，依据当时的 D5 代码与测试、`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md` 和 `research_modules/airsim_runtime/outputs/PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md`。当前结论以本文顶部 2026-07-13 实测状态为准。

| 优先级/能力 | 当前状态 | 2026-07-12 证据与边界 | 下一验收条件 |
| --- | --- | --- | --- |
| P0 安全合同 | 已闭合，保持原状态。 | 在线 truth/actor ID 隔离、相机作用域 local ID、friend/duplicate 保守门控、predicted/lost 禁止授权和 `global_track_id` 不变式均由 161 项模块测试保持；PNG delivery 报告的在线 truth 使用为 0。 | 持续运行 D5 全量测试；任何 truth/local ID 参与 binding、predicted 升级为 lock 或全局 ID 改写均重开 P0。 |
| P1 truth-free 视觉证据 schema | D5 侧已闭合，保持原状态。 | `CameraGeometryEvidence`、双时间戳/曝光时间、local-track transition/reset、MOT history、bbox clipping、相机 K/外参/姿态有效性已由 adapter、association 和 runtime record 透传。 | main/runtime 继续提供真实曝光时刻、camera pose、安装外参和同步姿态，并按相机/seed 校准时延与误差；缺字段时保持 unavailable。 |
| P1 2v2 主线非退化 | 系统级验收已通过，不新增 D5 算法完成项。 | candidate 10 seeds 为 20/20 pair 在 5 m 内成功，旧基线为 19/20，在线 truth=0，平均最小距离 4.844 m；自然运行没有触发 soft prediction/trend coast，因此不能把提升归因于 D5 或新增外推。 | 保持 D5 wrong binding/ID rewrite 为 0，并在同场景继续记录 D5 lock/hold/reacquire、D7 gate 和物理结果分层。 |
| P1 锁定后短时丢检 | 两帧真实链路已验证，长窗口仍开放。 | 锁定后 1.5-1.7 s 两帧 dropout 由 D7 在原 global/local track 与计划上下文内有界预测并达到 2/2 物理成功；D5 只提供身份/时序证据，不实现 coast 或控制。 | 跑 1-5 帧固定时刻矩阵；超过 0.25 s 必须 fail closed，重捕后需重新通过 D5 measured geometry gate 与稳定窗口，错误绑定为 0。 |
| P1 M5N2 视觉/联盟鲁棒性 | 开放。 | 2026-07-13 已取得 120 条 active-primary/visible 证据和 74 条 D5 关联/锁定证据；最佳 coalition completion 为 5/10，`global_track_id` rewrite 与 online truth use 均为 0。 | 优先提升第二 primary 的持续检测、稳定 bbox 和连续 measured lock；保持 plan/owner/version、friend/duplicate 和 reserve standby 门控，目标仍为至少 8/10。 |
| P1 真实几何/时间同步标定 | 部分实现，开放。 | DTO/日志字段和 unavailable 语义已闭合；真实 per-camera K/R/t/dist、曝光/arrival/attitude 同步误差、漂移恢复和 PnP RANSAC 尚未形成多 seed 验收。 | 固定相机与姿态来源，注入/采集漂移和延迟，报告重投影误差、门控拒绝、误锁、恢复时间及 unavailable 比例。 |
| P1 YOLO/native MOT、二级覆盖、D4 逐决策 evidence、真实友方 replay | 部分实测，继续开放。 | 原生 MOT 已完成 18-case screening；20 m tracker 连续性和延迟达标，但 precision/recall 仅约 0.26-0.33，30/50 m 无检测，0 候选进入 confirmation。二级覆盖和真实身份源状态不变。 | 先校正 bbox 口径/尺度/时间对齐和远距召回，再对候选做多 seed confirmation；同时保持二级完整覆盖、同 tick freshness/threshold version 和真实身份 replay 的既有验收条件。 |

### 1.7 P1 M5N2 双 primary 诊断接口（2026-07-12 已实现）

新增 `CooperativeResourceTargetDiagnostic`、`CooperativeTargetVisualFunnel`、`CooperativeVisualFunnelSummary` 和纯函数 `summarize_cooperative_visual_funnel()`。接口按现有 `global_track_id` 分组，逐资源输出 visible、projected、gate accepted、locked、稳定帧、共同窗口参与、置信度、歧义和拒绝原因；逐目标输出动态 active-primary 漏斗、最长共同锁定窗口、协同完成状态及第二 primary 的首个失败阶段。

完成判据保持 fail closed：只计算当前 plan/coalition 双版本匹配、已授权激活且在 committed coalition 中的 primary；D4 fallback commit 需要 epoch/lease/required member/ACK 全部有效；standby reserve 不计 active-primary completion。在线输出不读取或传播 actor/object/truth ID，也不创建或换绑 `global_track_id`。专项测试覆盖不同视场、共同窗口不足、版本不一致、友方冲突、稳定正例、动态资源/目标和缺 ACK，D5 全量基线更新为 `181 passed`。

main/D6 已将该 summary 接入 M5N2 paired AirSim episode，并形成 `assigned -> visible -> projected -> gate -> locked -> stable -> common window -> physical intercept` 漏斗。最新结果为 120 条 active-primary/visible 证据、74 条 D5 关联/锁定证据和最佳 coalition completion 5/10；D5 仍不修改 runtime、D7 控制和 PNG 公式。

### 1.8 pose-fix smoke 根因与共同窗口修正（2026-07-12）

已只读复核四组 `p1_cooperative_closure_v2_posefix_smoke_20260712_*`。T001 的 primary 成员集合频繁变化；`h020/w05/s040` 是当前单 seed 中视觉证据最充分的一组，但 183 帧仍只有 25 帧双 current lock、18 帧双稳定 lock。主要首断点是 best/second candidate margin 不足和视觉证据过期，另有 arrival window、outside-image/behind-camera。强类型 `camera_geometry` 在这些 runtime record 中全部 unavailable，尽管 candidate pair log 已携带投影和门控结果；main 后续需修复真实 K/R/t/姿态证据透传，D5 不允许用 truth pose 回填。

D5 已修复 cooperative funnel 的共同窗口跨版本不一致：共同窗口只使用 `stable_lock_frame_count` 已认可的 source plan versions、immutable historical binding 和当前连续尾段。合法单调升版且 primary 集合不变时可形成跨版本共同窗口；成员变化或任何安全冲突仍重新计数。`CoalitionVisualSummary.metadata` 新增逐 primary 首断点和相邻计划成员变化，cooperative summary 按 `global_track_id` 输出成员变化映射。新增测试覆盖安全跨版本正例、primary 换员阻断和真实 runtime 风格的 margin/expiry 失败。2026-07-13 重跑后的最佳 coalition completion 为 5/10，下一步针对第二 primary 的 `d5_not_locked` 和 detection acquisition timeout 做多 seed 标定，而不是降低视觉门限。

## 2. 核心工程问题与科学问题

工程问题：末端相机视场内可能同时出现分配目标、非分配目标、友方资源和未知飞行物。相机最近目标不一定是中心分配目标，本地 MOT 的 `local_track_id` 也不能替代全局身份。D5 需要在这些干扰下输出可解释、可审计的 `locked/ambiguous/hold/reacquire` 决策。

科学问题：如何融合中心航迹预测、像素协方差传播、几何门控、局部 MOT 稳定性、合作身份声明和二级侦察 cue，在不引入虚假确定性的前提下降低终端 ID switch 和错误绑定。

## 3. 输入输出

输入：

- `Assignment`：来自 D3/D4，包含 `assigned_global_track_id`、版本、授权状态和资源 ID。
- `GlobalTrack[]`：来自 D2，包含位置、速度、协方差、类别、时间戳和 `global_track_id`。
- `LocalVisualTrack[]`：来自本地检测/MOT，包含像素中心、bbox、角速率、质量、本地轨迹历史、`local_track_state` 和可选 `prediction_age_s`。
- `IdentityClaim[]`：来自仿真的 Remote ID、MAVLink 签名、DDS Security 或 AprilTag 等合作身份声明。
- `CameraModel`：相机内参、外参、图像尺寸和测量协方差。
- `ReconImageCue[]`：来自 D4 二级可机动高空侦察节点的局部图像 cue；高性能光电云台按 GlobalTrack/radar cue 指向目标簇，并可额外携带 `cue_position_ned`、`look_at_ned`、`gimbal_pointing_metadata`、`cue_pointing_error_m/rad`、`gimbal_track_error_px`、`cue_source`、`capability_class` 和 `coverage_mode`。

完全分布式跨视场输入：

- `resource_id/camera_id/frame_id`：给每个本地视觉轨迹建立唯一观测命名空间，避免不同无人机都使用 `track_1` 时发生冲突。
- `PeerCameraState`：记录每个 peer 相机在量测时刻的姿态协方差和可选位姿元数据。
- `measurement_timestamp/arrival_timestamp`：区分图像形成时刻和数据到达时刻，便于跨视场时间对齐。
- `covariance` 或 `covariance_px`：描述本地像素检测的不确定性，不把框中心当作确定值。
- `DistributedVisualObservation`：把上述字段和本地 `local_track_id`、bearing、bbox、类别、置信度封装为跨 peer 视觉观测。
- `VisualTrackletSummary`：按 `resource/camera:local_track_id` 汇总观测窗口，保留 bbox 面积、scale rate、bearing rate 和可选 `assigned_global_track_id` 状态。

输出：

- `TerminalAssociation`：包含中心分配 ID、本地候选 ID、置信度、歧义度、友方冲突状态、决策状态、候选代价、cue 使用标记，以及 detect-first source、双时间戳、age、local state 和 `truth_identity_used=false`。
- `CrossPeerAssociationHypothesis`：完全分布式模式下的跨 peer metadata-only 视觉假设，不创建全局 ID。
- `DistributedTerminalAssociation`：供 D4 完全分布式决策消费的保守摘要；missing/stale global ID、重复锁定、友方冲突或局部 ID 冲突时不得输出 `locked`。

## 4. 简化数学模型

### 4.1 时间预测

用常速度模型把中心航迹预测到图像帧时间：

```text
dt = t_image - t_track
p(t_image) = p(t_track) + v * dt
Sigma_p(t_image) = Sigma_p(t_track) + Q(dt)
```

该预测只用于终端投影对齐，不替代 D2 的航迹滤波器。

### 4.2 相机投影

使用针孔模型：

```text
P_c = R * P_w + t
u = fx * X_c / Z_c + cx
v = fy * Y_c / Z_c + cy
```

`Z_c <= 0` 或投影落出图像范围时，当前帧不可配准，输出 `reacquire`。

### 4.3 像素协方差传播

将世界坐标协方差传播到像素平面：

```text
J = d(project(P_w)) / d(P_w)
Sigma_px = J * Sigma_w * J^T + Sigma_measurement
```

用二维马氏距离进行几何门控：

```text
d2 = (z - p)^T * Sigma_px^-1 * (z - p)
```

默认门限采用 `gate_chi2 = 9.21`。

### 4.4 综合代价

候选代价：

```text
C = C_geo + C_rate + C_category + C_quality + C_friend + C_recon
```

其中 `C_recon` 只作为二级侦察 cue 的辅助负代价，不能越过授权、版本和友方冲突规则。

## 5. 算法选型理由

默认采用“中心航迹投影 + 像素马氏门控 + 本地 MOT 候选排序”的路线，原因是：

- 可解释：每个候选都有投影误差、角速率、类别、质量和身份冲突分项。
- 保守：没有候选过门限时不会强行匹配。
- 可集成：D2/D3/D4 已提供全局航迹、分配版本和降级计划。
- 可评估：D6 可以直接统计错误 `locked`、歧义事件、友方 `hold` 和 cue 使用次数。

ByteTrack、BoT-SORT、Deep SORT 只作为本地 MOT 输入来源。它们输出的 `local_track_id` 不能替代 `global_track_id`。

### 5.1 当前代码与测试状态

本节按当前 `src/d5_terminal_association/` 和 `tests/` 状态记录能力边界，避免把计划项写成已接入工程栈。

已实现并有测试或代码支撑的能力：

- `GlobalTrack -> CameraModel -> image projection`：`GlobalTrack` 是 frozen dataclass，`geometry.py` 和 `airsim_geometry.py` 支持投影、协方差传播、马氏门控和 AirSim camera info 到 D5 `CameraModel` 的离线转换。OpenCV 可用时使用 `cv2.projectPoints`；不可用时退回针孔模型。`TerminalAssociator.decide()` 和 `GeometricAssociationResult.to_log_records()` 已提供 projected pixel、bbox center、pixel error/reprojection error、Mahalanobis、gate pass、friend conflict、measurement age、selected pair、camera pose source、calibration health、drift warning 和 duplicate-risk advisory 字段，供 main/D6 后续写盘。
- `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、`ReconImageCue`：核心 DTO 已落地。`TerminalAssociator.decide()` 只核对 `Assignment.assigned_global_track_id`，输出 `locked/ambiguous/hold/reacquire`，不会选择另一个全局 ID 作为新分配。
- 保守 `decision_state`：未授权、版本不一致、已验证友方重叠时 `hold`；候选接近、质量不足或身份声明不可靠时 `ambiguous`；无有效投影或无门内候选时 `reacquire`；只有唯一、稳定、版本一致且无友方冲突时才 `locked`。
- P0-B 主动重捕获与时序一致性：`TerminalAssociator` 已保留 per `resource_id + assigned_global_track_id` 历史，正常 gate 失败时用 GlobalTrack 预测投影、上次 bbox/MOT 历史和 search window 主动寻找同一 assigned track；predicted 只输出 `reacquire` 且打断稳定窗口，恢复时无论 MOT ID 是否变化都必须重新通过 measured geometry gate 和 stable window，candidate margin、stale/OOSM、friend conflict、assignment/version mismatch 仍保持保守 `ambiguous/hold`。
- AirSim truth ID 隔离：`local_visual_tracks_from_sim_detections()`、`local_visual_tracks_from_offline_yolo_bytetrack()` 和 `YoloMotAdapter.process_frame()` 明确忽略 `object_id`、`actor_name`、`truth_id`、`true_global_track_id`、`global_track_id` 等真值/全局字段；若 AirSim `track_id`/`detection_id` 与 actor/truth 字段相同，sim detection adapter 会将其视为 truth alias 并回退到相机作用域本地检测 ID。truth label 只可在 `TerminalObservation.metadata` 或离线 evaluator 中用于 `terminal_lock_accuracy`、`locked_mismatch` 等评分。
- 跨视角 distributed visual association DTO 与 fusion：`DistributedVisualObservation`、`VisualTrackletSummary`、`PeerCameraState`、`CrossPeerAssociationHypothesis`、`DistributedTerminalAssociation` 和 `TerminalCrossViewFusion` 已实现 P0 metadata-only 融合。融合基于 measurement/arrival timestamp、bearing 或像素中心、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和姿态协方差做 gating/cost；SciPy 可用时用 Hungarian，缺失时退回纯 Python 唯一匹配。
- 完全无中心下多相机 peer evidence 输出：缺失或 stale `assigned_global_track_id` 时输出 `hypothesis_only/hold`，重复锁定、友方冲突或 local/global ID 冲突时输出 `hold/ambiguous` 风险证据；不会创建新 `global_track_id`。
- D7 视觉 PNG 前置证据：`annotate_visual_png_handoff()` 已在 `TerminalAssociation.metadata` 上附加 bbox 面积稳定性、距离区间、TGO、延迟、measurement age、LOS rate、friend/duplicate 风险和机动裕度建议。该建议只给 D7/main 做 gate 输入，不决定导引律。
- D4/D6 一致性摘要：`TerminalConsistencyTracker` 已按 `resource_id + assigned_global_track_id` 维护连续窗口；`assignment_version` 只随摘要审计输出，不作为窗口 key。因此同一资源持续执行同一全局目标时，D3 plan version 滚动更新不会清空连续 `locked/ambiguous/hold/reacquire` 状态。该摘要只作为 advisory evidence，不触发降级、不生成分配计划、不改写 `global_track_id`。
- 二级视觉覆盖与 detect 漏斗诊断：`summarize_secondary_visual_coverage_funnel()` 接受普通 replay frame dict/dataclass、`TerminalObservation` 和 `CrossViewAssociation`，输出单二级相机 full-view 率、二级网络联合 full-view 率、每相机/网络每帧可见目标数、覆盖比例均值/最小值，以及 detect -> local/recon cue -> terminal association -> cross-view association -> multi-support 计数。offline target label 只用于“看见目标”覆盖统计，不进入在线绑定。
- Detect-to-global-track registration：`register_local_visual_tracks_to_global_tracks()` 接受 `GlobalTrack[]`、D2/D3 binding/`Assignment`、每相机 `CameraModel(K/R/t)`、timestamp、协方差和 `LocalVisualTrack[]`，输出 registration candidates、registered observations、即时 cross-view support 和稳定 `stable_cross_view_associations`。truth/actor ID 和 tracker ID 不参与在线绑定。
- P0-B calibration health：`TerminalAssociation.metadata`、`TerminalConsistencySummary.to_metadata()`、registration candidate、registration observation 和 registration result summary 已输出 `projection_valid`、`reprojection_error`/`reprojection_error_px`、`camera_pose_source`、`camera_pose_source_trusted`、`calibration_health`、`calibration_health_reason`、`drift_warning`、health/source counts 和重投影误差摘要。P0-B 只做健康监测和告警，不做在线标定或外参重估。
- P1 二级 detect 注册校准：candidate/observation metadata 已补齐 `pixel_error_px`、`reprojection_error`、`mahalanobis_d2`、`gate_pass`、`projection_valid`、`camera_pose_source`、`calibration_health`、`drift_warning`、`bbox_area_px` 和仅离线评分用的 `offline_truth_global_id`。`camera_pose_source` 只从 batch metadata 标注 `airsim_camera_pose`、`runtime_guidance_pose` 或 `look_at_fallback`，D5 不调用 AirSim。
- P1 自适应像素协方差：`adaptive_pixel_covariance_px()` 按 `sigma_px = clamp(max(25, 0.5*sqrt(bbox_area_px), 0.008*image_diag_px), 25, 90)` 生成二级相机 bbox 观测协方差；有 bbox 面积时用于几何门控，无面积时保留 `batch.covariance_px` fallback。
- P1 多帧稳定注册：默认 `RegistrationStabilityConfig(window_frames=3, required_gate_passes=2)`。单帧 gate pass 只形成 candidate；近 3 帧内同一 `resource/camera/local_track/global_track` 至少 2 次通过才标记 `stable_cross_view_support=True`，否则 reason 记为 `stability_window_failed`。该逻辑只增加既有 `global_track_id` 的视觉支持，不创建、不改写、不换绑 ID。
- 机动高空侦察云台覆盖证据：`ReconImageCue`、`TerminalObservationBus.cross_view_associations()` 和 `summarize_secondary_visual_coverage_funnel()` 已支持 `fixed_downlook_secondary` 与 `mobile_recon_gimbal` 分层。移动侦察节点可记录雷达/GlobalTrack cue 到云台 look-at 的 NED 位置、pointing error 和像素 track error；coverage funnel 会标出固定俯视未 full-view、移动云台补足网络联合覆盖的帧和新增目标集合。

2026-07-08 AirSim D4/D5 视觉校准历史状态：

- `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 现在只作为历史 stress 证据：旧批次覆盖 3 个 seed、5v5 D4/D5 stress、200 m 高差、80 deg FOV、1920x1080，证明 D5 已能识别 `mobile_recon_gimbal`、`radar_global_track_cue`、`mobile_high_recon` 和云台指向 metadata。该批次的 bbox 3326-3334 px^2 对固定俯视约 1144-1145 px^2 只能说明目标看清能力改善，不能作为当前闭环结论；其覆盖与降级注册仍未闭合。
- 当时最新的 registration calibration v2 输出为 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`，单 seed、3 个机动高空二级节点、200 m、110 deg、1920x1080。
- v2 结果：`projection_valid_rate=1.0`，`geometry_gate_pass_rate≈0.474`，三个 case 的 stable cross-view registration 为 51/55/53，cross-view association 为 4/4/5，`degrade_to_secondary` / `degrade_to_distributed` 的 not-registered case 仍为 35/35，full-view mean≈0.048，coverage mean≈0.771。
- 该单 seed 结果只保留为历史基线；其中降级 case not-registered 35/35 已被 2026-07-10 的 60-case sweep 改写，不能继续作为当前状态。

2026-07-08 P1 calibration sweep 集成状态：

- main runtime 已新增 P1 D4/D5 calibration sweep，用于扫描二级高度、FOV、二级节点数量和 standoff 组合，并在每个组合内运行多 seed stress episode。
- main runtime 的 D4/D5 stress 链路已可把二级 detect-to-global-track registration 输出写入同一个 `TerminalObservationBus`，用于统计 `registered_to_global_track`、`geometry_gate_rejected`、`secondary_detect_available_but_not_registered`、cross-view support 和 coverage funnel。
- D6 标准报告 bundle 已由 main runtime 自动生成，输出 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。
- 因此 D5 当前 P1 重点不再是“是否有 registration/helper/report 接口”，而是通过真实 AirSim 多 seed sweep 校准二级网络覆盖、注册门限、YOLO/MOT 阈值、外参误差和 D4/D7 消费口径。

2026-07-10 真实 AirSim 60-case registration 状态：

- 证据目录为 `research_modules/airsim_runtime/outputs/p1_gap_closure_calibration_20260710`：5v5、10 seeds、50/200 m 二级高度、3 类 case，共 60 个 case。
- 60 个 case 均已形成有效 registration 记录；D6 的 `not_registered_count=0`，sweep 的 `secondary_detect_available_but_not_registered` 均值/最大值均为 0。平均 `projection_valid_rate=1.0`、`stable_cross_view_registration_count=92.233`、`cross_view_association_count=4.417`。
- 该结果关闭“detect 无法注册到既有 `global_track_id`”这一接口缺口，但不等于二级节点已具备完整接管态势：网络同帧全目标覆盖率均值仅 `0.0231`，平均覆盖率 `0.7059`，稳定窗口失败仍是主要 reject reason。D5 不因注册成功而放宽唯一性、友方冲突、版本、时效或 D7 独立安全门控。

2026-07-11 AirSim YOLO/MOT 冒烟状态：

- `p1_yolov8_bytetrack_smoke_fixed_20260711` 已完成 6 个 reset-separated episode、每个 2 帧；RGB 解码、YOLOv8/ByteTrack 调用、per-stream tracker state、在线 truth 隔离、offline bbox-only 评分和 runtime event 均能执行。
- 当前相机/actor 几何下 `accepted_detection_count=0`，AirSim offline truth box 多数也为 0，无法据此计算有效 detector recall 或 MOT continuity。原生 ByteTrack 因没有 track ID 退回 `iou_fallback`；观测延时多数约 38-49 ms，首轮约 197 ms。
- 三组既有 D4/D5 回归均有 `cross_view_association_count=4`，稳定注册约 19-61，但二级同帧全目标覆盖仍不足。后续不得用局部 cross-view count 替代完整网络覆盖指标。
- 因此计划状态为“接口闭合、检测/MOT 质量未闭合”。下一轮先让 AirSim offline truth bbox 对有效视场提供非零标签，再校准 YOLO 类别映射、阈值、目标像素尺度和相机指向；只有 accepted detection 非零且原生 tracker 产生稳定 ID 后，才进入多 seed IDSW/IDF1、遮挡恢复和预算验收。

部分实现或仅作为 adapter/抽象的能力：

- 真实工程几何配准：当前消费已有 `CameraModel.K/R/t/dist_coeffs`，并能离线验证投影误差；P2 已有合成 `calibrateCamera`/`solvePnP` 扰动 benchmark，但没有真实标定采集、PnP RANSAC、bundle adjustment 或在线外参漂移估计链路。
- YOLOv8/ByteTrack/BoT-SORT：已提供 `YoloMotAdapter` 图像帧入口，默认权重为 `/home/linux/Documents/MSM/research_modules/d5_terminal_association/best.pt` 且允许参数覆盖。`ultralytics` 可用时可请求 ByteTrack 或 BoT-SORT 原生 tracker；依赖、权重或原生 tracker 不可用时返回 `unavailable` 或退回确定性 IoU tracker，并在 `YoloMotFrameResult.metadata` 标明 stream key、实际 backend 和 per-stream 状态作用域。fallback tracker 与 native model/tracker 均按 `(resource_id, camera_id)` 隔离；输出仍只是带 camera namespace 的 `LocalVisualTrack`，tracker ID 不替代 `global_track_id`。
- Deep SORT/ReID：仍仅作为未来对照来源；当前没有 ReID embedding、长遮挡恢复或 IDSW/IDF1 统计实现。
- OpenCV：已用于投影与可选畸变参数消费；未实现标定工作流和真实图像角点/AprilTag 检测。
- ROS 2 `tf2/message_filters`：仅作为未来坐标/时间同步方案；D5 当前不启动 ROS graph，不订阅 topic，不消费 bag。
- OpenDroneID、MAVLink signing、DDS Security、AprilTag：`IdentityChecker` 只解析仿真/fixture 风格身份字典并生成 `IdentityClaim`；未接入真实广播报文、密钥、证书、tag detector 或硬件链路。

未实现的真实工程能力及原因：

- 真实 AirSim/main 图像接线：最小 2 帧 RGB/YOLO/MOT 冒烟链已接通；仍需推进到连续多帧、多 seed 和非零 accepted detection。main 必须保持 stream key 稳定，并在 episode 边界调用 `reset_all_streams()`。
- 真实 MOT 标定：ByteTrack/BoT-SORT 原生质量依赖 `ultralytics` 和连续图像；IoU fallback 只保证 deterministic local ID 连续性，不声明遮挡恢复、ReID、IDSW/IDF1 工程质量。
- 真实标定链：缺少标定图像、标定板/AprilTag 角点、相机-机体系-世界系同步姿态、重投影误差验收阈值和 drift 告警流程。
- 真实身份认证链路：缺少 OpenDroneID/MAVLink/DDS 实际报文、密钥和白名单管理、时钟一致性、消息来源到平台身份的可信映射。
- 跨相机三维联合优化：缺少多相机同步 `CameraModel`、D2 航迹预测合同、三角化候选、重投影残差模型和 D4/D6 消费协议；当前只承诺 metadata-only peer evidence。

## 6. 二级侦察节点 cue 计划

本阶段假设存在若干可机动高空侦察无人机作为二级区域节点。节点携带高性能光电云台，可随任务机动，并依据 GlobalTrack/radar cue 指向目标簇；中心节点正常时向覆盖小区内的拦截资源发送图像 cue，中心节点失效时由 D4 降级到二级节点协调，二级节点也失效时才进入完全无中心协商。

D5 将该输入表示为 `ReconImageCue`：

- `producer_node_id`：cue 来源二级节点。
- `image_frame_id`：cue 所属图像帧。
- `global_track_id`：可选的全局航迹提示。
- `center_px` 与 `bbox`：图像平面提示。
- `confidence`：cue 置信度。
- `scoped_resource_ids`：允许使用该 cue 的资源集合。
- `cue_position_ned` / `look_at_ned`：雷达或 GlobalTrack cue 与云台 look-at 的 NED 位置。
- `gimbal_pointing_metadata`：云台 yaw/pitch、目标簇/子簇、时间同步或控制状态等报告字段。
- `cue_pointing_error_m` / `cue_pointing_error_rad` / `gimbal_track_error_px`：cue 指向和图像跟踪误差。
- `cue_source`：例如 `radar_global_track_cue`。
- `capability_class` / `coverage_mode`：例如 `mobile_high_recon` 与 `mobile_recon_gimbal`；固定俯视二级相机使用 `fixed_downlook_secondary`。

关键约束：

- 若 cue 来自二级侦察节点自己的相机，必须先重投影到当前拦截资源相机平面。
- 未重投影的二级相机像素不能直接与 `LocalVisualTrack.center_px` 比较。
- cue 只能降低候选代价，不能绕过授权、版本校验、友方确认和 MOT 质量门槛。
- 空 `scoped_resource_ids` 当前可视为广播 cue；若实验要求严格小范围分发，应改为显式广播标记或视为空无效。
- 当前实现已加入 cue 新鲜度、目标相机帧校验、重投影标记校验和 `recon_cue_used` 决策标记；`recon_cue_used_count` 仍需进入 D6/main 统一日志。

机动侦察节点的图像服务末端跨视角配准的目标链路是：

```text
GlobalTrack/radar cue
-> mobile high-recon gimbal look-at(cue_position_ned, look_at_ned)
-> detector/MOT produces LocalVisualTrack[] on recon/interceptor cameras
-> per-camera geometry gate and Hungarian/JPDA-style candidate selection
-> TerminalAssociation for the existing assigned_global_track_id
-> TerminalObservationBus/CrossViewAssociation evidence
```

固定俯视二级相机覆盖不足时，D5 只在 evidence 中报告 `fixed_downlook_secondary` 的覆盖缺口和 `mobile_recon_gimbal` 对目标簇/子簇的补充覆盖；它仍不生成分配计划、不控制云台、不改写 `global_track_id`。

## 7. 多无人机重叠视场配准计划

典型场景：无人机 1 的相机看到目标 1/2/3，无人机 2 的相机看到目标 2/3/4。两个相机的 `local_track_id` 只在本机本相机内有效，例如 `UAV1:cam0:L2` 与 `UAV2:cam0:L2` 可能指向不同目标，也可能分别是同一个 `global_track_id` 的两个观测。D5 的跨视场目标是把这些本地观测配准到 D2 已存在的 `global_track_id`，而不是在本地创造新的全局 ID。

建议流程：

1. 当前 `TerminalObservationBus` 收集每架无人机的 `TerminalObservation` 摘要；完全分布式 metadata-only 路径使用 `DistributedVisualObservation` 和 `VisualTrackletSummary` 携带资源、相机、帧、时间戳、协方差和本地 MOT 命名空间信息。
2. 对 D2 的每个 `GlobalTrack` 按各自相机的 `measurement_timestamp` 做时间预测。
3. 将同一个 `GlobalTrack` 分别投影到 UAV1、UAV2 等相机平面，得到每个视场内的像素预测和协方差。
4. 在每个相机内先做像素马氏门控，形成局部候选代价。
5. 对重叠视场中的共享目标 2/3，比较多相机候选是否同时支持同一 `global_track_id`。
6. 对时间差过大、相机姿态不可信、协方差过大或候选代价接近的情况输出 `ambiguous/unknown`，不强行跨视场绑定。
7. 二级侦察 cue 先重投影到每个目标相机平面，再按 `scoped_resource_ids` 对相应资源降低候选代价。

当前已实现接口：

- `TerminalObservation`：单条跨节点末端摘要，可携带 `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim` 和 `ReconImageCue`。
- `TerminalObservationBus`：被动收集多资源/多链路摘要，按既有 `global_track_id` 生成跨视角汇总。
- `CrossViewAssociation`：表达一个 `global_track_id` 的 `supporting_resource_ids`、命名空间化 `local_track_ids`、`ambiguity_score`、`duplicate_terminal_lock_risk`、来源节点和链路类型。
- `DistributedVisualObservation`、`VisualTrackletSummary`、`PeerCameraState`：完全分布式 metadata-only 跨 peer 输入 DTO。
- `TerminalCrossViewFusion`：基于时间窗口、bearing、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和姿态协方差做 gating/cost，并使用 Hungarian 或纯 Python fallback 做唯一匹配。
- `CrossPeerAssociationHypothesis`、`DistributedTerminalAssociation`：向 D4 输出支持假设、`hypothesis_only/hold/ambiguous/locked` 状态、重复终端锁定风险和命名空间化 local track IDs。

该最小实现覆盖 UAV1 看到目标 1/2/3、UAV2 看到目标 2/3/4 的摘要层逻辑：目标 2/3 得到多视角支持，目标 1/4 保持单视角支持；重复锁定只上报风险，不改分配。

当前 `TerminalCrossViewFusion` 是 P0 metadata-only 融合器，不做三维重投影、三角化、bundle adjustment、真实图像 ReID 或 D4 分配决策。后续完整几何融合可新增 `CrossViewTrackEvidence`，把相机几何重投影和 D2 航迹预测纳入同一摘要，但仍不改变 D5 不改写 `global_track_id` 的边界。

## 8. 实施流程

1. 读取 D3/D4 分配，确认授权状态和版本。
2. 从 D2 航迹表中查找中心分配的 `global_track_id`。
3. 按图像帧时间预测该航迹。
4. 调用 `project_tracks_to_image()` 得到像素预测和协方差。
5. 将本地检测/MOT 输出标准化为 `LocalVisualTrack[]`。
6. 将合作身份消息标准化为 `IdentityClaim[]`。
7. 将已重投影的二级节点图像提示标准化为 `ReconImageCue[]`。
8. 调用 `build_cost_matrix()` 构造候选代价。
9. 调用 `decide()` 输出 `TerminalAssociation`。
10. 记录候选代价、身份冲突、决策状态和 cue 使用情况，交给 D6 离线评估。
11. 当前可由 `TerminalObservationBus` 汇总多个资源的 `TerminalAssociation` 摘要，向 D3/D4/D6 上报 `CrossViewAssociation` 支持关系和重复锁定风险。
12. 完全分布式模式可由 `TerminalCrossViewFusion` 对多个资源的 `DistributedVisualObservation` 或 `VisualTrackletSummary` 做 metadata-only 跨 peer 融合，并只向 D4/D6 上报 `CrossPeerAssociationHypothesis` 和 `DistributedTerminalAssociation`。

## 9. 代码模块划分

```text
research_modules/d5_terminal_association/
├── PLAN.md
├── README.md
├── docs/
│   ├── ALGORITHM_AND_IMPLEMENTATION.md
│   ├── EXPERIMENT_REPORT.md
│   ├── AIRSIM_INTEGRATION_PLAN.md
│   └── terminal_decision_timeline.png
├── simulations/
│   └── run_terminal_association_sim.py
├── src/d5_terminal_association/
│   ├── airsim_cv_adapter.py
│   ├── airsim_geometry.py
│   ├── associator.py
│   ├── consistency.py
│   ├── geometry.py
│   ├── identity.py
│   ├── observation_bus.py
│   ├── terminal_cross_view_fusion.py
│   ├── visual_handoff.py
│   └── models.py
└── tests/
    ├── test_airsim_cv_2v2_secondary_plan.py
    ├── test_airsim_cv_5v5_evidence.py
    ├── test_distributed_cross_view_fusion.py
    ├── test_geometric_registration_validation.py
    ├── test_terminal_association.py
    ├── test_airsim_dry_run_interface.py
    ├── test_terminal_consistency.py
    ├── test_terminal_observation_bus.py
    └── test_visual_handoff.py
```

主要职责：

- `models.py`：定义 `GlobalTrack`、`LocalVisualTrack`、`Assignment`、`IdentityClaim`、`ReconImageCue` 和 `TerminalAssociation`。
- `airsim_cv_adapter.py`：转换 `simGetDetections` 风格检测框，生成 N-v-N ComputerVision 压测指标、三类降级证据摘要和 multi-seed calibration readiness 字段覆盖审计；5v5 只是 stress baseline。
- `yolo_mot_adapter.py`：运行或适配 YOLOv8 图像帧检测，优先请求 ByteTrack/BoT-SORT，缺依赖时退回确定性 IoU tracker，输出 `LocalVisualTrack` 和 backend metadata。
- `airsim_geometry.py`：提供 AirSim 相机内外参到 D5 投影模型的离线转换和几何匹配验证辅助，不读取 AirSim truth 做在线关联。
- `observation_bus.py`：定义最小跨节点 `TerminalObservationBus` 汇总逻辑，输出 `CrossViewAssociation` 风险与支撑摘要。
- `terminal_cross_view_fusion.py`：定义完全分布式 metadata-only 跨 peer 假设生成，输出 `CrossPeerAssociationHypothesis` 和 `DistributedTerminalAssociation`。
- `consistency.py`：把连续帧 `TerminalAssociation`、跨视角摘要和冲突状态压缩为 `TerminalConsistencySummary`。
- `visual_handoff.py`：给 D7/main 输出视觉 PNG handoff advisory metadata，检查 locked、bbox 稳定、分配一致和重复锁定风险。
- `geometry.py`：实现投影、协方差传播和马氏距离。
- `identity.py`：解析仿真身份声明并判断友方冲突。
- `associator.py`：实现投影、代价矩阵和保守决策。
- `simulations/`：生成离线合成场景和实验结果。
- `docs/`：保存算法说明、实验报告、图表和 AirSim 离线计划。

## 10. 关键接口

推荐全部使用关键字参数调用，尤其是 `current_time` 和 `recon_image_cues`：

```python
decision = associator.decide(
    assignment=assignment,
    global_tracks=global_tracks,
    local_tracks=local_tracks,
    identity_claims=identity_claims,
    camera=camera,
    current_time=current_time,
    recon_image_cues=reprojected_recon_cues,
)
```

核心接口：

- `TerminalAssociator.project_tracks_to_image(global_tracks, camera, timestamp=None)`
- `TerminalAssociator.build_cost_matrix(projections, local_tracks, identity_claims=(), recon_image_cues=(), resource_id=None)`
- `TerminalAssociator.decide(assignment, global_tracks, local_tracks, identity_claims=(), camera=None, current_time=None, recon_image_cues=())`
- `IdentityChecker.parse_claims(raw_messages, current_time)`
- `TerminalObservationBus.publish_terminal_association(...)`
- `TerminalObservationBus.publish_local_track(...)`
- `TerminalObservationBus.cross_view_associations()`
- `TerminalCrossViewFusion.summarize_observations(...)`
- `TerminalCrossViewFusion.build_hypotheses(...)`
- `TerminalCrossViewFusion.associate(...)`
- `local_visual_tracks_from_sim_detections(...)`
- `YoloMotAdapter.process_frame(frame, resource_id=..., camera_id=..., frame_id=..., timestamp=...)`
- `YoloMotAdapter.reset_stream(resource_id, camera_id)`
- `YoloMotAdapter.reset_all_streams()`
- `YoloMotAdapter.reset_episode()`
- `publish_sim_detections_as_local_observations(...)`
- `compute_terminal_stress_metrics(...)`
- `summarize_degradation_case(...)`
- `summarize_multiseed_calibration_readiness(...)`
- `summarize_secondary_visual_coverage_funnel(...)`

最小跨视角摘要接口：

```python
bus.publish_terminal_association(
    resource_id="UAV1",
    source_node_id="UAV1",
    link_type="interceptor_peer",
    timestamp=current_time,
    terminal_association=decision,
    local_track=local_track,
    camera_id="front_rgb",
    frame_id="UAV1/front_rgb",
)

cross_view = bus.cross_view_associations()
```

完全分布式 metadata-only 跨视场接口：

```python
distributed = terminal_cross_view_fusion.associate(
    observations=distributed_visual_observations,
    tracklet_summaries=peer_tracklet_summaries,
    camera_states=peer_camera_states,
    current_assigned_global_track_ids=current_ids,
    stale_assigned_global_track_ids=stale_ids,
)
```

该接口只输出 `DistributedTerminalAssociation`，每条摘要携带 `CrossPeerAssociationHypothesis`；不产生新分配计划，不创建或换绑 `global_track_id`。

## 11. 仿真场景设计

初始仿真使用简单图像平面和质点投影，不涉及真实飞控或硬件：

- 一个中心分配目标。
- 一个非分配干扰目标。
- 一个带合作身份声明的友方目标。
- 一个未知目标靠近分配目标投影，制造歧义。
- 分配目标短时遮挡，触发 `reacquire`。
- 友方目标与投影重叠，触发 `hold`。

后续补充：

- 已重投影的二级侦察 cue。
- stale cue。
- 跨资源 cue。
- 空 `scoped_resource_ids` 语义对照。
- UAV1 看到目标 1/2/3、UAV2 看到目标 2/3/4 的重叠视场 metadata-only 配准。
- N-v-N ComputerVision 压测：数量由 main runtime 的 `--drone-count N` 统一控制；5v5 baseline 使用目标距主镜头约 50m、目标间距 20m、镜头间距 20m，每个主镜头视场内至少两个目标。
- 二级可机动高空侦察节点可保持约 200m 高差，使用高性能光电云台按 GlobalTrack/radar cue 指向目标簇，并输出已重投影到拦截机相机平面的 `ReconImageCue`。
- 相同 `local_track_id` 在不同无人机中重复出现的命名空间冲突测试。
- 相机姿态误差、时间戳错位和高协方差观测导致的跨视场 `ambiguous`。
- `no_degradation`、`degrade_to_secondary`、`degrade_to_distributed` 三类 D5 证据 case。

## 12. 指标

D5 至少记录：

- `terminal_association_accuracy`
- `locked_precision`
- `wrong_locked_count`
- `ambiguous_count`
- `hold_count`
- `friend_overlap_hold_count`
- `reacquire_count`
- `time_to_terminal_lock`
- `terminal_id_switch_count`
- `global_track_id_rewrite_count`
- `recon_cue_used_count`
- `cross_view_association_accuracy`
- `cross_view_id_switch_count`
- `cross_view_ambiguous_count`
- `cross_view_duplicate_local_id_count`
- `per_camera_detection_count`
- `multi_target_fov_rate`
- `cross_view_overlap_count`
- `duplicate_terminal_lock_risk`
- `terminal_lock_accuracy`
- `ambiguous_fov_event_count`
- `secondary_single_camera_full_view_frame_rate`
- `secondary_network_joint_full_view_frame_rate`
- `secondary_camera_frame_visible_target_counts`
- `secondary_network_frame_joint_visible_target_counts`
- `secondary_single_camera_coverage_ratio_mean`
- `secondary_single_camera_coverage_ratio_min`
- `secondary_network_joint_coverage_ratio_mean`
- `secondary_network_joint_coverage_ratio_min`
- `detect_count`
- `local_or_recon_cue_count`
- `terminal_association_count`
- `cross_view_association_count`
- `multi_support_count`
- `rejection_reason_counts`
- `coverage_mode_counts`
- `mobile_recon_gimbal_improved_joint_coverage_frame_count`
- `mobile_recon_gimbal_added_target_ids_by_frame`
- `cue_pointing_error_m_by_camera_frame`
- `cue_pointing_error_rad_by_camera_frame`
- `gimbal_track_error_px_by_camera_frame`

其中 `global_track_id_rewrite_count` 应始终为 0。二级覆盖指标分三层解释：`visible_target_ids`/覆盖比例只表示二级相机“看见目标”；`secondary_network_joint_full_view_frame_rate` 表示同一帧多二级相机并集覆盖全部 active targets；`cross_view_association_count` 和 `multi_support_count` 才表示检测/本地 cue 已经转成既有 `global_track_id` 支持。`mobile_recon_gimbal_improved_joint_coverage_frame_count` 只说明机动云台 evidence 补足固定俯视覆盖，不代表 D5 获得分配或控制权限。

## 13. 预期交付物

- 根目录 `PLAN.md` 和 `README.md`。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：中文算法原理与实施方案。
- `docs/EXPERIMENT_REPORT.md`：中文实验报告和图表引用。
- `docs/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放与接口计划。
- Python 源码、单元测试和离线仿真脚本。

## 14. 局限与后续工作

- `ReconImageCue` 的 scope、age、frame 和重投影标记已有代码校验，但真实二级侦察图像反投影/重投影链路尚未接入；当前 cue 仍主要来自 fixture 或预处理结果。
- 已实现 `TerminalObservationBus`、`CrossViewAssociation`、`TerminalCrossViewFusion` 和 N-v-N ComputerVision dry-run evidence helper。
- 尚未完整实现跨无人机多相机三维几何融合；`CrossViewTrackEvidence` 仍是后续接口建议。
- 当前身份声明为离线仿真抽象，不连接真实 OpenDroneID、MAVLink signing、DDS Security 或 AprilTag detector。
- 本地 MOT 质量对小目标场景影响大；18-case AirSim screening 已证明 20 m 下 ByteTrack/BoT-SORT 可原生连续运行且延迟在预算内，但 precision/recall 仅约 0.26-0.33，30/50 m 无检测，0 候选进入 confirmation。bbox 口径/尺度、远距召回、GPU/CPU 多 seed 预算仍未闭合。native 模式为避免 `persist=True` tracker 串流而按 stream 创建独立 model/tracker，资源占用随活跃 stream 数增长。
- D5 输出只用于 D4/D6/D7 的证据、评估和上游复盘，不应被解释为自动处置命令。

### 14.4 P1 M5N2 视觉鲁棒性 replay（2026-07-12 已实现）

本轮完成 D5 模块侧的可重复 replay 支撑，不修改 main/runtime、D7 控制或 PNG/KF 公式：

- 关联历史按 resource/camera/assigned GlobalTrack 隔离，阻止跨相机 local ID 和丢锁窗口串联。
- 对同一 plan lineage 保存最高已接受版本，下降版本保守 `hold`；未授权或 track-version 不匹配的输入不会抬高 watermark。
- 无 measured detection 或仅有 predicted local track 时不授权；超过 0.25 s 输出显式过期/fail-closed evidence。
- 恢复观测必须重新满足马氏门、候选唯一性、身份冲突检查和两次 measured 稳定支持，MOT ID 变化不触发全局换绑。
- 专项测试覆盖 1-5 帧 dropout、同相机交叉、跨相机 1/2/3 与 2/3/4 式部分重叠、外参漂移、时间偏差和 stale plan。

该实现轮次验收结果为 D5 全量 `168 passed`。main 后续已运行 M5N2 paired AirSim；当前实测为 120 条 active-primary/visible、74 条 D5 关联/锁定证据和最佳 coalition completion 5/10。真实 detector/MOT、相机曝光/姿态同步和第二 primary 多 seed 阈值仍开放，不能用本轮合成 replay 代替。

### 14.5 P1 版本化 summary API/CLI（2026-07-12 已实现）

- `P1VisualRobustnessSummary`/`P1VisualRobustnessCaseResult` 固化 schema、profile 和逐 case 安全计数。
- `run_p1_visual_robustness_matrix()` 无随机数、无 AirSim 依赖，复用当前 D5 在线 API 运行 10-case 矩阵。
- `write_p1_visual_robustness_summary()` 和 CLI 写出稳定排序 JSON，重复运行字节一致。
- payload 同时携带 D6 readiness 兼容字段与 `metadata.case_results`；已用当前 D6 `--d5-summary` 实际加载并生成 aggregate/source manifest。
- truth/expected mapping 只在关联结果返回后离线比较；在线输入不携带 actor/object/truth/global label。

当前 API 结果为 10/10 case 通过、24 次预期保守拒绝、在线 truth 使用 0、全局 ID 改写 0，D5 全量 `171 passed`。下一步 main/D6 可把该 JSON 与真实 AirSim paired/multi-seed summary 并列，不得用确定性 fixture 代替真实持续 detect 和物理闭环。

### 14.1 M 对 N 计划内多机锁定（合同已实现）

专项调研见 `subagent_reviews/D5_M_TO_N_TERMINAL_MULTIVIEW_REVIEW.md`。当前主线继续使用中心航迹投影、像素马氏门控、本地 MOT 和跨视角稳定支持，不引入单一重型多视图框架替代现有合同。

2026-07-11 已按 D3 `assignment_plan_v2` 名称实现只读消费：`coalition_id/version`、`member_role`、`wave_id`、`required_resource_count`、`coordination_mode`、arrival window、`plan_id/version` 和 activation state 均由 `Assignment -> TerminalAssociation` 保留，detect-to-GlobalTrack registration binding 也携带同一合同。多个已授权且已激活成员锁定同一中心拥有 `global_track_id`，在联盟/计划版本一致且资源数不超过 demand 时记为 `planned_cooperative_lock`，不再仅因 locked resource 数量大于 1 设置 duplicate。第四个超额资源、联盟外或版本不一致、resource scope 不符、未激活成员、单资源多本地锁定及 local-to-global 多重绑定仍形成 conflict/duplicate evidence。

未激活 `reserve/retry` 的视觉候选不会被丢弃：D5 完成本资源/本相机投影与 MOT 配准后输出 `hold`，并记录原始视觉匹配状态、activation blocker 和 D7 visual PNG execution gate；默认 active primary wave-0 与 k=1 保持兼容。D5 不决定联盟、不裁减超额资源、不修改分配或全局 ID。

2026-07-11 已补 `CoalitionVisualSummary`、纯函数 `summarize_coalition_visual_completion()` 和 `TerminalObservationBus.coalition_visual_summary()`。接口只读消费单联盟 D3 guidance bindings 与当前/历史 terminal associations，输出 `primary_required_count`、`primary_locked_resource_ids`、`primary_lock_complete`、`reserve_ready_resource_ids`、`coalition_visual_consensus`，并保留 `planned_cooperative_lock`、duplicate/over-demand、版本冲突和 excess resource 字段。D3 guidance binding 未直接暴露总需求数时，接口以该单联盟 binding 数量作为 `required_resource_count`，`primary_resource_count` 仍由 D3 合同提供。

hybrid 默认稳定口径为：所有已授权 active primary 都必须在当前帧锁定，且每个 primary 至少连续 2 帧保持 execution lock，才设置 `primary_lock_complete=True` 和 `coalition_visual_consensus=True`。standby reserve 的本机几何/MOT 匹配可由 `hold + visual_match_decision_state=locked` 形成 `reserve_ready_resource_ids`，但不进入 consensus 或视觉 PNG 授权。resource/camera provenance 不一致、借用 bbox、无本机 local detection、计划/联盟版本冲突或联盟外执行 lock 均保守阻断。

连续两帧不再要求 plan/coalition version 完全相同。bus 会保存先前 binding 快照并逐帧验证两者严格单调上升；当前输出永远使用当前 binding 的 plan ID/version 与 coalition version，历史 association 仅贡献稳定计数。`coalition_id` 仍是不可变 identity，reserve 集合可变化但 primary 集合必须相同。metadata 输出 `stability_continued_across_plan_version_resource_ids`、`stability_reset_reason_by_resource`、`stability_source_plan_versions_by_resource` 和 `stale_plan_replay_resource_ids`。`clear()` 同时清理 observation、binding snapshot 和 invalid-version state，episode 之间不得串联。

2026-07-11 真实 AirSim 集成暴露 `TerminalObservationBus` 历史污染：旧实现的 `cross_view_associations()` 遍历全部 `_observations`，导致旧 timestamp/旧 plan 的 lock 被解释为当前并发 duplicate，进而向 D3 提供持续错误风险。现已增加可选 `as_of_timestamp`、`max_age_s`、`plan_id`、`plan_version` 快照作用域；作用域模式先做时间与计划过滤，再按 resource 保留最新 timestamp 的同帧全部观测，最后才运行 local/global duplicate 和 coalition 合法性判断。无参数调用仍保留离线兼容行为，`CrossViewAssociation.metadata` 可审计 scope 与筛选数量。main 应在每个 decision frame 使用当前 frame timestamp、约 `1.5 * dt` freshness 和当前 plan identity。

跨视角边界保持两层：已实现层只汇总各 resource-camera 独立完成的投影/MOT/锁定证据并解释联盟合法性；尚未实现层是带相机位姿/像素协方差的多视角 bearing 三角化、可观测度/PDOP 和融合协方差。同步帧可作为后续瞬时三角化输入；序贯帧必须按 measurement timestamp 运动补偿并膨胀协方差，历史支持不得冒充当前同步支持。OpenCV 是几何默认候选，ByteTrack 是本地 MOT 默认候选，BoT-SORT、ReST 和多视图 GLMB 只作为可插拔或研究对照。

### 14.2 真实 AirSim M=5、N=2 检测/几何历史基线（2026-07-11）

以下 `blocks_cv_m5_n2_cooperative_live_20260711` 记录是 commit-aware gate 和受控跨版本延续实施前的诊断基线，已被 1.2 节的 10-seed 当前验收取代，不得再解释为当前 T001 状态。

证据目录 `research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_cooperative_live_20260711` 使用 5 个主 ComputerVision 相机、2 个二级相机和 2 个 `Quadrotor1` actor。7 个相机均持续返回 640x480 Scene 图像，但 `simGetDetections` 在每个 9 帧 episode 的前 8 帧均为 0；仅部分 episode 的末帧由 `Secondary_Recon_1` 返回 1 个约 7x7 px 的 bbox。full-flow D5 输出为 32 `reacquire`、4 `ambiguous`、0 `locked`。

D5 复核没有发现 bbox 解析或几何公式 bug。把唯一 bbox 与其真实来源相机 `Secondary_Recon_1:0` 的同帧外参配对后，`T002` 投影与 bbox center 误差约 0.09 px，几何关联正确选择 `T002`；该检测 `mot_history_length=1`，低于默认 2，因此 `ambiguous:mot_history_too_short` 是预期行为。日志中的 18-78 px 不是同相机标定残差：main runtime 在资源自有相机无检测时把全部 local tracks 作为 fallback，导致二级相机 bbox 被 4 个主资源用各自主相机模型重复评估。D5 只接受调用方提供的单 camera local-track batch，不能在缺少 resource-to-camera 映射时猜测或重绑来源。

当时的 main/runtime 修复建议（历史）：主资源无本相机检测时返回空 local batch，不得 fallback 到其他相机；二级检测必须使用二级相机模型形成 recon/cross-view evidence。AirSim 侧在 spawn 后同时尝试 actor exact name 与 asset mesh filter `Quadrotor1*`，并在 filter、actor pose 或 camera pose 更新后增加渲染 warm-up，再采集计数。专项验证时可临时 `--save-images`，验证后恢复默认不保存 PNG。

建议 main 修复 scope/warm-up 后运行：

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --sequence-id blocks_cv_m5_n2_filter_probe \
  --cv-5v5 --resource-count 5 --target-count 2 --secondary-count 2 \
  --enable-cooperative-demand --high-threat-resource-count 3 \
  --cooperative-high-threat-target-count 1 \
  --duration 8 --dt 0.5 \
  --target-asset-name Quadrotor1 \
  --target-detection-filter 'Quadrotor1*' \
  --secondary-height-above-targets 50 \
  --save-images

jq -r '[.frame_index,.timestamp,.metadata.detection_count,
  ([.metadata.detections[] | .camera_vehicle_name + ":" + (.count|tostring)] | join(","))]
  | @tsv' \
  research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_filter_probe/episode_006_full_flow/blocks_frames.jsonl
```

验收要求不是单个末帧偶发 detection，而是预期可见相机至少连续 2 帧 count>0；每条 terminal geometry record 必须同时记录且满足 `measurement_camera_id == projection_camera_id`。完成图像诊断后去掉 `--save-images`。

P1 补齐状态：

- 已完成 M-to-N 联盟视觉完成纯函数和 bus 薄封装，专项测试覆盖 hybrid 2+1、缺一个 primary、reserve-only、两帧稳定、版本冲突、跨相机 bbox 拒绝和 over-demand。
- 已完成 cross-view 当前快照过滤，专项测试覆盖同资源跨帧不 duplicate、旧 plan 多资源 lock 不污染新 plan、同帧当前 plan 非授权多 lock 仍 duplicate、授权 coalition 同帧合法，以及无参数历史兼容；实现当时的 D5 回归基线为 `127 passed`。
- 已完成 D5 侧 AirSim CV replay 可写盘字段：projected pixel、bbox center、pixel error、Mahalanobis、gate pass、candidate margin、measurement age、friend conflict、selected pair、`duplicate_terminal_lock_risk` advisory、`recon_cue_used_count` 和 visual PNG advisory metadata。main/D6 若需要实际 JSONL/CSV sink，应在 runtime/D6 owned path 接入这些 D5 输出字段。
- 已完成 D5 侧 multi-seed calibration readiness helper：`summarize_multiseed_calibration_readiness()` 对 `TerminalObservation` 和 `CrossViewAssociation` 做被动字段覆盖审计，输出每个 seed 的 `missing_required_fields`、`missing_recommended_fields`、source/backend counts、truth-label count、handoff/bbox-stability count 和 duplicate/friend conflict count。truth label 只作为离线 metadata 计数，不参与在线关联。
- 已完成 D5 侧二级覆盖/漏斗诊断 helper：`summarize_secondary_visual_coverage_funnel()` 输出 `not_all_targets_visible`、`network_union_incomplete`、`no_global_binding`、`reacquire_not_grouped`、`stale_or_missing_recon_cue`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`secondary_detect_offline_only` 和 `registered_to_global_track` 断点计数，帮助 main/D4/D6 区分“二级相机看见了目标”“二级网络并集覆盖了目标”和“D5 已形成全局 ID 支持”。
- 已完成 D5 侧 AirSim settings 驱动 detect-to-global-track registration helper：`register_local_visual_tracks_to_global_tracks()` 消费 `GlobalTrack[]`、D2/D3 binding/`Assignment`、每相机 `CameraModel(K/R/t)`、timestamp、像素协方差和 `LocalVisualTrack[]`，用像素马氏距离 + Hungarian 匹配输出 `DetectToGlobalTrackCandidate.outcome`、`TerminalObservation` 和 `CrossViewAssociation`；SciPy 不可用时退回确定性唯一匹配，同时保留 gated candidates 供 JPDA-compatible 下游使用。输出 records 携带 `detect_registration_outcome`、`detect_registration_reject_reasons`、projection reason、timestamp、measurement age、covariance/projection covariance summary 和 reasons，覆盖 `no_global_binding`、`stale_or_missing_recon_cue`、`projection_invalid`、`geometry_gate_rejected`、`network_union_incomplete`、`stability_window_failed`、`secondary_detect_offline_only` 和 `registered_to_global_track`。二级 detect 只能增加既有 `global_track_id` 支持，不能创建、重绑或使用 AirSim truth/actor ID。
- 已完成 main runtime P1 calibration sweep 和 D6 bundle 对 D5 evidence 的接线口径：D5 不启动 AirSim、不生成报告，但其 `TerminalObservation`、`CrossViewAssociation`、registration reason、secondary funnel 和 mobile gimbal metadata 已是 sweep/D6 统计的输入合同。
- 已完成 D5 侧机动侦察云台 cue evidence：`ReconImageCue` 与 coverage/cross-view summary 可携带 NED cue/look-at、云台 metadata、pointing/track error、`cue_source=radar_global_track_cue`、`capability_class=mobile_high_recon` 和 `coverage_mode=mobile_recon_gimbal`。历史 mobile recon stress 只保留为旧批次基线；2026-07-10 的 60-case sweep 已达到 `not_registered_count=0` 和平均 cross-view association `4.417`，当前主瓶颈转为同帧全目标覆盖、稳定支持和 D4 逐决策消费。
- 已完成 `TerminalConsistencySummary` 连续窗口修正：`TerminalConsistencyTracker` 按 `resource_id + assigned_global_track_id` 维护窗口，`assignment_version` 只做摘要审计字段。同一资源持续执行同一全局目标时，滚动 plan version 不会清空连续 `locked/ambiguous/hold/reacquire` 状态。
- 已完成 D4 evidence 输出：`CrossViewAssociation`、`DistributedTerminalAssociation.recommended_d4_action`、`duplicate_lock_resource_ids`、`hypothesis_only/hold/ambiguous` 原因和连续帧 `TerminalConsistencySummary` 均为 D4/D6 advisory evidence；D5 不触发降级、不生成 `AssignmentPlan`、不选择主备资源。
- 已完成 D7 visual PNG 前置证据：`annotate_visual_png_handoff()` 输出 handoff/prelock 建议、gate pass、blockers、measurement age、LOS availability、bbox stability、range band、timing 和 maneuver metadata；assignment mismatch、friend conflict、duplicate risk、unstable bbox、stale measurement age 或 missing LOS 都会阻断建议。
- 已完成 AirSim truth ID 在线隔离、YOLO/ByteTrack 离线 schema adapter 和 YOLOv8 frame adapter：AirSim `object_id`、`actor_name`、`truth_id`、`true_global_track_id` 或 `global_track_id` 输入字段不会进入在线关联；在线 category 只接受 `category/label/class_name` 或 detector `class_id + names` 映射，通用 `name/actor_name/object_name` 不影响 category、cost、binding 或 online metadata。本轮二级节点也先按 `simGetDetections` bbox/metadata 转 `LocalVisualTrack`，不启用 YOLO，且不会把 actor/truth alias 当作本地在线身份。truth 只允许进入离线 evaluator/metadata 统计。YOLO/ByteTrack row 或 frame adapter 输出只转为命名空间化 `LocalVisualTrack`，metadata 记录 confidence、class id、bbox scale、tracker backend 与 CPU/GPU budget，tracker ID 不替代 `global_track_id`。
- 2026-07-10 已闭合 active reacquire 友方声明复检 P0：候选在任何 `locked` 输出前复用 `IdentityChecker`，verified/stale/unverified/spoof-suspected 友方声明重叠均输出 `hold`，顶层与 search-window/candidate metadata 保留冲突状态和 reason；同一/新 MOT ID 回归均保持 `global_track_id` 不变。
- 2026-07-10 已闭合多相机 MOT 状态隔离 P1：fallback tracker 与 Ultralytics native model/tracker 按 `(resource_id, camera_id)` 持久化，提供单 stream 和全 episode reset API；交错相机、reset、native 成功及 native-to-fallback 回归均不串 ID/history。
- 2026-07-10 已闭合 D5 侧逐帧 D4 evidence P1：新增 `SecondaryFrameAssociationEvidence` 和 `build_secondary_frame_association_evidence()`，只消费同一 `frame_id`/timestamp 的 camera/network coverage 与当前帧 registration candidate，输出 D4 `TerminalAssociationSummary` 可直接消费的 coverage/full-view、stable/not-registered、cue freshness、gimbal 和 reject reason 字段。历史 candidate 只记 ignored count，混合 frame/timestamp 拒绝，禁止 episode 聚合冒充实时证据。
- 2026-07-10 已补齐 D5 YOLO/MOT adapter P1 元数据：默认优先 Ultralytics ByteTrack/BoT-SORT，依赖缺失明确 `unavailable`，detector 可用时提供 deterministic IoU fallback；输出实际 selection、processing latency、CPU/GPU budget comparison、observed device、camera-local continuity 和离线 detector recall/precision/FN/FP。离线 bbox 只在在线结果形成后评分，不携带 identity，也不影响 `LocalVisualTrack` 或 `global_track_id`。新增 5v5 多相机、交叉、短时遮挡恢复 fixture；本机 `best.pt` + Ultralytics 8.4.71 CPU 黑帧烟测可加载运行，因无检测按预期回退，不能替代真实目标多 seed 质量验收。
- 2026-07-11 已修复真实 AirSim YOLO/MOT 冒烟中的 bbox-only 离线标签解析：单个 `xyxy`、多个 `xyxy` 和 dict/object detection 均可进入 offline detector evaluation；畸形输入明确失败。该路径只计算聚合检测指标，不向在线 tracker 或全局绑定暴露身份。
- 2026-07-10 2v2 smoke 复核：2/2 资源对完成拦截，pair summary 的 D5 状态均为 `locked`，但 D7/main 因 `bbox_near_image_edge` 拒绝视觉接管 9 次、覆盖 2 个资源对，仅 2 个控制记录允许切换。该现象不要求放宽 D5/D7 门控；P1 需补充边缘裕量、连续边缘帧、相机指向误差和 handoff 抖动的多 seed 标定。
- 同一 smoke 的终端记录曾包含 `Interceptor*:0:MSM_TargetActor_*` 本地 ID。D5 sim-detection adapter 已过滤 actor/truth alias；main hotfix 已把 builtin detect 改为仅基于 bbox 的匿名 camera-local tracker，清理 intercept 注入和 D4/D5 fallback 的 actor-name local ID，并把 actor 名限制为 offline truth metadata。真实 AirSim 证据 `research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710` 中三类 case 均 connected、各 5 帧，local/detection ID 无 actor 名，匿名 ID history 达 5，offline truth 标记正确且 cross-view association 均为 4。端到端 truth 隔离 P0 已闭合；D5 不越权修改 runtime，也不对任意既有本地 tracker ID 做字符串重写。

P0 状态：无 P0 blocker。active reacquire 友方声明复检、detection category/truth 隔离和端到端 AirSim actor-name local ID 隔离均已闭合。安全合同仍需持续回归：D5 不分配、不授权、不改写 `global_track_id`，在线逻辑不得使用 AirSim truth ID。

剩余 P1：

- M5N2 协同视觉闭合：2026-07-13 paired AirSim 已取得 120 条 active-primary/visible 证据和 74 条 D5 关联/锁定证据，但最佳 coalition completion 仅 5/10。下一验收聚焦第二 primary 的持续检测、bbox 稳定和 measured lock，将 `d5_not_locked` 与 `terminal_detection_acquisition_timeout` 分开统计，目标至少 8/10；不恢复同时到达要求，不降低安全门控。
- 真实 YOLOv8 + ByteTrack/BoT-SORT 多 seed：18-case screening 已完成；20 m native active/continuity 为 1.0、IDSW 为 0、P95 约 7.4/16.2 ms，但 precision/recall 仅约 0.26-0.33，30/50 m 无检测。先完成 bbox 定义/尺度/时间对齐和远距召回诊断；只有候选通过 screening 后才运行至少 10 seeds 的 confirmation，并由 D6 评估 IDSW/IDF1、遮挡恢复、`locked_mismatch`、false handoff 与 `terminal_id_switch_count`。
- 外参漂移与时间同步：P2 已完成合成扰动敏感性对照；P1 仍需针对真实 AirSim/replay 的 per-camera `K/R/t/dist_coeffs`、measurement/arrival timestamp 做多 seed 漂移与时延标定，统计重投影误差、马氏门控拒绝率、错误锁定率和恢复时间，不在 D5 内伪造同步后的真值位姿。
- 二级同 tick freshness：D5 frame-scoped DTO 和 D4 字段映射已完成；main/D4 仍需在同一 decision tick 消费该 DTO，并记录 threshold version、stale rejection、覆盖状态和接管迁移。不得使用 episode 聚合值回填，也不得让 D5 直接触发降级。

剩余 P2/P3（OpenCV 合成 calibration/`solvePnP` benchmark 已完成）：

- 在真实图像链路后评估 BoT-SORT、Deep SORT 和 ReID 是否适合小型无人机图像；用 IDF1/IDSW、遮挡恢复和算力预算决定是否只保留 ByteTrack + 几何门控基线。
- P2 接入真实身份源、密钥/证书和白名单运维；未知、过期、伪造或校验失败只能降低可信度，不能升级为敌方或锁定目标。
- P2 建立完整在线 PnP/PnP RANSAC、真实标定图像、畸变校正和在线外参更新链；P1 几何 drift 验收不以此为前置条件。
- P3 仅以离线 replay/对照研究 IBVS，D5 不实现视觉伺服控制器、不授权控制。
- P3 ROS 2 `tf2/message_filters` 只在项目进入 ROS 2 runtime 或 bag replay 后实施，目标是维护带戳 frame tree 和相机/航迹时间同步，不改变 D5 不改写 `global_track_id` 的边界。
