# -*- coding: utf-8 -*-
"""生成《数据配比中心算子开发清单》xlsx。

用法（本机 conda 环境，openpyxl 3.1.5）：
    D:\\anaconda3\\envs\\use\\python.exe docs\\工具脚本\\gen_算子清单.py

注意：Git Bash 里 `python` 会先命中 WindowsApps 的商店别名（PATH 中排在
D:\\anaconda3\\envs\\use 之前），所以建议直接写 python.exe 全路径。

范围提醒（2026-11-19）：OP-03/04/07/15/18/20/21/22 已删除，当前交付 14 个算子。
本脚本仍保留原始 22 个算子的生成逻辑；直接重跑会覆盖已裁剪的 xlsx。如需重新生成，
先同步更新本文件中的算子定义，或确认要恢复历史 22 行基线。
"""
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "算子开发", "【算子清单】数据配比中心算子开发清单_2026-11-16.xlsx")

HEADERS = ["序号", "算子ID", "大环节", "算子名称", "算子类型", "优先级", "能力说明", "处理逻辑",
           "前置依赖", "FGW条款", "原型位置", "输入数据", "输出数据", "失败处理", "约束边界",
           "技术关键处理方案", "平台/算子边界", "是否通用", "算子英文名", "模型/技术栈",
           "完成状态", "负责人", "交付时间", "备注/待确认"]

KEYS = ["seq", "id", "stage", "name", "type", "priority", "desc", "logic", "dep", "fgw", "proto",
        "inp", "out", "fail", "bound", "tech", "boundary", "common", "en", "stack",
        "status", "owner", "date", "note"]

DEFAULT = {
    "type": "模型型", "priority": "P1", "status": "未开始", "owner": "待定", "date": "待定",
    "common": "通用", "note": "",
    "fail": "单批失败记录原因码并返回失败清单，不阻断已成功批次；支持幂等重跑。",
    "bound": "单请求文件/记录数受平台上限约束；原始数据只读；结果必须带算子版本、模型版本（如适用）与参数哈希。",
    "boundary": "平台负责批次调度、存储、结果落库与展示；算子只对输入数据计算并返回结果/产物。",
}

ROWS = []


def add(**kw):
    row = dict(DEFAULT)
    row.update(kw)
    row["seq"] = len(ROWS) + 1
    ROWS.append(row)


# ============ ① 接入与解析 ============
add(id="OP-ING-01", stage="①接入与解析", name="模态识别", type="解析型/规则型", priority="P0",
    desc="判定每个文件/样本属于文本、图像、音频、视频中的哪些模态；一个数据集可含多模态，一个模态可有多种格式。",
    logic="读 magic/MIME + 扩展名 + 编码探测 + 容器流；目录/归档逐成员探测；混合文件按流/页拆分；输出模态、置信度与判定证据。",
    dep="批次登记完成、文件可访问", fgw="13.1-一", proto="数据接入·识别模态列 L2414-2424；详情 L2395",
    inp="文件清单/OSS 前缀、前 64KB-1MB 抽样、扩展名/MIME 声明", out="modal + confidence + 证据；各模态样本数/字节量；待人工确认清单",
    tech="文件头与容器流规则判定；低置信用轻量分类兜底，不用大模型；混合文件先拆流再分别识别。",
    stack="libmagic / ffprobe / chardet / uchardet / fastText",
    en="corpus_ingest_modality_detect_v1",
    note="必须支持“一个数据集多模态、一个模态多格式”；视频含音轨时同时输出 audio 子模态。",
    fail="无法判定标 unknown 并进人工确认；单文件失败不影响同批其他文件。",
    bound="只判定模态，不解析内容；不改变原文件；混合文件必须输出拆分建议。")

add(id="OP-ING-02", stage="①接入与解析", name="文本解析", type="解析型", priority="P0",
    desc="解析 TXT/JSONL/JSON/XML/PDF，抽取正文、段落、字号、页号、bbox，输出逐条记录与解析质量。",
    logic="按格式路由；PDF 抽文本层与版面，扫描页走 OCR；JSONL 流式容错；统计空文本率、乱码率、失败条数。",
    dep="模态识别判定为文本", fgw="13.1-一", proto="数据接入·文本分步 L1560 / L2402",
    inp="原始文件、字段映射、是否启用 OCR、分片参数", out="record_id/text/char_len、页号/段落/字号/bbox、解析质量指标、Parquet part 清单",
    tech="PDF 用 PyMuPDF/pdfplumber；TXT 编码探测+段落切分；JSONL 流式；扫描页 OCR + 版面分析；按页/行分片。",
    stack="PyMuPDF / pdfplumber / lxml / orjson / chardet / PaddleOCR / DocLayout-YOLO",
    en="corpus_ingest_parse_text_v1",
    note="PDF/OCR 建议单独算子，避免超时拖垮普通文本解析；同一文本模态可能包含多种格式。")

add(id="OP-ING-03", stage="①接入与解析", name="图像解析", type="解析型", priority="P0",
    desc="解析 JPG/PNG/BMP，提取分辨率、色彩空间、位深、DPI、压缩比、EXIF，产出 WebP 与 phash。",
    logic="读 header + EXIF，不解全图；OpenCV 做可解码校验；WebP 转码；phash 供去重与相似检索。",
    dep="模态识别判定为图像", fgw="13.1-一", proto="数据接入·图像分步 L1561；画像 L1864",
    inp="图像文件/压缩包、EXIF/ICC 开关、WebP 质量与长边上限", out="逐图特征、EXIF、可解码标记、WebP、phash、分辨率/色彩分布",
    tech="Pillow 仅读 header；exifread/piexif 取 EXIF；ICC Profile 解析；OpenCV 校验；imagehash.phash。",
    stack="Pillow / OpenCV / exifread / imagehash",
    en="corpus_ingest_parse_image_v1")

add(id="OP-ING-04", stage="①接入与解析", name="音频解析", type="解析型", priority="P0",
    desc="解析 WAV/MP3/FLAC，提取采样率、声道、码率、时长，转 16k 单声道，生成梅尔谱与 VAD。",
    logic="ffprobe 读流信息；ffmpeg/soxr 重采样；librosa 生成梅尔谱；VAD 算有效语音时长与静音比。",
    dep="模态识别判定为音频", fgw="13.1-一", proto="数据接入·音频分步 L1562；画像 L1865",
    inp="音频文件、目标采样率/声道、梅尔参数、VAD 开关", out="音频属性、16k mono WAV、梅尔谱、有效语音时长/静音比、失败清单",
    tech="ffprobe + ffmpeg/soxr + librosa + silero-vad；长音频按 5-10 分钟切片并行后拼接。",
    stack="ffmpeg / soxr / librosa / silero-vad",
    en="corpus_ingest_parse_audio_v1")

add(id="OP-ING-05", stage="①接入与解析", name="视频拆流与抽帧", type="解析型", priority="P0",
    desc="解析 MP4/MOV，分离音视频流，转 H.264，按场景抽关键帧，输出帧-时间戳关联。",
    logic="ffprobe 读流；ffmpeg 分流；场景检测抽帧；音轨转音频解析；保留帧 ID/时间戳/所属视频 ID。",
    dep="模态识别判定为视频", fgw="13.1-一", proto="数据接入·视频分步 L1563；L1546",
    inp="视频文件、抽帧策略、转码参数、分片时长", out="视频属性、H.264、关键帧+时间戳、音轨、帧-视频-音频片段关联键",
    tech="ffprobe + ffmpeg + PySceneDetect；长视频按 5 分钟切片并行后合并时间轴。",
    stack="ffmpeg / PySceneDetect / libx264",
    en="corpus_ingest_parse_video_v1",
    note="音轨不在此重写，转音频解析算子；关键帧同时供图像打标/画像复用。")

add(id="OP-ING-06", stage="①接入与解析", name="标准化与元数据索引", type="解析型/统计型", priority="P0",
    desc="把四模态产物写标准容器（Parquet/WebP/WAV/H.264），生成元数据宽表与索引文件，供全链路复用。",
    logic="固定 schema 写 Parquet；按模态-来源-时间分区；生成 manifest；抽取元数据；建索引；输出路径=输入指纹+算子版本+参数哈希实现幂等。",
    dep="四模态解析完成", fgw="13.1-二", proto="标准化路径 L2410；列表进度 L2344",
    inp="解析产物、目标格式、分区规则、索引字段与类型", out="标准产物、manifest、元数据宽表、索引文件、字段缺失清单、失败清单",
    tech="pyarrow 流式写 Parquet+zstd；Pillow WebP；ffmpeg WAV/MP4；元数据落 ES/ClickHouse/DuckDB；幂等路径。",
    stack="pyarrow / ffmpeg / Pillow / Elasticsearch / ClickHouse / DuckDB",
    en="corpus_ingest_standardize_meta_v1",
    note="可拆“标准化写容器”和“元数据/索引”两个算子；建议拆，便于重分区/回刷。",
    fail="单分片失败保留 manifest 与失败清单，可重跑；不产生半成品。",
    bound="只写标准产物与元数据，不移动正式存储、不更新平台台账。")

add(id="OP-ING-07", stage="①接入与解析", name="去重与异常样本识别", type="规则型", priority="P1",
    desc="精确/近似去重与无效样本识别：MD5/SHA256、SimHash/MinHash、空文本、坏图、静音、黑帧、零时长。",
    logic="两级哈希；近重复 LSH；按模态规则质检；输出重复组、异常原因码、可释放字节。",
    dep="标准化产物/元数据", fgw="13.1-二/四", proto="标准化路径 L2410（仅静态 chip）",
    inp="标准产物、已有哈希索引、阈值配置", out="重复组、异常清单、原因码、重复率/异常率、可释放字节",
    tech="hashlib 流式哈希；SimHash+MinHashLSH；imagehash.phash；chromaprint；DuckDB/Spark 聚合。",
    stack="Python / SimHash / MinHashLSH / imagehash",
    en="corpus_ingest_dedup_quality_v1",
    note="精确去重与近重复/异常可拆两个算子；隔离/剔除动作归平台。")

add(id="OP-ING-08", stage="①接入与解析", name="分区与跨模态关联", type="规则型", priority="P1",
    desc="计算 modal/source/dt 分区键与格式分组，构建“视频帧 ID-音频片段 ID-文本描述 ID”跨模态关联表。",
    logic="来源映射归一；时间取采集/文件时间；按模态+编码分组；按时间戳/帧号对齐三模态。",
    dep="标准化产物、来源映射表", fgw="13.1-二/三", proto="数据分片卡片 L1556；详情 L2410",
    inp="样本元数据、来源映射、时间粒度、跨模态时间戳", out="分区路径、格式分组、关联表、分区条数/字节统计",
    tech="DuckDB/pyarrow groupby；时间戳对齐；规则型，无模型。",
    stack="DuckDB / pyarrow",
    en="corpus_ingest_partition_link_v1",
    note="分区键可并入标准化算子；跨模态关联表是 FGW 明确要求，原型未实现。")

