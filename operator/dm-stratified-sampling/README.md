# OP-04 分层抽样（`dm-stratified-sampling`）

- 语义编码：`corpus_shard_stratified_sample_v1`
- 阶段/优先级：S3 / P1
- 版本：`0.1.0`
- 模型：无（Neyman 公式 + 哈希抽样）

## 1. 用途与边界

**做**：按 来源 × 主题簇 × 质量等级分层，Neyman 分配配额，确定性无放回抽样；输出层配额、样本清单、实抽比例、代表性偏差、未达标层与参数快照。

**不做**：不做选样打包（OP-17）、不做跨层借调（默认关闭）、不做库存扣减。

## 2. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `share` | 大样本 0.05 / 小样本 0.20 | 抽样比例 |
| `cluster_path` | 无 | OP-03 结果，用于主题层 |
| `quality_path` | 无 | OP-14 结果，用于质量层 |

## 3. 指标口径

- **Neyman**：`n_h = n·(N_h·CV_h)/Σ(N_h·CV_h)`；CV = 层内单位大小（文本字数/媒体字节）标准差/均值；CV 全 0 退化为按 N_h 比例；
- **取整**：最大余数法，n_h ≤ N_h；再按 `minPerStratum=1` 从高配额层借调；
- **抽样**：`sha256(seed|record_id)` 升序取前 n_h，无放回、可复现；
- **偏差**：`bias = 样本层占比 − 总体层占比`；`maxAbsBias` 为最大绝对偏差；
- **约束**：最小样本 10 万条不满足时 `minTotalMet=false`，如实记录。

## 4. 复算与测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-stratified-sampling/tests -q
```

## 5. 已知限制

1. 无主题簇/质量等级时对应维度为 `MISSING`，分层粒度下降；
2. CV 用单位大小近似，未使用独立辅助变量；
3. 比例与最小样本阈值待业务确认（H-03）。

## 6. 版本与证据

`operatorVersion=0.1.0`、`modelVersion=null`、`treeVersion=null`；
证据目录 `operator/dm-stratified-sampling/output/evidence/<runId>/`。
