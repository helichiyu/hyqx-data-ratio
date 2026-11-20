# DM 算法侧问题清单（待统一发给算法同事）

> 记录日期：2026-11-18（2026-11-19 补充说明）
> **算法侧答复见 [`算法侧问题答复-DM.md`](算法侧问题答复-DM.md)**（2026-11-19）。
> 状态：下列问题已逐条答复并处理；本文件保留原始记录。当前本地只剩环境准备：按
> `operator/requirements.txt` 安装依赖，并从发布包/模型仓准备 `operator/weights/`（git checkout 不带权重）。
> 环境：本地三端联调（后端 8082、算法 8092、前端 9851）
> 用途：汇总平台侧接入时发现的算法资产/契约/依赖问题，后续统一发送；不在平台侧修改算子代码。
>
> **注意**：第七/八/九步的“仿真/生产/分析未接执行链”属于平台侧编排未完成，
> 不是算法缺陷，见 `平台侧问题清单-DM.md`，不要混入本清单发给算法同事。

| # | 事项 | 状态 | 结论 |
| ---: | --- | --- | --- |
| 1a | bge-base-zh-v1.5 | ✅ 已解决 | 已从 ModelScope `BAAI/bge-base-zh-v1.5` 下载，13 个文件 SHA256 全部匹配 |
| 1b | paraformer-zh | ⚠ 版本不一致 | ModelScope 上游已下载，但 `model.pt` 等 5 个文件与 `SHA256SUMS` 不一致，`.mdl/.msc/.mv` 等 7 个文件上游没有；音频/视频 ASR 未验证 |
| 1c | fsmn-vad / ct-punc | ⚠ 未使用/未校验 | 代码当前只读 `paraformer-zh`；SHA 清单未登记这两个目录，联调音频前需算法侧确认 |
| 2 | OP-11 CPU/依赖 | ✅ 已解决 | CPU 可跑，按 `operator/requirements.txt` 安装；本机需 ffmpeg |
| 3 | OP-08 / OP-06 | ✅ 已解决 | basic 画像平台链路已改为 OP-01→02→06→08，OP-06 失败即任务失败 |
| 4 | 模型网关凭据 | ✅ 已答复 | 当前 14 个算子均不调用网关，凭据缺失不影响任务 |
| 5 | ffmpeg | ✅ 已答复 | 生产镜像内置；本地联调自行安装 |
| 6 | 打标结果契约 | ✅ 已答复 | labels 单条、topK 降序、path 数组、未归类保留 result.jsonl |
| 7 | 置信度阈值 | ✅ 已解决 | 平台默认 0.25，与 OP-05 一致；阈值版本 dm-2026-11-19 |
| 8 | 测试版本污染 | ✅ 已解决 | 平台已支持删除非生效分类版本 |

---

## 1. 打标算子 OP-05 权重（bge ✅ / paraformer ⚠）

**现象**：数据打标任务启动后约数秒失败：

```text
[DEPENDENCY_UNAVAILABLE] 模型权重缺失：
.../operator/weights/shared/bge-base-zh-v1.5
（缺少 config.json, pytorch_model.bin）
```

**影响**：文本打标无法完成，`hs_data_mixing_sample_label` 无样本，生产/分析随之中断。
平台侧已按契约把失败明确落库，不会停在 running。

**需要算法侧确认/提供**：

1. `bge-base-zh-v1.5` 的完整权重文件（至少 `config.json`、`pytorch_model.bin` 或等价分片）及 SHA256；
2. 交付方式：直接给权重包，或给可从内网模型仓下载的脚本；
3. 目录约定确认：`operator/weights/shared/bge-base-zh-v1.5/`，或 `WEIGHTS_DIR`/`D:\models\shared\bge-base-zh-v1.5/`；
4. 是否还需要 RapidOCR、FunASR paraformer-zh 等模型文件才能覆盖图像/音频/视频打标。

**2026-11-20 状态**：
- `bge-base-zh-v1.5`：已从 ModelScope 下载到 `operator/weights/shared/bge-base-zh-v1.5/`，13 个文件 SHA256 与清单全部匹配；文本打标/basic 画像已跑通。
- `paraformer-zh`：已从 ModelScope 下载，但上游 `model.pt`、`config.yaml`、`configuration.json`、README、示例音频与清单 SHA 不一致，且清单中的 `.mdl/.msc/.mv`、`asr_example_hotword.wav`、`hotword.txt`、`fig/res.png`、`fig/seaco.png` 上游没有；**音频/视频 ASR 未验证**。需要算法侧提供与 `SHA256SUMS` 完全一致的权重包，或更新清单/说明哪些文件非必需。
- `fsmn-vad`、`ct-punc`：算法答复提到，但当前算子和 SHA 清单都没有使用/登记；联调音频前需确认。

**平台侧动作**：权重到位后执行 `python scripts/stage_weights.py`，重启 8092，重新打标。

---

## 2. OP-11 语音画像依赖 torch/funasr（✅ 已解决）

**现象**：本机算子池 21/22 ready，`dm-speech-analysis` 因缺 torch 等依赖不可用；
`operator/weights/shared` 也没有语音模型。