add(id="OP-ING-09", stage="①接入与解析", name="源库增量拉取", type="I/O型", priority="P1",
    desc="按源库地址/数据表/游标增量拉取，输出批次文件+manifest+新游标，支持断点续传。",
    logic="JDBC keyset、S3 Range、HTTP Range；增量 watermark；batch_id 幂等；失败分类与指数退避。",
    dep="源库连接与凭据", fgw="13.1-一", proto="检查点恢复 L6977-7038",
    inp="连接信息、表/前缀、游标字段与上次值、batchSize、增量水位", out="批次文件、manifest、新游标、失败原因分类",
    tech="JDBC keyset 分页、boto3 list/GetObject Range、requests Range；重试指数退避。",
    stack="Java/Python 连接器 / S3 SDK",
    en="corpus_ingest_source_pull_v1",
    note="I/O 型；若平台连接器已实现可下沉平台，不单独做算子。")

# ============ ② 分片与打标 ============
add(id="OP-SHP-01", stage="②分片与打标", name="句向量与主题聚类", type="模型型/统计型", priority="P0",
    desc="文本分句/分块→bge 句向量→K-Means 聚类，用轮廓系数选 K，输出簇、主题词与参数快照。",
    logic="512 token 切窗、重叠 64；batch 编码+L2 归一；MiniBatchKMeans；候选 K 评估；c-TF-IDF 主题词。",
    dep="标准化文本", fgw="13.1-三", proto="数据分片卡片 L1556；L2357-2362",
    inp="文本记录、模型标识、切句/窗口参数、K 范围、seed", out="句向量矩阵、最优 K/轮廓系数、record→cluster、簇规模/主题词、参数快照",
    tech="bge-base-zh/bge-m3 + sentence-transformers；scikit-learn/faiss MiniBatchKMeans；silhouette_score。",
    stack="bge / sentence-transformers / scikit-learn / FAISS",
    en="corpus_shard_embed_cluster_v1",
    note="向量与聚类可拆两个算子；向量可复用给打标、FAISS、近重复检测。")

add(id="OP-SHP-02", stage="②分片与打标", name="分层抽样", type="统计型/规则型", priority="P1",
    desc="按来源×主题×质量分层，Neyman 分配配额并执行抽样，输出配额、样本清单、层代表性偏差。",
    logic="n_h=n·(N_h·CV_h)/Σ；总样本约束 5-10%/20-30%、≥10 万；固定 seed；层内加权无放回。",
    dep="元数据/主题簇/质量等级", fgw="13.1-四", proto="分层抽样配置 L1565/L2380",
    inp="分层字段、各层 N/CV、比例、最小样本、seed", out="层配额、样本清单、实抽比例、代表性偏差、未达标层",
    tech="DuckDB/Spark stratified sample；Neyman 分配；哈希取模保证可复现。",
    stack="DuckDB / Spark / pandas",
    en="corpus_shard_stratified_sample_v1")

add(id="OP-LBL-01", stage="②分片与打标", name="文本自动初标", type="模型型", priority="P0",
    desc="文本层级分类，输出“文本-一级-二级-细分”可变深度路径 + 置信度 + topK。",
    logic="一级 softmax 后条件分类；长文本分块投票；温度校准；低置信分桶供未归类。",
    dep="标准化文本、类型树快照", fgw="12.2-6/8", proto="数据打标列表 L1810-1821",
    inp="文本、类型树、阈值/topK/最大深度", out="路径、置信度、topK、模型/树版本、低置信标记",
    tech="BERT/RoBERTa-zh 微调；LLM few-shot 兜底难样本；层级约束解码；置信度校准。",
    stack="BERT / RoBERTa-zh / Qwen 小模型",
    en="corpus_label_text_v1")

add(id="OP-LBL-02", stage="②分片与打标", name="图像自动初标", type="模型型", priority="P0",
    desc="图像层级分类，输出“图像-一级-二级-细分”路径 + 置信度；覆盖文档/证照/图表/医学/遥感等分支。",
    logic="ViT/ConvNeXt 微调 + CLIP zero-shot 长尾；文档页先 OCR 判扫描件；多标签阈值裁剪。",
    dep="标准化图像、类型树", fgw="12.2-6/8", proto="数据打标图像行 L1813",
    inp="图像、类型树、可选弱文本（文件名/alt/来源）、阈值/topK", out="路径、置信度、topK、多标签结果、模型/树版本",
    tech="ConvNeXt/ViT 微调；CLIP zero-shot 兜底；文档页 PaddleOCR 文本密度判定。",
    stack="PyTorch / ConvNeXt / ViT / CLIP / PaddleOCR",
    en="corpus_label_image_v1")

add(id="OP-LBL-03", stage="②分片与打标", name="音频自动初标", type="模型型", priority="P0",
    desc="音频层级分类：语音/音乐/环境音/事件音，语音场景、人声属性、语种方言，与文本/图像同级。",
    logic="音频事件分类；语音先 ASR 辅助语义；语种/方言；音乐/人声分离后分类；多标签输出。",
    dep="标准化音频、类型树", fgw="12.2-6/8", proto="数据打标音频行 L1814",
    inp="音频、类型树、可选元数据、语种阈值", out="路径、置信度、ASR 文本、语种/方言、低置信分桶",
    tech="PANNs/AST/CLAP 音频事件；Whisper/Paraformer ASR；emotion2vec 情绪；语种模型。",
    stack="PyTorch / PANNs / AST / Whisper / FunASR",
    en="corpus_label_audio_v1",
    note="所有模态一视同仁：音频打标必须与文本/图像同级，不能只放在“建议”档。")

add(id="OP-LBL-04", stage="②分片与打标", name="视频自动初标", type="模型型", priority="P0",
    desc="视频层级分类：短视频/纪实/动作/交通/安防/专业过程；关键帧+音轨+ASR 三路融合。",
    logic="关键帧 CLIP + 音轨 CLAP + ASR 文本三路分类；场景切分按时长加权投票；长视频分段处理。",
    dep="标准化视频+音轨+ASR", fgw="12.2-6/8", proto="数据打标视频行 L1815/L1819",
    inp="视频、关键帧、音轨、字幕/ASR、类型树", out="路径、置信度、topK、模型/树版本",
    tech="VideoMAE/SlowFast 动作识别；CLIP 帧分类；CLAP 音轨；Whisper ASR；三路加权。",
    stack="PyTorch / VideoMAE / CLIP / CLAP / Whisper",
    en="corpus_label_video_v1",
    note="原型把“物理课堂实录”标成“办公室会议”，说明不能靠文件名，必须真实推理。")

add(id="OP-LBL-05", stage="②分片与打标", name="领域多标签", type="模型型", priority="P1",
    desc="领域多标签分类，输出 16 行业树的多路径+分数，支持任意层级、跨领域分别计入。",
    logic="多标签层次分类；embedding 相似度或微调；阈值裁剪；非文本用关联文本/转写。",
    dep="打标文本/ASR/OCR、领域树", fgw="12.2-6", proto="数据打标领域列 L1832/L2836",
    inp="文本/转写、领域树、阈值/topK", out="领域多路径+分数、未明确标记、模型/树版本",
    tech="BERT 多标签或 bge 向量+kNN；层级约束；LLM few-shot 兜底。",
    stack="BERT / bge-m3",
    en="corpus_label_domain_v1")

add(id="OP-LBL-06", stage="②分片与打标", name="能力多标签", type="模型型", priority="P1",
    desc="能力多标签分类：判断样本对语言理解/生成、代码、感知、生成等能力项的训练价值。",
    logic="能力项描述向量+样本向量相似；LLM 逐项 0-3 分；规则特征（代码块/QA/公式/图文配对）。",
    dep="文本/转写/图像描述、能力树", fgw="12.2-6/12.3", proto="数据打标能力列 L1832/L2837",
    inp="样本内容、能力树、阈值/topK", out="能力多路径+分数、证据片段、模型/树版本",
    tech="bge-m3 + LLM few-shot；规则特征融合；阈值化。",
    stack="bge-m3 / LLM",
    en="corpus_label_ability_v1")

add(id="OP-LBL-07", stage="②分片与打标", name="标签校验与未归类识别", type="规则型/模型型", priority="P1",
    desc="服务端校验标签路径合法性（存在/末级/深度/同义/父子冲突），并把低置信/冲突/新场景样本放入未归类池。",
    logic="树快照+规则引擎；置信阈值/margin/OOD/聚类离群；输出原因、最近节点、建议父路径。",
    dep="打标结果、类型树", fgw="12.2-4/5/6/7/9", proto="修改标签弹窗 L3183；未归类池 L2045",
    inp="标签记录、树快照、阈值", out="合法/非法、修正路径、冲突对；未归类原因、最近节点、建议父路径",
    tech="规则引擎+编辑距离/同义词表；bge 近邻/OOD 检测。",
    stack="Python 规则 / bge-m3",
    en="corpus_label_validate_outlier_v1",
    note="校验与未归类可拆两个算子；人工归类/扩树归平台。")

add(id="OP-LBL-08", stage="②分片与打标", name="打标质量评估", type="统计型", priority="P1",
    desc="用人工审核记录评估自动打标质量：准确率、采纳率、修改率、覆盖率、混淆矩阵、Kappa。",
    logic="路径前缀/祖先等价归一；分层抽样；Wilson 区间；混淆矩阵；双人 Kappa。",
    dep="自动打标结果、人工审核记录", fgw="12.2-7/10", proto="打标 KPI L2778；卡片4 L2104",
    inp="自动标签、人工标签、树快照、抽样比例", out="准确率/F1/采纳率/修改率/覆盖、混淆矩阵、Kappa、置信区间",
    tech="sklearn classification_report；分层抽样；Cohen/Fleiss Kappa。",
    stack="pandas / scikit-learn",
    en="corpus_label_quality_v1",
    note="没有真实人工审核记录时只能标“待补数据”，不能用常量冒充。")

add(id="OP-LBL-09", stage="②分片与打标", name="治理属性建议", type="模型型/规则型", priority="P2",
    desc="敏感度/价值/关联度建议值：PII/敏感内容、知识密度/稀缺度、与业务目标匹配度，人工确认。",
    logic="正则+NER+人脸/证件检测；价值评分；领域/能力路径匹配；输出建议与依据。",
    dep="打标/画像结果、治理规则", fgw="12.2（治理口径）", proto="治理标签 L1856；编辑弹窗 L3077",
    inp="文本/ASR/OCR/图像、目标能力/领域、词表", out="三档建议+分项得分+命中证据",
    tech="PII NER/正则、人脸检测、价值加权评分、树路径匹配。",
    stack="PII-BERT / uie / RetinaFace / 规则",
    en="corpus_label_governance_v1",
    note="原型为纯人工下拉；是否做建议值待产品确认，优先级 P2。")

