# 合规词表（开源垫底）

- 文件：`sensitive-words-zh.txt`（UTF-8，每行一词，65,139 条）
- 上游：`houbb/sensitive-word`（Apache-2.0）`src/test/resources/dict_v20240407.txt`
  （取自 2024-04-07 版词典，65,143 条）
- 本地加工：剔除 4 条纯数字词条（`610`/`64`/`89`/`8964`）——算子匹配语义为子串
  包含，纯数字词条对任意含数字的正常文本全是误报；其余词条未做增删改。
- 获取方式：`cdn.jsdelivr.net/gh/houbb/sensitive-word@master/...`（2026-11-18），
  哈希与完整元数据见 `.meta.json`。
- 用途：OP-18 数据评测"合规"维度的**联调垫底词表**（Q-08，2026-11-18 用户口径：
  平台暂无正式合规资源，先用开源）。平台正式词表到位后，经运行参数
  `compliance_terms_path` 传入即可整体替换，无需改代码。
- 版权哈希库与原创性 API 仍待平台提供，缺失时对应分项如实标 `unavailable`。
- 许可证登记：`docs/算子开发/许可证清单.md`。