**影响**：画像类型「语音属性」无法执行；文本/质量/规模等不受影响。

**需要算法侧确认**：

1. CPU 环境是否支持语音算子；如只支持 GPU，给出最低显存/驱动要求；
2. FunASR / paraformer-zh / 其他声学模型权重及版本；
3. `torch`、`funasr`、`librosa`、`soundfile` 的推荐版本组合（生产镜像已锁版本，本地 venv 未装 torch）。

---

## 3. OP-08 领域覆盖依赖 OP-06 领域标签（✅ 已解决）

**现象**：画像 `basic` 能跑通，但 `domainCoverage.coverage` 为空，页面标注
「领域覆盖暂不可用：当前数据集还没有领域标签（需先完成 OP-06 领域打标）」。

**影响**：不是报错，但领域覆盖图/缺口无法展示；配比方案的领域覆盖依据不足。

**需要算法侧确认**：

1. OP-08 是否必须消费 OP-06 结果目录；没有 OP-06 时是否只能 `unavailable`；
2. 平台编排是否需要固定链路 `OP-01 → OP-02 → OP-06 → OP-08`；
3. OP-06 需要哪些标签树/权重/配置，是否有轻量 CPU 版本。

---

## 4. 模型网关凭据缺失（✅ 已答复）

**现象**：`GET /health` 返回：

```json
"modelBackend": {
  "backend": "idg",
  "credentialsOk": false,
  "missing": ["MODEL_GATEWAY_BASE_URL", "MODEL_APP_KEY"]
}
```

**影响**：当前文本/画像算子未走模型网关，暂不影响已跑通流程；如 OP-05/OP-11/OP-12
依赖网关，则需要凭据。

**需要算法侧确认**：

1. 哪些算子必须调用模型网关，哪些可纯本地推理；
2. 联调环境是否可用 siliconflow 平替，需要哪个 Key；
3. 生产 idg 网关的 Base URL / APP_ID / APP_KEY 由谁注入。

---

## 5. 运行环境依赖 ffmpeg（✅ 已答复）

**现象**：算子 `healthz` 的 `dependencyStatus.ffmpeg = missing`（本机未装 ffmpeg）。

**影响**：音频/视频解析与关键帧提取可能不可用；纯文本/图像流程不受影响。

**需要算法侧确认**：生产镜像是否已内置 ffmpeg；本地联调是否必须安装，推荐版本。

---

## 6. 打标结果契约确认（✅ 已答复）

**平台侧解析**：OP-05 `result.jsonl` 每行 `labels[].path` 是数组，平台按 `/` 拼接成
`labelPath`，并取 `labels[0]` 作为主标签；`topK`、`evidence` 原样落库。

**需要算法侧确认**：

1. `labels` 是否按置信度降序，`labels[0]` 是否保证为主标签；
2. 路径分隔符固定为 `/`，且必须与平台分类树 `node_path` 完全一致；
3. `treeVersion` 当前为 `taxonomy-1013-pending`，平台后续会有版本切换；算法侧如何接收/校验版本；
4. 未归类样本是否只进 `unclassified.jsonl`，`result.jsonl` 中是否保留 `labels=[]` 的记录。

---

## 7. 置信度阈值口径（✅ 已解决）

**平台侧**：打标任务可配置 `confidence_threshold`，当前默认取系统阈值（0.6）；
OP-05 README 默认参数为 `confidence_threshold=0.25`。

**需要算法侧确认**：平台传入的值是否直接覆盖算子默认值；0.25 与 0.6 的业务语义是否一致，
避免“平台以为 0.6、算法按 0.25 放行”的口径偏差。

> **2026-11-19 已处理**：平台默认值改为 0.25（`DmThresholdProperties`、`application.yml`），
> 与 OP-05 一致。依据与后续口径见 [`算法侧问题答复-DM.md`](算法侧问题答复-DM.md) 第 6 节。

---

## 8. 测试版本污染提示（✅ 平台已解决）

分类体系性能验证过程中创建了多个「性能验证-批量快照」草稿版本；不影响算子，
但版本列表会看到。后续可加版本删除/归档清理能力。

---

## 9. 剩余非算法阻塞（本地环境准备）

- **bge 权重已落地**：已放 `operator/weights/shared/bge-base-zh-v1.5/`，SHA 全匹配；文本打标、basic 画像已跑通。
- **paraformer 权重版本不一致（算法侧待确认）**：上游 ModelScope 文件与 `SHA256SUMS` 不一致，音频/视频 ASR 尚未验证；需算法侧提供与清单一致的权重包或更新清单。
- `fsmn-vad`、`ct-punc` 当前代码未使用，SHA 清单也未登记；如需音频/视频，先确认是否必需。
- 本机需按 `operator/requirements.txt` 安装 torch/transformers/funasr 等依赖，并安装 ffmpeg；否则打标/语音/basic 画像会明确报依赖缺失。
- 依赖/ffmpeg 属于本地环境准备；paraformer 权重版本不一致属于算法侧交付物问题。bge/文本链路已闭环。