# ============ ③ 语料画像 ============
add(id="OP-PRF-01", stage="③语料画像", name="规模与结构统计", type="统计型", priority="P0",
    desc="统计各模态条目数、字符/时长/帧数、平均/中位长度、分辨率/采样率分布、存储量、压缩比、模态占比。",
    logic="流式扫描标准产物；t-digest 分位数；UTF-8 字节；按模态聚合。",
    dep="标准化产物/元数据", fgw="13.2-1", proto="规模与结构 L1862；L3313-3317",
    inp="标准产物/元数据、模态、统计维度", out="条目/字符/时长/帧数、分位数、存储/压缩比、模态占比",
    tech="DuckDB/Spark 聚合；t-digest/DDSketch；ffprobe/Pillow 补元数据。",
    stack="DuckDB / Spark / t-digest",
    en="corpus_profile_scale_v1")

add(id="OP-PRF-02", stage="③语料画像", name="来源归类与可信度评分", type="规则型/统计型", priority="P0",
    desc="样本级来源归类（六类）+ 来源可信度 AHP（权威 40/透明 30/更新 20/评价 10）。",
    logic="域名/DOI/ISBN/代码特征规则；低置信 fastText；四项归一+加权+CR 一致性校验。",
    dep="采集元数据、来源台账", fgw="13.2-2/3", proto="来源可信度 L1868；卡片1 L2084",
    inp="URL/域名/授权/标注/更新时间/评价", out="来源标签+置信度、六类占比、四项分+总分+CR",
    tech="规则映射+fastText；AHP+min-max；贝叶斯平滑评价分。",
    stack="Python / fastText",
    en="corpus_profile_source_credibility_v1",
    note="原型只有 3 类来源常量；FGW 要求六类，需扩映射表。")

add(id="OP-PRF-03", stage="③语料画像", name="领域覆盖分析", type="模型型/统计型", priority="P1",
    desc="预测样本领域路径，统计各领域占比与四种口径覆盖率、未覆盖/低覆盖清单。",
    logic="领域多标签分类（复用 LBL-05）；按树 rollup；覆盖率=命中节点/目标节点。",
    dep="领域标签、领域树、目标清单", fgw="13.2-4", proto="主题覆盖 L2135；领域分析 L6632",
    inp="样本领域标签、领域树、覆盖口径", out="领域占比、覆盖率、未覆盖/低覆盖清单、未明确占比",
    tech="复用领域分类；SQL/pandas 聚合；四种口径分别 rollup。",
    stack="BERT / bge / pandas",
    en="corpus_profile_domain_coverage_v1")

add(id="OP-PRF-04", stage="③语料画像", name="语种与方言识别", type="模型型", priority="P0",
    desc="语种识别与方言判别，置信度<0.85 标混合/未识别；语音先 ASR、图像先 OCR。",
    logic="fastText/CLD3 语种；方言特征词+声学；低置信分桶；按语种聚合。",
    dep="文本/ASR/OCR", fgw="13.2-5", proto="语言分布 L1873；风险 RK-005 L1893",
    inp="文本/转写、阈值、方言词表", out="语种/方言+置信度、混合/未识别标记、分布",
    tech="fastText lid.176/CLD3；方言特征词；口音用 x-vector（可选）。",
    stack="fastText / CLD3",
    en="corpus_profile_language_id_v1")

add(id="OP-PRF-05", stage="③语料画像", name="地域推断", type="规则型/模型型", priority="P2",
    desc="通过 IP/正文地域词/EXIF GPS/时区推断来源地域，输出国家/省级分布供热力图。",
    logic="ip2region；GeoNames+NER；EXIF GPS；多路证据加权。",
    dep="采集 IP/正文/元数据", fgw="13.2-5", proto="语言风格 region 列 L2165",
    inp="IP、正文、GPS/时区", out="国家/省级+置信度+证据",
    tech="ip2region、GeoNames、NER、时区映射。",
    stack="ip2region / GeoNames",
    en="corpus_profile_geo_infer_v1",
    note="原型无真实入口；P2。")

add(id="OP-PRF-06", stage="③语料画像", name="时间抽取与新鲜度", type="规则型/统计型", priority="P0",
    desc="抽取发布时间/拍摄时间/正文时间表达，统计年季分布，计算新鲜度指数（0.6/0.3/0.1），<0.4 预警。",
    logic="元数据时间优先；正文时间词归一；分桶加权；强时效领域单独算过时率。",
    dep="元数据/正文/领域标签", fgw="13.2-6", proto="时间新鲜度 L1877；RK-004 L1892",
    inp="时间戳、正文、领域、基准日", out="时间区间、年季分布、新鲜度指数、过时风险",
    tech="dateparser/HeidelTime/时间词规则；分桶加权公式。",
    stack="dateparser / HanLP 时间词",
    en="corpus_profile_freshness_v1")

add(id="OP-PRF-07", stage="③语料画像", name="文本属性分析", type="模型型/统计型", priority="P0",
    desc="文本属性：句长、从句嵌套深度、被动句占比、TTR/词汇密度、体裁/语体。",
    logic="分句/分词/依存句法；规则识别被动；TTR/MSTTR/MTLD；语体分类。",
    dep="文本", fgw="13.3-1", proto="语料属性指标 L1878；L3340-3343",
    inp="文本、分词/句法模型、停用词表", out="句长/嵌套/被动比例、TTR/密度、体裁/语体、分布",
    tech="HanLP/LTP/Stanza 依存句法；jieba；RoBERTa 语体分类。",
    stack="HanLP / LTP / jieba / RoBERTa",
    en="corpus_profile_text_attributes_v1")

add(id="OP-PRF-08", stage="③语料画像", name="语音质量与 WER", type="模型型/统计型", priority="P1",
    desc="ASR 转写、WER/CER、语速、基频、停顿、口音；WER>20% 标低质量语音。",
    logic="ASR；文本归一化；编辑距离；VAD 有效时长；声学特征。",
    dep="音频、参考文本（可选）", fgw="13.3-1", proto="WER L1887；语速 L1880；RK-002 L1890",
    inp="音频、参考转写、ASR 模型、阈值", out="转写、WER/CER、语速、基频/停顿、低质量清单",
    tech="Whisper/Paraformer ASR；jiwer；praat/parselmouth；pyannote VAD。",
    stack="Whisper / FunASR / jiwer / praat",
    en="corpus_profile_speech_quality_v1",
    note="ASR 可复用给音频打标；无参考文本时只出置信度/困惑度，不冒充 WER。")

add(id="OP-PRF-09", stage="③语料画像", name="图像属性分析", type="模型型/统计型", priority="P1",
    desc="图像场景分类、目标检测、场景多样性香农熵、色彩/分辨率分布。",
    logic="Places365/CLIP 场景；YOLO 检测；熵公式；按模态聚合。",
    dep="图像", fgw="13.3-1", proto="香农熵 L1880",
    inp="图像、场景体系、检测模型", out="场景标签、目标频次、熵、色彩/分辨率分布",
    tech="CLIP/ResNet 场景分类；YOLOv8/Detectron2 检测；numpy 熵。",
    stack="CLIP / ResNet / YOLOv8",
    en="corpus_profile_image_attributes_v1")

add(id="OP-PRF-10", stage="③语料画像", name="视频属性分析", type="模型型/统计型", priority="P1",
    desc="镜头切换/平均时长、动态静态光流、音画对齐 BLEU、动作类别覆盖。",
    logic="镜头检测；光流；ASR/字幕 BLEU；动作识别。",
    dep="视频+音轨+ASR/字幕", fgw="13.3-1", proto="仅平均帧率 L1865（缺口）",
    inp="视频、关键帧、ASR/字幕、动作体系", out="镜头数/切换频率、动态占比、BLEU、动作覆盖",
    tech="PySceneDetect/TransNetV2；RAFT/Farneback；sacrebleu；VideoMAE/SlowFast。",
    stack="PySceneDetect / RAFT / sacrebleu / VideoMAE",
    en="corpus_profile_video_attributes_v1",
    note="原型没有视频专项卡；FGW 要求，建议补 UI。")

add(id="OP-PRF-11", stage="③语料画像", name="任务适配性评分", type="规则型/模型型", priority="P1",
    desc="六维任务适配 0-10：语言理解/生成、代码生成、多模态推理、知识问答、对话交互。",
    logic="结构完整性 40/语义复杂 30/领域相关 30；QA 结构、因果词、代码沙箱、CLIP 图文、对话轮次。",
    dep="文本/代码/图文、领域标签", fgw="13.3-2", proto="雷达图 L1882；L3345-3347",
    inp="样本、评分权重、校准集（可选）", out="六维分数+子指标+低适配样本",
    tech="规则 rubric+LightGBM/LLM 校准；tree-sitter；Docker 沙箱；CLIP。",
    stack="Python 规则 / LightGBM / CLIP",
    en="corpus_profile_task_fit_v1")

add(id="OP-PRF-12", stage="③语料画像", name="知识覆盖与层次", type="模型型/统计型", priority="P1",
    desc="知识覆盖与层次：实体/术语覆盖率、知识密度、事实/推理/创意占比、知识层级断点。",
    logic="NER+实体链接；术语词表 AC；密度=术语/总词；层次分类；分位分层。",
    dep="文本、知识图谱/术语表", fgw="13.3-3", proto="知识指标 L1886；卡片9 L2142",
    inp="文本、KG/实体表、术语表、阈值", out="覆盖率、密度、三类占比、层级/断点",
    tech="HanLP NER+BLINK/向量链接；Aho-Corasick；层次分类。",
    stack="HanLP / BLINK / AC 自动机",
    en="corpus_profile_knowledge_v1")

add(id="OP-PRF-13", stage="③语料画像", name="质量与一致性分析", type="统计型/模型型", priority="P0",
    desc="完整率、跨文档冲突率、基尼系数、低频实体、跨模态一致性、标注覆盖。",
    logic="字段校验；实体链接+属性比对；基尼公式；低频计数；CLIP/ASR 对齐。",
    dep="元数据/实体/领域/标注记录", fgw="13.3-4", proto="质量卡 L1887；卡片10 L2149；卡片3 L2098",
    inp="字段/实体/属性/领域/标注", out="完整率热力图、冲突清单/冲突率、基尼、低频清单、覆盖率",
    tech="规则校验；实体消歧；基尼；CLIP/ASR 一致性。",
    stack="pandas / BLINK / CLIP",
    en="corpus_profile_quality_consistency_v1")

