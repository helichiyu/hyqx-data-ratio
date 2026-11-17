# OP-12 图像/视频属性（`dm-visual-analysis`）

- 语义编码：`corpus_profile_visual_attributes_v1`
- 阶段/优先级：S3 / P1
- 版本：`0.1.0`
- 模型：无（OpenCV/Pillow 规则），`opencv-heuristics-v1`

## 1. 用途与边界

**做**：图像香农熵、Laplacian 清晰度、亮度/对比度、色彩丰富度、主色；视频镜头切换与平均镜头时长、Farneback 光流动态/静态占比、关键帧时间。

**不做**：不做场景/目标/动作分类（无 CLIP/YOLO 权重，标 `unavailable`）；音画 BLEU 无字幕/参考时不计算；不做转码。

## 2. 接口与参数

`input_path` 为 OP-02 运行目录；媒体路径固定为 `standard/images/<rid>.webp`、`standard/video/<rid>.mp4`。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `max_records` | 100000 | 最多记录数 |

## 3. 指标口径

- **熵**：256 灰度直方图 `−Σ p·log2 p`；
- **清晰度**：Laplacian 方差；**色彩丰富度**：Hasler–Süsstrunk；
- **镜头**：相邻采样帧 HSV 直方图相关系数 <0.5 记一次切换；镜头数 = 切换数+1；
- **光流**：Farneback 平均幅值 >0.5 记为动态帧；
- **采样**：默认 2 fps，最多 600 帧；
- **不可用项**：场景/目标/动作/音画 BLEU 均返回 `unavailable` + reasonCode。

## 4. 复算与测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-visual-analysis/tests -q
```

## 5. 已知限制

1. OpenCV 构建可能缺 WebP 解码，图像统一用 Pillow 读取；
2. 镜头阈值与光流阈值为联调初值，快速剪辑/渐变转场可能漏检；
3. 无视频专项 UI，只产出指标与关键帧时间；
4. 场景/目标/动作模型需人工审批（H-06）。

## 6. 版本与证据

`operatorVersion=0.1.0`、`modelVersion=opencv-heuristics-v1`、`treeVersion=null`；
证据目录 `operator/dm-visual-analysis/output/evidence/<runId>/`。
