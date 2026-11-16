# 工作包回执 · S0-0 环境与样例准备

## 状态
完成（本机）；样例授权待人工确认（H-04）

## 完成项
- 固定解释器 D:/anaconda3/envs/use/python.exe（Python 3.12.12）
- 安装 ffmpeg 9.0.2（imageio-ffmpeg 静态构建，放入 env Scripts）
- 收集 7 个样例：文本/图像/音频×2/视频×2/PDF 扫描书；生成四模态混合 zip
- 记录来源、大小、SHA-256、授权状态

## 运行命令
```bash
python scripts/gen_sample_manifest.py
ffmpeg -version
python --version
```

## 证据路径
- 结果目录：E:/HYQX/数据配比/docs/算子开发/evidence/S0-0/run-20261116
- 指标文件：metrics.json
- 日志：logs/
- 样例输入：input-manifest.json

## 指标
| 指标 | 值 | 样本量 | 口径 | 证据 |
| --- | --- | --- | --- | --- |
| samples | 7 | — | 本机实测 | metrics.json |
| mixedZipBytes | 1120290 | — | 本机实测 | metrics.json |
| treeVersion | taxonomy-1013-pending | — | 本机实测 | metrics.json |

## 未决问题
- 内部素材授权未确认（H-04），仅内网联调
- ffprobe 未单独安装，S1 前补齐

## 下一步
按任务书 10.3 进入下一工作包；待人工项见任务书 10.8。