add(id="OP-PRF-14", stage="③语料画像", name="难度与正负导向", type="模型型/统计型", priority="P2",
    desc="难度四档（容易/中等/困难/极难）与正/负/中性导向占比、平衡度。",
    logic="小模型 PPL/损失分位分档；情感/安全分类器；平衡度=1-|p-q|。",
    dep="样本、参考模型、极性模型", fgw="13.3-2/Comic", proto="卡片6 L2117",
    inp="样本、PPL 模型、极性模型、分档阈值", out="四档占比、正负占比、平衡度、失衡清单",
    tech="Qwen2.5-0.5B PPL；RoBERTa 情感/安全分类；分位数分档。",
    stack="Qwen2.5-0.5B / RoBERTa",
    en="corpus_profile_difficulty_polarity_v1",
    note="Comic 口径，FGW 未单列；P2。")

add(id="OP-PRF-15", stage="③语料画像", name="热点长尾与语言风格", type="模型型/统计型", priority="P1",
    desc="热点主题/长尾缺口、语体占比、术语覆盖率、适配建议。",
    logic="BERTopic/KeyBERT 热点；频次分位长尾；语体分类；术语词表；规则建议。",
    dep="主题簇/文本/术语表/目标清单", fgw="13.3-3/Comic", proto="卡片11/12 L2156/L2165",
    inp="文本、时间、主题/术语表、目标清单", out="热点主题/热度、长尾缺口、语体占比、术语覆盖、建议",
    tech="BERTopic/KeyBERT；RoBERTa 语体；AC 术语匹配；规则生成建议。",
    stack="BERTopic / KeyBERT / RoBERTa",
    en="corpus_profile_hotspot_style_v1")

# ============ ④ 配比引擎 ============
add(id="OP-RAT-01", stage="④配比引擎", name="数据源结构与六类占比", type="规则型/统计型", priority="P0",
    desc="样本级六类来源归类与加权占比；来源×标签交叉表；配比 A/B 来源结构。",
    logic="来源规则+fastText；权重=可信度/治理指令；Σ条数×权重/Σ全部。",
    dep="来源标签、来源权重", fgw="12.1-1/3", proto="来源权重 L1973；卡片1 L2084",
    inp="样本来源/条数/token、权重", out="六类占比、加权占比、来源×标签交叉、A/B 对比",
    tech="规则+fastText；加权聚合；DuckDB/Spark。",
    stack="Python / DuckDB",
    en="ratio_source_structure_v1")

add(id="OP-RAT-02", stage="④配比引擎", name="加权配比与归一化", type="规则型", priority="P0",
    desc="标签级加权配比计算与无损归一化，输出条数/权重/占比三列与投喂条数。",
    logic="权重=采样频率×来源权重×偏见降权×角色/阶段；最大余数法；0.1% 精度；长尾不置零。",
    dep="标签库存、来源权重、目标规模", fgw="12.3-2/12.4", proto="配比编辑 L3870；归一化 L4029",
    inp="标签条数/token、权重、目标规模", out="target%、投喂条数、权重明细、残差记录",
    tech="Python 规则；最大余数法；约束最小二乘（可选）。",
    stack="Python / OR-Tools",
    en="ratio_weighted_plan_v1",
    note="纯规则，可下沉后端；建议保留独立服务以便审计复算。")

add(id="OP-RAT-03", stage="④配比引擎", name="规则校验与库存折算", type="规则型/统计型", priority="P0",
    desc="高频≥30%、一二级覆盖 100%、合计 100%、最小样本、库存/规模折算与缺口。",
    logic="按树逐节点集合覆盖；核心标签集前缀匹配；库存=target%×总规模；缺口量。",
    dep="配比明细、标签树、库存", fgw="12.3-3/4", proto="KPI 行 L3899；库存列 L3924",
    inp="配比明细、树、核心标签集、库存、阈值", out="校验单、未覆盖类别、缺口量、可满足性",
    tech="规则引擎；树 rollup；tokenizer 抽样折算。",
    stack="Python / DuckDB",
    en="ratio_validate_inventory_v1")

add(id="OP-RAT-04", stage="④配比引擎", name="能力预测与领域覆盖", type="规则型/统计型", priority="P1",
    desc="标签→能力/领域映射，按配比加权预测六维能力与领域覆盖。",
    logic="标签-能力/领域矩阵；按 target 加权；领域 rollup；有历史数据可拟合 surrogate。",
    dep="标签映射、配比", fgw="12.4-5/12.1-2", proto="能力预测 L3658；领域覆盖 L6448",
    inp="配比、映射库、历史实验（可选）", out="六维能力分+贡献度、领域占比/未覆盖",
    tech="专家矩阵/岭回归/GBDT；bge 映射。",
    stack="Python / scikit-learn",
    en="ratio_capability_domain_v1")

add(id="OP-RAT-05", stage="④配比引擎", name="按目标能力推荐配比", type="优化型", priority="P1",
    desc="按目标能力集合反解配比，满足 100%/30%/覆盖/库存约束，输出建议与改动量。",
    logic="线性规划/投影梯度；目标最大化能力分；无解软约束并报告。",
    dep="映射、库存、当前配比", fgw="12.3-2/12.4-4", proto="推荐弹窗 L6420",
    inp="目标能力+权重、映射、库存、阈值", out="建议 target%、预期提升、约束满足、改动量",
    tech="OR-Tools/scipy linprog；软约束松弛。",
    stack="OR-Tools / scipy",
    en="ratio_recommend_v1")

add(id="OP-RAT-06", stage="④配比引擎", name="缺口补数建议", type="规则型/统计型", priority="P1",
    desc="缺口补数：推荐来源、补样量、优先级，补数后回写复算。",
    logic="来源×标签覆盖矩阵打分；补样量=目标规模×缺口%/(折算×可用率×去重率)；优先级加权。",
    dep="缺口、来源覆盖、库存/成本", fgw="12.3-5/12.4-3", proto="去补数 L6000",
    inp="缺口、来源×标签覆盖、库存、成本、目标规模", out="来源 TopN+理由、补样量、优先级、补齐预测",
    tech="线性打分/协同过滤；量级测算。",
    stack="Python",
    en="ratio_refill_advice_v1")

add(id="OP-RAT-07", stage="④配比引擎", name="达成度、偏见与薄弱标签", type="统计型/规则型", priority="P1",
    desc="达成度（目标 vs 实际）、偏见指标（集中度/熵/JS/毒性）、薄弱标签识别。",
    logic="按标签 rollup 实际占比；达成率/差值；分布偏斜指标；薄弱标签=低占比/低准确率。",
    dep="投喂/组装记录、画像结果", fgw="12.3-5/12.4-2", proto="达成度 L2071；权重 L1973",
    inp="目标、实际、来源/语种/群体标签、毒性", out="达成率/差值/状态、偏见指标、问题来源、薄弱标签建议",
    tech="pandas/DuckDB；毒性分类器；熵/JS 散度。",
    stack="pandas / RoBERTa 毒性",
    en="ratio_achievement_bias_v1")

add(id="OP-RAT-08", stage="④配比引擎", name="通用专业权衡与多方案对标", type="规则型/优化型", priority="P2",
    desc="通用/专业权衡、应用类型建议模板、N 方案对比矩阵与帕累托前沿。",
    logic="约束优化；模板规则；参数采样；多目标打分/NSGA-II 简化。",
    dep="配比、能力/覆盖/库存/偏见结果", fgw="12.1-4/5、12.4-1/4", proto="方案设置 L3882（原型弱）",
    inp="旋钮范围、底座、约束、历史方案", out="通用/专业占比、权衡曲线、N 方案矩阵、帕累托、推荐",
    tech="网格/拉丁超立方；TOPSIS/非支配排序。",
    stack="Python",
    en="ratio_tradeoff_compare_v1",
    note="原型无对标视图，P2；Comic 有“多套推荐方案”，可后端占位。")

# ============ ⑤ 生产评测 ============
add(id="OP-PRD-01", stage="⑤生产评测", name="组装选样", type="统计型/规则型", priority="P0",
    desc="按配方配额从语料池分层选样，输出样本清单与层偏差。",
    logic="配额；Neyman/加权无放回；固定 seed；按目录分片调用后合并。",
    dep="配方、库存、分层字段", fgw="13.1-四/12.3", proto="组装任务 L4419",
    inp="配方明细、库存、分层、seed", out="样本清单、层实抽/配额、偏差、seed",
    tech="DuckDB/Spark；Alias/A-Res 加权抽样；哈希取模；固定 seed 可复现。",
    stack="DuckDB / Spark",
    en="prod_assembly_sample_v1")

add(id="OP-PRD-02", stage="⑤生产评测", name="成品打包与清单", type="解析型/I/O型", priority="P0",
    desc="按选样清单读源文件，写成品 Parquet 分区，生成 manifest 与校验和。",
    logic="流式读写；按 modal/source/dt 分区；MD5/SHA-256；断点续跑；幂等。",
    dep="选样清单", fgw="13.1-二/三", proto="下载 L4477",
    inp="选样清单、源文件、分区/格式/压缩参数", out="成品文件、manifest、校验和、汇总",
    tech="pyarrow 流式读写；zstd；SHA-256；按 manifest 断点续跑。",
    stack="pyarrow",
    en="prod_package_dataset_v1")

add(id="OP-PRD-03", stage="⑤生产评测", name="评测抽样与标签准确率", type="统计型/模型型", priority="P0",
    desc="5-10% 分层抽样，重新预测标签，算准确率/F1/混淆矩阵/错标清单。",
    logic="分层抽样；复用打标模型；路径精确/前缀匹配；宏平均；Wilson 区间。",
    dep="成品 manifest、真值、打标模型", fgw="13.3-一/12.2", proto="数据评测 L4453",
    inp="成品、真值、抽样比例、模型", out="抽样清单、准确率/F1、混淆矩阵、错标清单",
    tech="复用 LBL 模型；sklearn；分层抽样；Wilson 置信区间。",
    stack="PyTorch / scikit-learn",
    en="prod_eval_label_accuracy_v1")

add(id="OP-PRD-04", stage="⑤生产评测", name="合规检测与综合质量分", type="模型型/规则型", priority="P1",
    desc="合规检测（违法/有害/隐私/版权）+ 综合质量分（分项加权）。",
    logic="多标签安全模型+敏感词+版权哈希；分项归一加权；扣分项。",
    dep="成品、策略/词表/哈希库/分项结果", fgw="13.3-四/13.5-三", proto="评测范围 L4459；专家维度 L4796",
    inp="成品、策略、词表、版权库、分项分", out="风险类型/等级/证据、合规率、总分/分项/扣分",
    tech="内容安全模型、NSFW、AC 敏感词、SimHash/MinHash 版权比对。",
    stack="安全模型 / SimHash / MinHash",
    en="prod_compliance_quality_v1")

