# 共享权重目录

> 权重本身不进 git；`SHA256SUMS` 进 git，Docker 构建期逐项校验。
> 约定见 `docs/算子开发/权重目录约定.md`。

```text
weights/
├── SHA256SUMS                 # 相对本目录的 SHA-256 清单（进 git）
├── shared/
│   ├── bge-base-zh-v1.5/      # 文本向量（OP-03/OP-05/OP-06/OP-20 共用）
│   └── paraformer-zh/         # 中文 ASR（OP-05/OP-11 共用）
└── <operatorId>/              # 单算子私有模型（当前为空）
```

## 模型登记

| 模型 | 路径 | 用途 | 版本 | 许可证 | 来源 |
| --- | --- | --- | --- | --- | --- |
| BAAI/bge-base-zh-v1.5 | `shared/bge-base-zh-v1.5/` | 文本/标签向量（768 维） | 2023-09 | MIT（可商用） | ModelScope `BAAI/bge-base-zh-v1.5`；原始仓库 <https://huggingface.co/BAAI/bge-base-zh-v1.5> |
| paraformer-zh | `shared/paraformer-zh/` | 中文语音转写 | FunASR 1.4.16 兼容 | Apache-2.0 | 内部参考仓 `平行语料/4个算子源码/音频转文本知识库相似度匹算子/models/paraformer-zh`；上游 <https://www.modelscope.cn/models/iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch> |

未采用：`m3e-base`（本地参考仓存在，但模型卡明确“非商用，仅供研究”，按任务书 2.4/3.6 不进入交付物）。

## 校验

```bash
cd operator/weights && sha256sum -c SHA256SUMS
```

镜像构建时 `Dockerfile` 在 `SHA256SUMS` 非空时自动执行同一命令；校验失败即构建失败。
运行期不得联网下载权重。
