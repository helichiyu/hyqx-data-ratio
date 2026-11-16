# 工作包回执 · S0-9 打包与最小压缩包

## 状态
完成（本机 dry-run + 打包）；独立 docker build 待人工（H-01）

## 完成项
- allowlist 单一来源；.dockerignore 与打包脚本共用
- 生成 dist/op-data-mixing-0.1.0.tar.gz，44230 字节，170 个文件
- 清单无 tests/dataset/output/docs/*.md/缓存；22 个 core.py
- 解压到空目录核对 map 22 条、必需文件齐全、无 _template

## 运行命令
```bash
bash scripts/package_docker_bundle.sh --version 0.1.0
tar -tzf dist/op-data-mixing-0.1.0.tar.gz
```

## 证据路径
- 结果目录：E:/HYQX/数据配比/docs/算子开发/evidence/S0-9/run-20261116
- 指标文件：metrics.json
- 日志：logs/
- 样例输入：input-manifest.json

## 指标
| 指标 | 值 | 样本量 | 口径 | 证据 |
| --- | --- | --- | --- | --- |
| bundleBytes | 44230 | — | 本机实测 | metrics.json |
| members | 170 | — | 本机实测 | metrics.json |
| coreFiles | 22 | — | 本机实测 | metrics.json |
| version | 0.1.0 | — | 本机实测 | metrics.json |

## 未决问题
- 空目录独立 docker build 待人工执行（H-01）

## 下一步
按任务书 10.3 进入下一工作包；待人工项见任务书 10.8。