add(id="OP-PRD-05", stage="⑤生产评测", name="九维分析聚合", type="统计型/规则型", priority="P1",
    desc="汇总 9 维结果，归一化加权综合评分，输出状态矩阵与结论摘要。",
    logic="接收各维 JSON；权重/阈值；缺失维度权重重分配；模板结论。",
    dep="9 维算子结果", fgw="13.4-一/二/三", proto="配比分析 L4621",
    inp="9 维结果、权重、基线", out="综合分/等级、9 维状态、结论、报告数据包",
    tech="加权/TOPSIS；规则阈值；模板化结论。",
    stack="Python",
    en="prod_analysis_9d_v1")

add(id="OP-PRD-06", stage="⑤生产评测", name="报告渲染导出", type="服务型", priority="P2",
    desc="用报告数据包渲染 HTML/PDF/Excel，上传对象存储返回 URL 与哈希。",
    logic="模板渲染；图表 SSR；PDF 转换；多 Sheet Excel；上传。",
    dep="报告数据包、模板", fgw="13.4-四/五", proto="下载报告 L4687；reportExport L3651",
    inp="报告数据包、模板、格式", out="HTML/PDF/Excel、URL、哈希、元数据",
    tech="Jinja2/Thymeleaf；ECharts SSR/WeasyPrint；openpyxl。",
    stack="Jinja2 / WeasyPrint / openpyxl",
    en="prod_report_render_v1",
    note="建议放后端渲染服务；如果算子池只放算法，可不做算子，列此表便于分工。")

# ============ ⑥ 工具与风险 ============
add(id="OP-TOL-01", stage="⑥工具与风险", name="知识图谱构建", type="模型型/图检索型", priority="P1",
    desc="从语料抽实体/关系，实体链接归一，写 Neo4j，输出图谱统计与待审实体。",
    logic="NER+RE+实体链接；UNWIND 批写；增量去重；覆盖率/缺口。",
    dep="文本、本体/词表、图谱", fgw="13.5-一", proto="工具链 Neo4j L2009",
    inp="文本分片、本体/词表、已有图谱", out="实体/关系表、图谱导入文件、节点/关系统计、待审清单",
    tech="HanLP/BERT NER、LLM RE、BLINK、Neo4j 批量 MERGE。",
    stack="Neo4j / HanLP / BLINK",
    en="tool_kg_build_v1")

add(id="OP-TOL-02", stage="⑥工具与风险", name="多模态向量与 FAISS 索引", type="模型型/图检索型", priority="P1",
    desc="多模态 embedding + FAISS 索引构建/增量/检索，输出 topK、recall@k、QPS。",
    logic="bge/CLIP 向量；IVF-PQ/HNSW；增量 add/delete；过滤；评估集。",
    dep="向量文件、索引参数", fgw="13.5-二", proto="工具链 FAISS L2011",
    inp="文本/图像、向量模型、索引参数、查询", out="向量文件、索引版本、检索结果、recall/QPS/时延",
    tech="bge-m3/CLIP、FAISS、ONNX/TensorRT。",
    stack="FAISS / bge / CLIP",
    en="tool_vector_index_v1")

add(id="OP-TOL-03", stage="⑥工具与风险", name="版权与重复内容检测", type="规则型", priority="P1",
    desc="内容指纹与哈希库/原创性 API 比对，识别精确/近似重复，结合授权台账判风险。",
    logic="MD5/SHA256；SimHash/MinHash；外部 API；授权匹配。",
    dep="文本/文件、哈希库、授权台账", fgw="13.5-三", proto="工具链版权 L2012",
    inp="文本/文件、哈希库、授权、阈值", out="重复命中/相似度、原创分、授权冲突、批次重复率",
    tech="hashlib、SimHash、MinHashLSH、API 适配。",
    stack="Python / SimHash / MinHash",
    en="tool_copyright_detect_v1")

add(id="OP-TOL-04", stage="⑥工具与风险", name="专家校验抽样", type="统计型/规则型", priority="P1",
    desc="5-10% 分层抽样，高风险/关键指标必选，输出可复现样本清单与比例校验。",
    logic="Neyman；高风险配额上浮；哈希取模；比例/最小样本校验。",
    dep="待校验对象、风险标记", fgw="13.5-四", proto="专家校验 L2015；发起 L4804",
    inp="对象清单、分层、风险、比例、seed", out="抽样方案、sampleIds、必选样本、比例校验",
    tech="分层抽样；哈希取模；比例校验规则。",
    stack="Python",
    en="tool_expert_sampling_v1")

add(id="OP-TOL-05", stage="⑥工具与风险", name="专家一致性与准确率", type="统计型", priority="P2",
    desc="多专家判定聚合，算 Cohen/Fleiss Kappa、Krippendorff Alpha、准确率/覆盖率。",
    logic="两两/多人一致性；多数投票金标准；混淆矩阵；bootstrap CI。",
    dep="专家标注、自动结果", fgw="13.5-四", proto="专家详情 L4788",
    inp="专家标注、自动结果、阈值", out="Kappa/Alpha、混淆矩阵、逐标签 P/R/F1、争议 TopN",
    tech="sklearn/自定义；bootstrap 置信区间。",
    stack="Python",
    en="tool_expert_agreement_v1",
    note="原型无真实专家数据；P2。")

add(id="OP-RSK-01", stage="⑥工具与风险", name="风险指标阈值与分级", type="规则型", priority="P1",
    desc="消费指标结果，按阈值/趋势判定风险等级、证据、建议动作，去重与抑制。",
    logic="规则 DSL；双阈值；作用域；severity；去重键+窗口；EWMA。",
    dep="指标算子结果、规则配置、历史风险", fgw="13.4-二/13.5", proto="风险列表 L1888",
    inp="指标包、阈值、历史、基线", out="风险条目、等级/证据/建议、抑制/合并清单",
    tech="JSON 规则/决策表；Python。",
    stack="Python",
    en="risk_metric_rule_v1")

add(id="OP-RSK-02", stage="⑥工具与风险", name="过时知识检测", type="模型型/规则型", priority="P2",
    desc="检测过时知识内容：与知识库比对，标记过时内容，计算过时率。",
    logic="时间敏感识别；与知识库版本比对；过时判定；过时率。",
    dep="文本、知识库/时效规则", fgw="13.3-三", proto="原型无独立卡（仅新鲜度）",
    inp="文本、知识库、时间、规则", out="过时标记、过时率、需更新清单",
    tech="时间抽取+知识库比对+规则/LLM。",
    stack="Python / LLM",
    en="risk_stale_knowledge_v1",
    note="原型未展示，P2；如审计要求可后置。")

# ============ 收敛版：22 个算子 ============
C_HEADERS = ["序号", "算子ID", "大环节", "算子名称", "算子类型", "优先级", "能力说明", "处理逻辑",
             "前置依赖", "FGW条款", "原型位置", "包含明细算子", "输入数据", "输出数据", "失败处理",
             "约束边界", "技术关键处理方案", "平台/算子边界", "是否通用", "算子英文名", "模型/技术栈",
             "完成状态", "负责人", "交付时间", "备注/待确认"]
C_KEYS = ["seq", "id", "stage", "name", "type", "priority", "desc", "logic", "dep", "fgw", "proto",
          "members", "inp", "out", "fail", "bound", "tech", "boundary", "common", "en", "stack",
          "status", "owner", "date", "note"]
C_WIDTHS = [5, 10, 14, 20, 15, 8, 48, 58, 22, 14, 30, 22, 32, 36, 30, 35, 52, 35, 8, 30, 32, 8, 8, 10, 30]

C_DEFAULT = {
    "type": "模型型", "priority": "P1", "status": "未开始", "owner": "待定", "date": "待定",
    "common": "通用", "note": "",
    "fail": "单批失败记录原因码并返回失败清单，不阻断已成功批次；支持幂等重跑。",
    "bound": "单请求受平台上限约束；原始数据只读；结果带算子版本、模型版本（如适用）、树版本与参数哈希。",
    "boundary": "平台负责批次调度、存储、结果落库与展示；算子只对输入数据计算并返回结果/产物。",
}
CONS = []


def cadd(**kw):
    row = dict(C_DEFAULT)
    row.update(kw)
    row["seq"] = len(CONS) + 1
    CONS.append(row)


cadd(id="OP-01", stage="①接入与解析", name="多模态识别与解析", type="解析型", priority="P0",
     members="ING-01~05",
     desc="判定并解析一个批次里的所有模态：文本、图像、音频、视频；同一数据集可多模态，同一模态可多格式，混合文件先拆流。",
     logic="文件头/MIME 判模态；按格式路由解析；PDF 扫描页 OCR；音视频拆流；输出内容、格式元数据、声学/图像特征。",
     dep="批次登记、文件可访问", fgw="13.1-一", proto="数据接入·模态识别与四模态分步 L2395-2412、L2414-2462",
     inp="文件清单/OSS 前缀、扩展名/MIME、解析参数（OCR/重采样/抽帧）",
     out="各模态内容/特征、格式元数据、解析质量指标、拆流清单",
     tech="libmagic/ffprobe 判模态；PyMuPDF/PaddleOCR 解析文本；Pillow 解析图像；ffmpeg/librosa 解析音频；ffmpeg/PySceneDetect 拆视频。",
     stack="libmagic / ffprobe / PyMuPDF / PaddleOCR / Pillow / ffmpeg / librosa / PySceneDetect",
     en="dm-multimodal-analysis",
     note="内部按模态分支，不按模态拆成多个算子；视频音轨转音频分支；四模态同等优先级。")

cadd(id="OP-02", stage="①接入与解析", name="标准化、元数据与去重", type="解析型/规则型", priority="P0",
     members="ING-06~08",
     desc="标准容器、分区、manifest、元数据索引、去重/异常识别、跨模态关联表。",
     logic="Parquet/WebP/WAV/H.264；按 modal/source/dt 分区；MD5/SimHash 去重；元数据宽表+索引；帧-音频-文本关联。",
     dep="多模态解析完成", fgw="13.1-二/三", proto="标准化路径 L2410；数据分片卡 L1556",
     inp="解析产物、分区规则、索引字段、哈希阈值",
     out="标准产物+manifest、元数据宽表/索引、重复/异常清单、跨模态关联表",
     tech="pyarrow+zstd；Pillow/ffmpeg；hashlib+SimHash/MinHashLSH；DuckDB/ES 索引。",
     stack="pyarrow / ffmpeg / Pillow / SimHash / MinHashLSH / DuckDB / Elasticsearch",
     en="dm-corpus-normalization",
     note="标准化、元数据、去重、关联作为同一算子的子步骤；如部署资源差异大，可再拆。")

cadd(id="OP-03", stage="②分片与打标", name="句向量与主题聚类", type="模型型/统计型", priority="P0",
     members="SHP-01",
     desc="文本分句/分块→bge 向量→K-Means，轮廓系数选 K，输出簇与主题词。",
     logic="512 token 切窗、L2 归一、MiniBatchKMeans、候选 K 评估、c-TF-IDF 主题词。",
     dep="标准化文本", fgw="13.1-三", proto="数据分片卡 L1556",
     inp="文本记录、模型、切句参数、K 范围、seed",
     out="句向量、K/轮廓系数、record→cluster、簇规模/主题词",
     tech="bge-m3 + sentence-transformers；FAISS/scikit-learn MiniBatchKMeans；silhouette_score。",
     stack="bge-m3 / sentence-transformers / scikit-learn / FAISS",
     en="dm-text-clustering",
     note="向量可复用给打标、FAISS、近重复检测。")

cadd(id="OP-04", stage="②分片与打标", name="分层抽样", type="统计型/规则型", priority="P1",
     members="SHP-02",
     desc="按来源×主题×质量分层，Neyman 分配配额并执行抽样，输出代表性校验。",
     logic="n_h=n·(N_h·CV_h)/Σ；总样本 5-10%/20-30%、≥10 万；固定 seed。",
     dep="元数据/主题簇/质量等级", fgw="13.1-四", proto="分层抽样配置 L1565/L2380",
     inp="分层字段、N/CV、比例、最小样本、seed",
     out="层配额、样本清单、实抽比例、代表性偏差、未达标层",
     tech="DuckDB/Spark stratified sample；Neyman；哈希取模保证可复现。",
     stack="DuckDB / Spark / pandas",
     en="dm-stratified-sampling",
     note="同时服务接入抽样与组装选样。")

cadd(id="OP-05", stage="②分片与打标", name="多模态自动打标", type="模型型", priority="P0",
     members="LBL-01~04",
     desc="文本/图像/音频/视频统一打标，输出可变深度路径+置信度+topK；四模态同一优先级。",
     logic="文本层级分类；图像 ViT/CLIP；音频 PANNs/ASR；视频关键帧+音轨+ASR 融合。",
     dep="标准化四模态、类型树", fgw="12.2-6/8", proto="数据打标列表 L1810-1821",
     inp="四模态内容、类型树、阈值/topK/最大深度",
     out="路径、置信度、topK、证据、模型/树版本、低置信标记",
     tech="BERT/RoBERTa；ViT/ConvNeXt+CLIP；PANNs/AST+Whisper；VideoMAE+CLIP+CLAP。",
     stack="PyTorch / BERT / ViT / CLIP / PANNs / VideoMAE / Whisper",
     en="dm-multimodal-labeling",
     note="一个算子四个模态分支，任何模态都不能缺；视频音轨复用音频分支；低置信进标签治理。")

cadd(id="OP-06", stage="②分片与打标", name="领域/能力多标签", type="模型型", priority="P1",
     members="LBL-05~06",
     desc="领域 16 行业树 + 能力树多标签，支持任意层级、跨领域分别计入。",
     logic="多标签层次分类/embedding 相似；阈值裁剪；LLM few-shot 兜底。",
     dep="文本/ASR/OCR、领域/能力树", fgw="12.2-6/12.3", proto="数据打标领域/能力列 L1832/L2836",
     inp="样本内容、领域树、能力树、阈值/topK",
     out="领域/能力多路径+分数、证据、模型/树版本",
     tech="BERT 多标签或 bge 向量+kNN；LLM 逐能力项打分。",
     stack="BERT / bge-m3 / LLM",
     en="dm-taxonomy-labeling",
     note="领域=讲什么，能力=能练什么，两个标签空间分开。")

cadd(id="OP-07", stage="②分片与打标", name="标签治理", type="规则型/模型型/统计型", priority="P1",
     members="LBL-07~09",
     desc="标签校验、未归类识别、质量评估、治理属性建议。",
     logic="树快照校验；低置信/margin/OOD；人工审核比对准确率；PII/价值/关联度建议。",
     dep="打标结果、人工审核、类型树", fgw="12.2-4/5/7/9/10", proto="修改标签弹窗 L3183；未归类池 L2045；KPI L2778",
     inp="标签记录、审核记录、树、阈值",
     out="合法/非法、未归类原因、质量报告、治理建议",
     tech="规则引擎+编辑距离；bge 近邻/OOD；sklearn/Kappa；PII NER。",
     stack="Python / bge-m3 / scikit-learn / PII-BERT",
     en="dm-label-governance",
     note="质量评估依赖真实人工审核记录；没有记录只能标“待补数据”。")

cadd(id="OP-08", stage="③语料画像", name="规模、来源与领域画像", type="统计型/规则型/模型型", priority="P0",
     members="PRF-01~03",
     desc="条目/字符/时长/帧数/存储/分位数；六类来源+可信度；领域占比/覆盖。",
     logic="流式聚合+t-digest；来源规则+fastText；AHP；领域分类+树 rollup。",
     dep="标准化产物/元数据/领域标签", fgw="13.2-1/2/3/4", proto="规模卡 L1862；来源卡 L1868；主题覆盖 L2135",
     inp="标准产物/元数据、来源台账、领域标签",
     out="规模/分位数/占比、六类来源+可信度、领域覆盖",
     tech="DuckDB/Spark；fastText；AHP；BERT 领域分类。",
     stack="DuckDB / Spark / fastText / BERT",
     en="dm-corpus-profiling",
     note="来源口径要从原型的 3 类扩为 FGW 六类。")

cadd(id="OP-09", stage="③语料画像", name="语言、地域与时效画像", type="模型型/规则型/统计型", priority="P0",
     members="PRF-04~06",
     desc="语种/方言、地域推断、时间抽取与新鲜度。",
     logic="fastText/CLD3；ip2region+GeoNames；dateparser+分桶加权。",
     dep="文本/ASR/OCR、元数据", fgw="13.2-5/6", proto="语言分布 L1873；新鲜度 L1877；RK-005 L1893",
     inp="文本/转写、IP/GPS/时区、时间戳",
     out="语种/方言+置信度、地域分布、年季分布/新鲜度",
     tech="fastText lid.176/CLD3；ip2region；dateparser/HeidelTime。",
     stack="fastText / CLD3 / ip2region / dateparser",
     en="dm-language-profiling",
     note="语种置信度<0.85 标混合/未识别；地域推断为 P2 子项。")

cadd(id="OP-10", stage="③语料画像", name="文本属性与任务适配", type="模型型/统计型", priority="P0",
     members="PRF-07、PRF-11",
     desc="句长/从句/被动/TTR/语体 + 六维任务适配评分。",
     logic="依存句法；TTR/MSTTR；语体分类；结构 40/语义 30/领域 30 加权。",
     dep="文本、领域标签", fgw="13.3-1/2", proto="语料属性 L1878；任务适配 L1882",
     inp="文本、句法/语体模型、评分权重",
     out="文本属性、分布、六维适配分+子指标",
     tech="HanLP/LTP/Stanza；RoBERTa；LightGBM/LLM 校准。",
     stack="HanLP / LTP / RoBERTa / LightGBM",
     en="dm-text-profiling",
     note="任务适配的代码/图文子项可复用打标/图像结果。")

cadd(id="OP-11", stage="③语料画像", name="语音质量与声学属性", type="模型型/统计型", priority="P1",
     members="PRF-08",
     desc="ASR 转写、WER/CER、语速、基频、停顿、口音。",
     logic="ASR；文本归一+编辑距离；VAD 有效时长；声学特征。",
     dep="音频、参考文本（可选）", fgw="13.3-1", proto="WER L1887；语速 L1880；RK-002 L1890",
     inp="音频、参考转写、ASR 模型、阈值",
     out="转写、WER/CER、语速、基频/停顿、低质量清单",
     tech="Whisper/FunASR；jiwer；praat/parselmouth；pyannote VAD。",
     stack="Whisper / FunASR / jiwer / praat",
     en="dm-speech-analysis",
     note="无参考文本时只出置信度/困惑度，不冒充 WER。")

cadd(id="OP-12", stage="③语料画像", name="图像/视频属性", type="模型型/统计型", priority="P1",
     members="PRF-09~10",
     desc="图像场景/目标/熵；视频镜头/光流/音画对齐/动作。",
     logic="CLIP/YOLO；场景熵；PySceneDetect/RAFT；BLEU；VideoMAE。",
     dep="图像/视频+音轨+ASR", fgw="13.3-1", proto="香农熵 L1880；视频帧率 L1865（缺口）",
     inp="图像/视频、关键帧、ASR/字幕",
     out="场景/目标/熵、镜头/光流/BLEU/动作覆盖",
     tech="CLIP/YOLOv8；PySceneDetect/RAFT；sacrebleu；VideoMAE/SlowFast。",
     stack="CLIP / YOLOv8 / PySceneDetect / RAFT / VideoMAE",
     en="dm-visual-analysis",
     note="原型没有视频专项卡；FGW 要求，建议补 UI。")

cadd(id="OP-13", stage="③语料画像", name="知识覆盖、热点与风格", type="模型型/统计型", priority="P1",
     members="PRF-12、PRF-15",
     desc="实体/术语覆盖率、知识密度/层次；热点长尾、语体、术语覆盖。",
     logic="NER+实体链接；AC 术语；BERTopic；语体分类。",
     dep="文本、KG/术语表、目标清单", fgw="13.3-3", proto="知识指标 L1886；卡片9 L2142；卡片11/12 L2156/L2165",
     inp="文本、KG/术语表、时间、目标清单",
     out="覆盖率/密度/层次、热点/长尾、语体/术语覆盖",
     tech="HanLP/BLINK；AC；BERTopic；RoBERTa。",
     stack="HanLP / BLINK / BERTopic / RoBERTa",
     en="dm-knowledge-analysis",
     note="热点长尾为 Comic 口径；FGW 只要求稀疏/长尾。")

cadd(id="OP-14", stage="③语料画像", name="质量、一致性与难度", type="统计型/模型型", priority="P0",
     members="PRF-13~14",
     desc="完整率/跨文档冲突/基尼/标注覆盖；难度四档/正负样本。",
     logic="字段校验；实体链接+属性比对；基尼；PPL 分档；极性分类。",
     dep="元数据/实体/领域/标注/样本", fgw="13.3-4/13.3-2", proto="质量卡 L1887；卡片10 L2149；卡片6 L2117",
     inp="字段/实体/属性/标注/样本",
     out="完整率/冲突/基尼/覆盖；难度/正负/平衡度",
     tech="pandas；BLINK；PPL 小模型；RoBERTa 极性。",
     stack="pandas / BLINK / Qwen2.5-0.5B / RoBERTa",
     en="dm-quality-analysis",
     note="难度/正负为 Comic 口径，P2 子项。")

cadd(id="OP-15", stage="④配比引擎", name="配比引擎", type="规则型/统计型", priority="P0",
     members="RAT-01~03",
     desc="六类来源占比、加权配比、归一化、30%/100%/库存校验。",
     logic="Σ条数×权重；最大余数法；树覆盖；库存=target%×总规模。",
     dep="标签库存、来源权重、目标规模、标签树", fgw="12.1/12.3/12.4", proto="配比编辑 L3870；KPI L3899；库存 L3924",
     inp="标签条数/token、权重、目标规模、核心标签集、库存",
     out="条数/权重/占比、投喂条数、校验单、缺口量",
     tech="Python 规则/OR-Tools；DuckDB。",
     stack="Python / OR-Tools / DuckDB",
     en="dm-ratio-computation",
     note="纯规则；可下沉后端，但建议独立服务便于审计复算。")

cadd(id="OP-16", stage="④配比引擎", name="配比分析与建议", type="规则型/优化型", priority="P1",
     members="RAT-04~08",
     desc="能力预测、领域覆盖、按目标能力推荐、缺口补数、达成度、偏见、通用/专业对标。",
     logic="标签→能力/领域矩阵；加权/线性规划；来源覆盖打分；分布偏斜；多目标。",
     dep="配比、映射库、库存、实际投喂", fgw="12.3-2/5、12.4-1/2/4/5", proto="能力预测 L3658；领域覆盖 L6448；推荐 L6420；达成度 L2071",
     inp="配比、映射、库存、实际、目标",
     out="六维能力、领域覆盖、建议配比、补数、达成度、偏见、对标",
     tech="专家矩阵/岭回归；OR-Tools；pandas；毒性分类。",
     stack="Python / scikit-learn / OR-Tools",
     en="dm-ratio-analysis",
     note="通用/专业对标、偏见为 P2 子项。")

cadd(id="OP-17", stage="⑤生产评测", name="数据组装与打包", type="统计型/I/O型", priority="P0",
     members="PRD-01~02",
     desc="按配方配额分层选样，写成品 Parquet，生成 manifest 与校验和。",
     logic="Neyman/加权无放回；固定 seed；分区写；MD5/SHA256；断点续跑。",
     dep="配方、库存、分层字段", fgw="13.1-二/三/四", proto="组装任务 L4419；下载 L4477",
     inp="配方明细、库存、分层、seed、分区/格式参数",
     out="样本清单、成品文件、manifest、校验和",
     tech="DuckDB/Spark；pyarrow+zstd；SHA-256。",
     stack="DuckDB / Spark / pyarrow",
     en="dm-dataset-packaging",
     note="选样与打包作为同一服务两个端点。")

cadd(id="OP-18", stage="⑤生产评测", name="数据评测", type="模型型/统计型/规则型", priority="P0",
     members="PRD-03~04、TOL-03",
     desc="5-10% 抽样、标签准确率/F1/混淆矩阵、合规/版权检测、综合质量分。",
     logic="分层抽样；复用打标模型；路径匹配；安全模型+敏感词+版权哈希；分项加权。",
     dep="成品 manifest、真值、打标模型", fgw="13.3/13.5-三", proto="数据评测 L4453；专家维度 L4796",
     inp="成品、真值、抽样比例、策略/词表/版权库",
     out="抽样清单、准确率/F1、合规/版权结果、综合分",
     tech="复用打标模型；sklearn；安全模型；SimHash/MinHash。",
     stack="PyTorch / scikit-learn / SimHash / MinHash",
     en="dm-dataset-evaluation",
     note="版权检测作为合规子项，不单独做算子。")

cadd(id="OP-19", stage="⑤生产评测", name="配比分析与报告", type="统计型/服务型", priority="P1",
     members="PRD-05~06",
     desc="9 维结果聚合、综合评分、状态矩阵、报告数据包与 HTML/PDF/Excel 渲染。",
     logic="归一化加权；阈值；模板结论；模板渲染+PDF/Excel。",
     dep="9 维算子结果、模板", fgw="13.4", proto="配比分析 L4621；下载报告 L4687",
     inp="9 维结果、权重、模板",
     out="综合分、9 维状态、报告数据包、HTML/PDF/Excel",
     tech="Python 聚合；Jinja2/WeasyPrint/openpyxl。",
     stack="Python / Jinja2 / WeasyPrint / openpyxl",
     en="dm-ratio-reporting",
     note="报告渲染可下沉后端；算子只产数据包。")

cadd(id="OP-20", stage="⑥工具与风险", name="知识图谱与向量索引", type="模型型/图检索型", priority="P1",
     members="TOL-01~02",
     desc="实体/关系抽取、实体链接、Neo4j 建图；多模态 embedding、FAISS 建索引/检索。",
     logic="NER+RE+BLINK；UNWIND 批写；bge/CLIP 向量；IVF-PQ/HNSW；recall/QPS。",
     dep="文本/图像、本体/词表、图谱/向量库", fgw="13.5-一/二", proto="工具链 Neo4j/FAISS L2009-2011",
     inp="文本分片、图像、本体、索引参数",
     out="实体/关系表、图谱统计、向量/索引、检索结果",
     tech="HanLP/BLINK/Neo4j；bge/CLIP/FAISS。",
     stack="Neo4j / HanLP / BLINK / bge / CLIP / FAISS",
     en="dm-graph-indexing",
     note="图谱/索引服务由平台运维；算子只做抽取/向量/建索引。")

cadd(id="OP-21", stage="⑥工具与风险", name="专家校验", type="统计型/规则型", priority="P1",
     members="TOL-04~05",
     desc="5-10% 分层抽样、高风险必选；多专家 Kappa/Alpha、准确率/覆盖率。",
     logic="Neyman；哈希取模；多数投票金标准；混淆矩阵；bootstrap。",
     dep="待校验对象、专家标注、自动结果", fgw="13.5-四", proto="专家校验 L2015/L4788",
     inp="对象清单、风险、专家标注、自动结果",
     out="抽样清单、Kappa/Alpha、准确率/覆盖率、争议 TopN",
     tech="Python/分层抽样/sklearn。",
     stack="Python / scikit-learn",
     en="dm-expert-validation",
     note="专家任务流程/签署归平台。")

cadd(id="OP-22", stage="⑥工具与风险", name="风险检测与分级", type="规则型/模型型", priority="P1",
     members="RSK-01~02",
     desc="消费指标结果按阈值/趋势判定风险等级、证据、建议；检测过时知识。",
     logic="规则 DSL；双阈值；去重/抑制；时间敏感+知识库比对。",
     dep="指标结果、规则配置、历史风险、知识库", fgw="13.4-二/13.5/13.3-三", proto="风险列表 L1888",
     inp="指标包、阈值、历史、知识库",
     out="风险条目、等级/证据/建议、过时标记/过时率",
     tech="JSON 规则/决策表；时间抽取+知识库比对。",
     stack="Python / LLM",
     en="dm-risk-detection",
     note="风险工单/处置归平台；过时知识为 P2 子项。")

# ============ 样式与写盘 ============
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="微软雅黑", size=9)
TITLE_FONT = Font(name="微软雅黑", size=16, bold=True, color="1F4E78")
SECTION_FONT = Font(name="微软雅黑", size=11, bold=True, color="1F4E78")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top", horizontal="left")
CENTER = Alignment(wrap_text=True, vertical="center", horizontal="center")
PRI_FILL = {"P0": PatternFill("solid", fgColor="FCE4D6"),
            "P1": PatternFill("solid", fgColor="FFF2CC"),
            "P2": PatternFill("solid", fgColor="EDEDED")}
ALT_FILL = PatternFill("solid", fgColor="F7F9FC")

WIDTHS = [5, 16, 14, 18, 15, 8, 45, 55, 22, 14, 30, 30, 35, 30, 35, 50, 35, 8, 32, 30, 8, 8, 10, 30]


def style_header(ws, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = BORDER
    ws.row_dimensions[1].height = 32


def write_sheet(ws, rows, headers, keys, widths):
    for c, h in enumerate(headers, 1):
        ws.cell(row=1, column=c, value=h)
    style_header(ws, len(headers))
    for i, row in enumerate(rows, 2):
        for c, k in enumerate(keys, 1):
            cell = ws.cell(row=i, column=c, value=row.get(k, ""))
            cell.font = BODY_FONT
            cell.alignment = CENTER if k in ("seq", "priority", "common", "status") else WRAP
            cell.border = BORDER
            if i % 2 == 0:
                cell.fill = ALT_FILL
        pcell = ws.cell(row=i, column=6)
        if pcell.value in PRI_FILL:
            pcell.fill = PRI_FILL[pcell.value]
        ws.row_dimensions[i].height = 62
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "1:1"


def write_table(ws, rows):
    write_sheet(ws, rows, HEADERS, KEYS, WIDTHS)


wb = Workbook()
wb.remove(wb.active)

# ---- 00 说明 ----
ws0 = wb.create_sheet("00-说明")
ws0.column_dimensions["A"].width = 18
ws0.column_dimensions["B"].width = 110
ws0.merge_cells("A1:B1")
ws0["A1"] = "数据配比中心 · 算子开发清单"
ws0["A1"].font = TITLE_FONT
ws0["A1"].alignment = Alignment(vertical="center")
ws0.row_dimensions[1].height = 38

intro = [
    ("用途", "本表把原型中必须由算子真实计算/推理的能力整理成可排期、可验收的清单。01 是 22 个收敛算子，02 是 56 行能力明细，03 是 11 个 P0 最小链路。平台 CRUD、任务编排、人工审核、存储与展示不在本表。"),
    ("依据", "docs/html原型/数据配比中心_完整交互版_2026-11-15.html；FGW《数据配比》12.x/13.x；Comic 任务书；PST/PRE/IND 交接文档。"),
    ("范围口径", "只列“能对真实语料产生可核验新结果”的能力。纯 CRUD、状态机、人工审核、进度展示、报告页面交互、工具健康度面板均不列。"),
    ("模态口径", "所有模态一视同仁：文本/图像/音频/视频均有解析、打标、画像；同一数据集可含多模态；同一模态可有多种格式；混合文件先拆流再分别处理。"),
    ("收敛口径", "同一个算子的多模态分支/子步骤合并为一行；01 总表 22 行，P0 11 行、P1 11 行。原 56 行能力明细保留在 02，便于追溯和验收。源库增量拉取（原 ING-09）归平台连接器，不列入算子。"),
    ("优先级", "P0=最小真实链路必须；P1=业务价值高、第二阶段。原 P2 子项（地域推断、治理属性建议、通用/专业对标、报告渲染、过时知识、专家一致性）已并入对应算子。"),
    ("完成状态", "统一从“未开始”起算；负责人和交付时间待排期后填写。"),
    ("重要提醒", "原型中绝大多数数值是常量、哈希或 Math.random() 伪造；不能用原型的“已显示”当作“已实现”。"),
]
r = 3
for k, v in intro:
    ws0.cell(row=r, column=1, value=k).font = SECTION_FONT
    ws0.cell(row=r, column=1).alignment = Alignment(vertical="top")
    ws0.cell(row=r, column=2, value=v).font = BODY_FONT
    ws0.cell(row=r, column=2).alignment = WRAP
    ws0.row_dimensions[r].height = 42
    r += 1

r += 1
ws0.cell(row=r, column=1, value="表头说明").font = SECTION_FONT
r += 1
legend = [
    ("算子类型", "解析型 / 模型型 / 规则型 / 统计型 / 图检索型 / I/O型 / 服务型"),
    ("FGW条款", "对应原文 12.x/13.x 二级能力编号，用于审计追溯"),
    ("原型位置", "原型页面 + 关键行号；L 指 HTML 文件行号"),
    ("包含明细算子", "该收敛算子合并了 02-能力明细 里的哪些行，便于追溯"),
    ("平台/算子边界", "明确平台负责什么、算子只负责什么，避免职责外溢"),
    ("是否通用", "通用=可跨业务复用；场景专用=仅本项目使用"),
    ("算子英文名", "01/03 采用 dm-<对象>-<动作> 两词命名（如 dm-multimodal-analysis）；02 能力明细保留内部能力编码 corpus_*。发布后不可改。"),
]
for k, v in legend:
    ws0.cell(row=r, column=1, value=k).font = BODY_FONT
    ws0.cell(row=r, column=2, value=v).font = BODY_FONT
    ws0.cell(row=r, column=2).alignment = WRAP
    r += 1

# ---- 01 算子总表（22 行收敛版） ----
ws1 = wb.create_sheet("01-算子总表")
write_sheet(ws1, CONS, C_HEADERS, C_KEYS, C_WIDTHS)

# ---- 02 能力明细（原 56 行） ----
ws2 = wb.create_sheet("02-能力明细")
write_table(ws2, ROWS)

# ---- 03 P0 最小链路（收敛版） ----
ws3 = wb.create_sheet("03-P0最小链路")
write_sheet(ws3, [x for x in CONS if x["priority"] == "P0"], C_HEADERS, C_KEYS, C_WIDTHS)

# ---- 04 模态覆盖矩阵 ----
wsM = wb.create_sheet("04-模态覆盖矩阵")
m_headers = ["模态", "常见/需支持格式", "解析算子", "标准化产物", "自动打标算子", "画像/分析算子", "关键说明"]
m_widths = [14, 40, 22, 24, 22, 30, 60]
for c, h in enumerate(m_headers, 1):
    cell = wsM.cell(row=1, column=c, value=h)
    cell.fill = HEADER_FILL
    cell.font = HEADER_FONT
    cell.alignment = CENTER
    cell.border = BORDER
wsM.row_dimensions[1].height = 30
modal_rows = [
    ("文本", "TXT、JSONL、JSON、XML、PDF（含扫描页）", "OP-01 多模态识别与解析", "Parquet 列式", "OP-05 多模态自动打标", "OP-08/09/10/13/14",
     "同一文本模态可能同时出现多种格式；PDF 扫描页走 OCR/版面，普通文本走解析器。"),
    ("图像", "JPG、PNG、BMP（扩展：WebP、TIFF）", "OP-01 多模态识别与解析", "WebP + phash", "OP-05 多模态自动打标", "OP-12/14",
     "读 header/EXIF 即可出基础特征；图像打标与文本打标同级，不能只做文本。"),
    ("音频", "WAV、MP3、FLAC（扩展：M4A、AAC）", "OP-01 多模态识别与解析", "WAV 16k mono + 梅尔谱", "OP-05 多模态自动打标", "OP-11/09",
     "视频里的音轨也走同一算子；语种识别复用 OP-09；WER 复用 ASR 转写。"),
    ("视频", "MP4、MOV（扩展：AVI、MKV）", "OP-01 多模态识别与解析", "H.264 + 关键帧", "OP-05 多模态自动打标", "OP-12/14",
     "先拆音视频流，再分别走音频/图像链路；视频打标用关键帧+音轨+ASR 融合。"),
    ("混合/跨模态", "视频含音轨、PDF 含扫描页、图文配对、音视频+字幕", "OP-01 拆流 + OP-02 关联", "各模态标准产物 + 关联表", "OP-05 按子模态分支", "OP-14 跨模态一致性",
     "一个数据集可含多个模态；先识别并拆流，再按子模态并行处理，最后建“帧-音频-文本”关联表。"),
]
for i, row in enumerate(modal_rows, 2):
    wsM.cell(row=i, column=1, value=row[0]).font = Font(name="微软雅黑", size=9, bold=True)
    wsM.cell(row=i, column=1).alignment = CENTER
    wsM.cell(row=i, column=1).border = BORDER
    for c, v in enumerate(row[1:], 2):
        cell = wsM.cell(row=i, column=c, value=v)
        cell.font = BODY_FONT
        cell.alignment = WRAP
        cell.border = BORDER
    wsM.row_dimensions[i].height = 58
for c, w in enumerate(m_widths, 1):
    wsM.column_dimensions[get_column_letter(c)].width = w
wsM.freeze_panes = "A2"
wsM.page_setup.orientation = "landscape"
wsM.page_setup.fitToWidth = 1
wsM.page_setup.fitToHeight = 0
wsM.sheet_properties.pageSetUpPr.fitToPage = True

# ---- 05 非算子清单 ----
ws9 = wb.create_sheet("05-非算子清单")
n_headers = ["序号", "模块/功能", "原型位置", "建议落位", "说明", "备注"]
n_widths = [5, 34, 32, 22, 70, 30]
for c, h in enumerate(n_headers, 1):
    cell = ws9.cell(row=1, column=c, value=h)
    cell.fill = HEADER_FILL
    cell.font = HEADER_FONT
    cell.alignment = CENTER
    cell.border = BORDER
ws9.row_dimensions[1].height = 30
non_ops = [
    ("分类体系树管理", "分类体系管理 L2499-2738", "平台表+接口", "树的增删改、启停、排序、收藏；算子只消费树快照", "treeVersion 需版本化"),
    ("场景管理", "场景管理 L3834-3868", "平台表+接口", "场景 CRUD 与标签勾选；场景→配比行由 OP-15 计算", "不单独做算子"),
    ("配方包管理", "配方包管理 L4082-4184", "平台表+版本字段", "我的/公共配方、版本快照/差异/封存/回滚", "版本工程属平台"),
    ("配比生产任务状态机", "配比生产任务 L4186-4228", "平台任务服务", "组装/投喂/补数任务创建、进度、重试、状态流转", "算子只执行单批计算"),
    ("配比分析任务状态机", "配比分析任务 L4537-4560", "平台任务服务", "分析任务创建、运行、归档、重新分析", "算子只产维度结果"),
    ("风险工单与处置", "风险预警 L3579-3649", "平台工单", "风险列表、筛选、处置、闭环、通知", "OP-22 只产风险条目"),
    ("专家校验任务流程", "工具链 L4734-4826", "平台+人工", "任务派发、专家打分、签署、发布", "OP-21 只做抽样与一致性"),
    ("报告页面与下载入口", "分析报告 L4687-4731", "前端/后端", "报告展示、下载按钮、历史归档", "OP-19 可只做渲染服务"),
    ("图表与看板", "语料画像/配比页", "前端", "ECharts 图表、筛选交互、KPI 卡", "算子只给数据"),
    ("进度/通知/权限/审计", "全局", "平台", "进度条、通知、菜单权限、操作日志", "不属于算子"),
    ("源库增量拉取（原 ING-09）", "检查点恢复 L6977-7038", "平台连接器", "JDBC/S3/HTTP 游标拉取、断点续传、幂等批次", "不作为算子，归平台数据接入层"),
    ("策略仿真与准入", "Comic 额外模块", "后端占位/简单规则", "候选策略、沙盒仿真、七维评估、准入放行", "甲方只要求“有”，不必做算子"),
    ("智能推荐生成数据集包", "Comic 额外模块", "后端占位/模板", "目标画像、语义拆解、多方案推荐、反馈迭代", "可复用 OP-16 的简化版"),
    ("参考配方相似生成", "Comic 额外模块", "后端占位", "参考集画像拆解、复刻规则、双集对标", "可复用画像算子结果"),
    ("数据集包配比分析", "Comic 额外模块", "后端 SQL/简单聚合", "子集权重、主题互补/冗余、跨子集关联等", "不单独做算子"),
    ("数据集包版本管理/运营统计", "Comic 额外模块", "平台表+SQL", "版本差异、交付血缘、运营指标", "平台功能"),
]
for i, row in enumerate(non_ops, 2):
    ws9.cell(row=i, column=1, value=i - 1).font = BODY_FONT
    ws9.cell(row=i, column=1).alignment = CENTER
    for c, v in enumerate(row, 2):
        cell = ws9.cell(row=i, column=c, value=v)
        cell.font = BODY_FONT
        cell.alignment = WRAP if c >= 5 else CENTER
        cell.border = BORDER
    ws9.row_dimensions[i].height = 40
for c, w in enumerate(n_widths, 1):
    ws9.column_dimensions[get_column_letter(c)].width = w
ws9.freeze_panes = "A2"
ws9.auto_filter.ref = f"A1:F{len(non_ops) + 1}"
ws9.page_setup.orientation = "landscape"
ws9.page_setup.fitToWidth = 1
ws9.page_setup.fitToHeight = 0
ws9.sheet_properties.pageSetUpPr.fitToPage = True

# 标签颜色
colors = ["1F4E78", "2E75B6", "548235", "BF8F00", "C00000", "7030A0", "404040", "808080", "255E91", "7F6000"]
for i, ws in enumerate(wb.worksheets):
    ws.sheet_properties.tabColor = colors[i % len(colors)]

# 让 Excel 打开时直接落在算子总表，而不是说明页
ws0.title = "06-说明"
ORDER = ["01-算子总表", "02-能力明细", "03-P0最小链路", "04-模态覆盖矩阵", "05-非算子清单", "06-说明"]
wb._sheets = [wb[name] for name in ORDER]
wb.active = 0
ws1.sheet_view.zoomScale = 85

wb.save(OUT)
print("saved:", OUT)
print("consolidated:", len(CONS), "P0:", sum(1 for x in CONS if x["priority"] == "P0"),
      "P1:", sum(1 for x in CONS if x["priority"] == "P1"))
print("detail:", len(ROWS), "P0:", sum(1 for x in ROWS if x["priority"] == "P0"),
      "P1:", sum(1 for x in ROWS if x["priority"] == "P1"),
      "P2:", sum(1 for x in ROWS if x["priority"] == "P2"))
print("sheets:", wb.sheetnames)
