下面是我建议你直接替换原文的 **Phase 1 v3 Execution-Safe Plan**。它保留原计划的 Codex/Ralph 执行结构，但修掉了我前面指出的 P0：音频 chunk 限流冲突、删除链路 DDL 不完整、PII 加密不一致、支付口径缺失、admin 强制 publish 过危险、VLM 范围越界、API path 不统一、session 状态名不统一等。原计划的总体方向是对的：Phase 1 要围绕语音采访、Claim Ledger、Family Correction、Verifier、微信数字故事页、隐私/导出/删除链路来做，而不是提前做视频、精装书、历史卡片或 avatar。

---

# 长卷 Phase 1 — v3 Execution-Safe Implementation Plan

> 本文档是 Phase 1 唯一执行 spec。
> 冲突优先级：**本文档 v3 > 公司宪章 v2 > 旧版 Codex 执行计划 > 对话历史**。
> 目标不是做完整商业化产品，而是验证：**老人愿意讲，子女愿意核验，系统不瞎编，家庭愿意推荐。**

---

## 0. Phase 1 一句话目标

> **用微信生态跑通 100 户家庭的可信家庭故事交付：老人原声采访 → 事实抽取 → 家人核验 → 引用绑定叙事 → 二次同意 → 私密故事页 + PDF。**

Phase 1 的产品真相是：

> **不是 AI 回忆录，而是 evidence-grounded family story。**

所有工程决策围绕一个原则：

> **没有证据的事实，不进入正式故事。**

---

## 1. Phase 1 范围

## 1.1 In Scope

| 模块                | Phase 1 必须交付                                                                      |
| ----------------- | --------------------------------------------------------------------------------- |
| 微信小程序             | 项目创建、照片上传、采访发起、家人核验、故事预览、分享设置、隐私/导出/删除                                            |
| H5                | 营销落地页、老人采访入口跳转、小程序兜底入口                                                            |
| 管理后台              | 项目状态、音频/转写查看、claim 审核、敏感内容审核、失败任务重试、运营备注                                          |
| 语音采访              | 小程序内实时语音采访，15–40 分钟，支持沉默、拒答、中断                                                    |
| ASR/TTS           | 火山 streaming ASR/TTS 主路，讯飞 batch ASR 作为后处理与方言补偿                                   |
| Claim Ledger      | 原子事实账本，绑定音频/照片/用户输入证据                                                             |
| Family Correction | 家人确认、修改、不确定、不公开、删除                                                                |
| Narrative Agent   | 只基于 verified claims 生成章节草稿                                                        |
| Verifier Agent    | 四个 gate：citation coverage、unsupported claim、sensitive content、family confirmation |
| Consent           | 采访前同意、分享前二次同意、撤回、删除                                                               |
| 数字故事页             | 微信内私密访问，音频引用可播放                                                                   |
| PDF 导出            | 基础排版 PDF，可下载                                                                      |
| Pilot Metrics     | 100 户 pilot 的完成率、NPS、推荐率、错误投诉、人工处理时长                                              |

---

## 1.2 Out of Scope

| 不做                | 原因                                  |
| ----------------- | ----------------------------------- |
| 精装小册正式供应链         | Phase 2 再做；Phase 1 只允许 PDF 或样书 mock |
| AI 纪录片 / 视频生成     | 成本、深度合成合规、审核链路都不适合 Phase 1          |
| 历史背景卡片            | Phase 3 再做；Phase 1 避免引入政治/历史复杂度     |
| iOS / Android App | 回忆录是低频产品，Phase 1 必须微信内优先            |
| 家族树 / 多人物家族版      | 会显著增加数据模型和核验复杂度                     |
| 抢救服务              | 需要人工采访员和医疗/心理 SOP，Phase 3 再试点       |
| Avatar / 已故亲属对话   | Phase 4 前禁止                         |
| 公开 viral loop 依赖  | 大多数家庭故事是私域内容，不把抖音公开传播作为增长假设         |

---

## 2. Phase 1 成功指标

## 2.1 必过指标

| 指标        |     验收线 | 说明                                  |
| --------- | ------: | ----------------------------------- |
| 项目完成率     |   ≥ 70% | 入组家庭完成采访、核验、故事页                     |
| 有效采访完成率   |   ≥ 75% | 进入采访后完成 ≥15 分钟有效讲述                  |
| 家人核验完成率   |   ≥ 70% | P0 claims 完成确认/修改/不确定               |
| 重大事实错误投诉率 |   < 10% | 人名、地名、亲属关系、年份、工作单位等                 |
| 推荐率       |   ≥ 80% | 愿意推荐给亲友                             |
| NPS       |    > 50 | 进入 Phase 2 的关键门槛                    |
| 单户人工处理时长  | < 60 分钟 | 含客服、人工审核、异常处理                       |
| 证据覆盖率     |   ≥ 80% | final story 中事实句可追溯到 claim evidence |
| 付费/押金占比   |   ≥ 30% | 可用人工收款，不要求自动支付                      |

原路线图里 Phase 1 已经设置了 100 户内测、70% 完成率、80% 推荐率、重大事实错误投诉 <10%、NPS >50 的验收线；v3 增加工程与运营可规模化指标。

---

## 2.2 Kill / Pivot Signals

出现以下情况，Phase 2 不应启动：

| 信号                         | 处理                              |
| -------------------------- | ------------------------------- |
| 100 户里 <50 户完成采访           | 老人端 UX 或信任机制有根本问题               |
| 家人核验完成率 <50%               | 核验流程太重，需要重做                     |
| 重大事实错误投诉 ≥15%              | Claim extraction / verifier 不可用 |
| 单户人工处理 >90 分钟              | unit economics 不成立              |
| 用户喜欢概念但不愿交押金               | 需求停留在情绪赞同，不是真购买                 |
| 用户认为“AI 编得挺好”而不是“这真是我爸妈说的” | 产品心智偏了，需回到 evidence-first       |

---

## 3. 产品主流程

```text
1. 子女创建项目
2. 填写老人信息与采访主题
3. 上传照片，可选
4. 生成老人采访入口
5. 老人进入小程序/H5 采访页
6. 采访前同意
7. AI 语音采访
8. 音频上传 OSS
9. batch ASR + transcript cleanup
10. Extraction Agent 生成 claims
11. Photo hypothesis 生成，可选且内部标记
12. 生成待核验清单
13. 子女逐条确认 / 修改 / 不确定 / 不公开 / 删除
14. P0 claims 处理完成
15. Narrative Agent 生成章节
16. Verifier Agent 跑 gate
17. 通过后进入老人二次同意
18. 老人同意分享
19. 生成故事页 + PDF
20. 子女分享给家人
21. Pilot 反馈与指标统计
```

旧执行计划已经把端到端链路设计为小程序创建项目、上传照片、采访、转写、claim extraction、family correction、narrative、verifier、二次同意、分享页和 PDF；v3 保留这条主链路，但修正执行细节。

---

## 4. 技术栈

## 4.1 Pinned Stack

| 层                 | 选型                                           |
| ----------------- | -------------------------------------------- |
| Monorepo          | `changjuan/`                                 |
| Backend API       | Python 3.12 + FastAPI + SQLAlchemy 2.0       |
| Worker            | Celery + Redis                               |
| DB                | PostgreSQL 16 + pgvector                     |
| Migration         | Alembic                                      |
| Storage           | 阿里云 OSS + KMS                                |
| AI Router         | LiteLLM + 自建 task router                     |
| Structured Output | Pydantic v2 + instructor                     |
| Web Admin         | Next.js 15 + React 19 + Tailwind             |
| H5                | Next.js 15                                   |
| Mini Program      | 微信原生 + TypeScript                            |
| Test              | pytest / pytest-asyncio / Vitest             |
| Observability     | structlog + OpenTelemetry + Sentry + 阿里云 SLS |

## 4.2 禁止引入

* LangChain
* LangGraph
* Pydantic v1
* Flask
* 无类型裸 `requests/fetch`
* 未经 router 的 AI provider 直连
* 未审计的 admin 手工改库
* 任何 secret commit

---

## 5. Monorepo 结构

```text
changjuan/
├── apps/
│   ├── api/                  # FastAPI 主服务
│   ├── worker/               # Celery worker
│   ├── voice-pipeline/       # WebSocket voice runtime
│   ├── web-admin/            # 管理后台
│   └── web-h5/               # H5 营销页 / 入口页
├── miniprogram/              # 微信小程序
├── packages/
│   ├── schemas/              # Pydantic schemas
│   ├── prompts/              # versioned prompts
│   ├── providers/            # AI provider router
│   ├── shared-types/         # 前端共享 TS 类型
│   └── clients/              # typed API clients
├── infra/
│   ├── migrations/           # Alembic
│   ├── docker/
│   ├── deploy/
│   └── seed/
├── docs/
│   ├── SPEC.md
│   ├── runbooks/
│   └── adr/
├── scripts/
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

---

## 6. 数据模型 v3：权威修正版

这里不贴完整 SQL，只定义必须字段和修正点。Codex 生成 Alembic migration 时必须以本节为准。

---

## 6.1 Users：PII 不落明文

旧版问题：`users.phone_e164 VARCHAR(20)` 与“PII AES-256 加密”冲突。

v3 修正：

```sql
users (
  id UUID PK,
  wx_openid VARCHAR(64) UNIQUE NOT NULL,
  wx_unionid VARCHAR(64) UNIQUE NULL,

  phone_e164_enc BYTEA NULL,
  phone_hash VARCHAR(64) NULL,       -- HMAC-SHA256，用于查重/登录，不可逆
  realname_enc BYTEA NULL,

  nickname VARCHAR(64) NULL,
  avatar_url TEXT NULL,

  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  deleted_at TIMESTAMPTZ NULL
)
```

要求：

* 电话、真实姓名、身份证等 PII 只能加密存储。
* 查询手机号只能用 `phone_hash`。
* 日志永不输出明文 PII。
* 加密密钥来自 KMS，不在 `.env` 里放原始主密钥。

旧文档要求所有 PII AES-256 加密、删除请求 T+7、audit log 永不删除，但原 users 表还保留明文 phone 字段；v3 统一为加密字段 + hash 字段。

---

## 6.2 Audio / Transcript / Photos：必须支持 soft delete

旧版问题：删除规则要求 soft delete + 7 天后 purge，但部分表没有相关字段。

v3 要求以下表必须有：

```sql
deleted_at TIMESTAMPTZ NULL,
purge_after_at TIMESTAMPTZ NULL,
purged_at TIMESTAMPTZ NULL
```

适用表：

* `audio_recordings`
* `transcript_segments`
* `photos`
* `photo_analyses`
* `claims`
* `claim_evidence`
* `chapters`
* `citations`
* `story_pages`
* `share_links`
* `pdf_exports`

删除逻辑：

```text
用户请求删除
→ deletion_requests 创建记录
→ resource.deleted_at = now()
→ resource.purge_after_at = now() + 7 days
→ 前端立即不可见
→ T+7 worker 物理删除 DB record / OSS object
→ deletion_requests.executed_at = now()
```

例外：

* `audit_logs` 永不删除。
* `deletion_requests` 永不删除。
* `consent_records` 不物理删除，只做最小化脱敏保留。
* 若法务要求保留争议证据，只保留 hash、时间戳、操作记录，不保留原始音频/图片。

---

## 6.3 Admin / Ops 表必须进入 Phase 1 DDL

旧版问题：后续 sprint 引用了 admin notes、feedback、NPS、白名单，但 DDL 没有表。

v3 必须新增：

```sql
admin_users (
  id UUID PK,
  email VARCHAR(128) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(32) NOT NULL,          -- super_admin | ops | reviewer | readonly
  enabled BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL,
  last_login_at TIMESTAMPTZ NULL
)

admin_sessions (
  id UUID PK,
  admin_user_id UUID FK,
  token_hash VARCHAR(255) NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
)

internal_notes (
  id UUID PK,
  project_id UUID FK,
  admin_user_id UUID FK,
  note_type VARCHAR(32),              -- ops | review | support | risk
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
)

pilot_whitelist (
  id UUID PK,
  phone_hash VARCHAR(64),
  wx_openid VARCHAR(64),
  source VARCHAR(64),                 -- friend | xhs | wechat_article | manual
  invited_by VARCHAR(64),
  created_at TIMESTAMPTZ NOT NULL
)

feedback (
  id UUID PK,
  project_id UUID FK,
  user_id UUID FK,
  nps_score INTEGER,
  recommend BOOLEAN,
  issue_type VARCHAR(64),
  body TEXT,
  created_at TIMESTAMPTZ NOT NULL
)

support_tickets (
  id UUID PK,
  project_id UUID FK,
  user_id UUID FK NULL,
  admin_owner_id UUID FK NULL,
  status VARCHAR(32),                 -- open | pending | resolved | closed
  priority VARCHAR(16),               -- P0 | P1 | P2
  category VARCHAR(64),
  body TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
)
```

---

## 6.4 Payment：Phase 1 用“人工收款 + admin 标记”，不接微信支付

旧版问题：Go/No-Go 要求验证 ¥499+ deposit，但支付实现放到了 Phase 2。

v3 决策：

> **Phase 1 不接微信支付。用人工收款 / 转账 / 内测押金二维码，admin 后台标记支付状态。**

新增字段：

```sql
projects (
  payment_status VARCHAR(32) NOT NULL DEFAULT 'not_required',
  payment_cents INTEGER NOT NULL DEFAULT 0,
  payment_method VARCHAR(32) NULL,     -- manual_wechat | manual_alipay | waived | free_trial
  payment_reference VARCHAR(128) NULL,
  payment_marked_by_admin_id UUID NULL,
  payment_at TIMESTAMPTZ NULL
)
```

API 返回：

```json
{
  "project_id": "uuid",
  "status": "created",
  "payment_required": true,
  "payment_mode": "manual",
  "payment_instruction": "请联系内测运营完成押金支付"
}
```

Phase 2 再接：

* 微信支付
* 支付宝
* 自动退款
* invoice/order 系统

---

## 6.5 Publish Gate：禁止危险强制发布

旧版问题：admin 可以 force publish，但这会绕过 Verifier 和同意链路。

v3 规则：

项目进入 `published` 必须同时满足：

```text
1. project.status = elder_second_consent_pending
2. 所有 P0 claims 的 verification_status ∈ {confirmed, modified, marked_unsure, rejected}
3. 没有 unresolved block-level verification_issues
4. 至少存在一条 family_sharing consent_record
5. story_page 已生成
6. share_links 默认 disabled，发布后才 enabled
```

Admin 权限：

| 操作                          | 允许吗               |
| --------------------------- | ----------------- |
| 重跑 verifier                 | 允许                |
| 标记 issue resolved           | 允许，但必须写理由         |
| 将 P0 claim 改为 marked_unsure | 允许，但必须进入故事页“待确认”区 |
| 跳过老人二次同意                    | 禁止                |
| 有 block issue 时 publish     | 禁止                |
| P0 未处理时 publish             | 禁止                |
| 直接 SQL 改状态                  | 禁止                |

状态机必须以代码实现，不允许前端或 admin API 自行写状态。

---

## 6.6 Session 状态统一

统一使用：

```sql
session_status ENUM (
  'scheduled',
  'in_progress',
  'completed',
  'aborted_by_storyteller',
  'aborted_technical',
  'completed_short'
)
```

禁止出现：

```text
in_session
running
started
finished
```

---

## 7. API Contract v3

## 7.1 Base URL

统一：

```text
Base URL = https://api.changjuan.com
所有 endpoint 显式写 /api/v1/...
```

不要写：

```text
Base URL = https://api.changjuan.com/api/v1
Endpoint = /api/v1/...
```

避免双前缀。

---

## 7.2 通用响应

```json
{
  "code": 0,
  "data": {},
  "message": "ok",
  "trace_id": "uuid"
}
```

常用错误码：

|  code | meaning                 |
| ----: | ----------------------- |
| 40001 | invalid request         |
| 40101 | unauthenticated         |
| 40301 | forbidden               |
| 40401 | not found               |
| 40901 | state conflict          |
| 42201 | precondition failed     |
| 42901 | rate limited            |
| 50001 | internal error          |
| 50002 | upstream provider error |

---

## 7.3 Auth

```text
POST /api/v1/auth/wx-login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
```

---

## 7.4 Projects

```text
POST /api/v1/projects
GET  /api/v1/projects
GET  /api/v1/projects/{project_id}
PATCH /api/v1/projects/{project_id}
DELETE /api/v1/projects/{project_id}
```

创建项目时：

```json
{
  "storyteller": {
    "display_name": "爸爸",
    "relation_to_payer": "father",
    "birth_year": 1954,
    "birth_place": "江苏南通",
    "current_city": "上海",
    "primary_dialect": "mandarin"
  },
  "title": "爸爸的故事",
  "themes": ["childhood", "work", "family"],
  "tier": "standard"
}
```

返回：

```json
{
  "project_id": "uuid",
  "status": "created",
  "payment_required": true,
  "payment_mode": "manual",
  "next_action": "complete_manual_deposit"
}
```

---

## 7.5 Photos

```text
POST /api/v1/projects/{project_id}/photos/presign
POST /api/v1/projects/{project_id}/photos/complete
GET  /api/v1/projects/{project_id}/photos
DELETE /api/v1/photos/{photo_id}
```

Phase 1 中 photo analysis 只作为 internal hypothesis，不进入用户承诺。

---

## 7.6 Interview

```text
POST /api/v1/projects/{project_id}/interview-sessions
GET  /api/v1/interview-sessions/{session_id}
POST /api/v1/interview-sessions/{session_id}/start
POST /api/v1/interview-sessions/{session_id}/end
WS   /api/v1/interview-sessions/{session_id}/stream
```

Audio chunk 规则：

```text
chunk_duration_ms = 300–500ms
max_chunks_per_minute = 240
```

解释：

* 300ms chunk → 200 chunks/min
* 500ms chunk → 120 chunks/min
* 限流 240/min 有 20% buffer
* 禁止 100ms chunk + 200/min rate limit 的冲突设计

---

## 7.7 Corrections

```text
GET  /api/v1/projects/{project_id}/corrections/pending
GET  /api/v1/claims/{claim_id}
POST /api/v1/claims/{claim_id}/corrections
POST /api/v1/projects/{project_id}/corrections/complete
```

Correction action：

```text
confirm
modify
unsure
hide_from_family
delete
```

规则：

* P0 claims 必须处理。
* `delete` 不物理删除，只 soft delete。
* `unsure` 可进入“待确认”区域，不进入事实叙事正文。
* `hide_from_family` 不进入故事页，但保留 audit。

---

## 7.8 Narrative / Story

```text
POST /api/v1/projects/{project_id}/drafts/generate
GET  /api/v1/projects/{project_id}/drafts
POST /api/v1/projects/{project_id}/verify
POST /api/v1/projects/{project_id}/request-second-consent
POST /api/v1/projects/{project_id}/publish
GET  /api/v1/story-pages/{story_page_id}
POST /api/v1/story-pages/{story_page_id}/share-links
POST /api/v1/story-pages/{story_page_id}/pdf-export
```

`publish` 必须检查 Publish Gate，不允许 admin override。

---

## 7.9 Admin API

```text
POST /api/v1/admin/auth/login
GET  /api/v1/admin/projects
GET  /api/v1/admin/projects/{project_id}
POST /api/v1/admin/projects/{project_id}/notes
POST /api/v1/admin/projects/{project_id}/mark-payment
POST /api/v1/admin/verification-issues/{issue_id}/resolve
POST /api/v1/admin/tasks/{task_id}/retry
GET  /api/v1/admin/metrics/pilot
GET  /api/v1/admin/support-tickets
PATCH /api/v1/admin/support-tickets/{ticket_id}
```

Admin 所有写操作必须进入 `audit_logs`。

---

## 8. AI Provider Routing

## 8.1 Task Types

```python
class TaskType(StrEnum):
    REALTIME_STT = "realtime_stt"
    BATCH_TRANSCRIPTION = "batch_transcription"
    INTERVIEWER_TTS = "interviewer_tts"
    INTERVIEW_NEXT_QUESTION = "interview_next_question"
    CLAIM_EXTRACTION = "claim_extraction"
    CONTRADICTION_DETECTION = "contradiction_detection"
    PHOTO_HYPOTHESIS = "photo_hypothesis"
    NARRATIVE_GENERATION = "narrative_generation"
    VERIFICATION = "verification"
```

---

## 8.2 Routing Table

| Task                    | Primary                  | Backup               |
| ----------------------- | ------------------------ | -------------------- |
| REALTIME_STT            | Volcengine streaming ASR | Aliyun Paraformer    |
| BATCH_TRANSCRIPTION     | Xunfei ASR               | Tongyi Tingwu        |
| INTERVIEWER_TTS         | Volcengine TTS           | Minimax / Aliyun TTS |
| INTERVIEW_NEXT_QUESTION | DeepSeek                 | Doubao               |
| CLAIM_EXTRACTION        | DeepSeek                 | Doubao               |
| CONTRADICTION_DETECTION | DeepSeek                 | Doubao               |
| PHOTO_HYPOTHESIS        | Qwen3-VL                 | Doubao Vision        |
| NARRATIVE_GENERATION    | DeepSeek                 | Doubao               |
| VERIFICATION            | DeepSeek                 | Doubao               |

要求：

* 所有 provider 调用必须经 `packages/providers/router.py`。
* 失败 3 次切 backup。
* 每次调用记录 `generation_runs`。
* prompt 必须有 `prompt_version` 和 `prompt_hash`。
* raw input/output 存 OSS，路径进入 `generation_runs`。

旧计划已有 provider-neutral router 和外部 provider 设计；v3 保留这个结构。

---

## 9. Agent Contract

## 9.1 Capture Agent

输入：

```json
{
  "project_context": {},
  "storyteller_profile": {},
  "themes": [],
  "confirmed_photo_captions": [],
  "recent_transcript": [],
  "session_state": {}
}
```

输出：

```json
{
  "next_utterance": "string",
  "action": "ask_followup | switch_topic | pause | suggest_end | end_session",
  "topic": "childhood | work | family | migration | open",
  "safety_flag": "none | emotional_distress | refusal | health_risk"
}
```

硬规则：

* 一次只问一个问题。
* 不主动深挖创伤。
* 老人拒答立即换话题。
* 沉默 5–10 秒内不催促。
* 长时间沉默后温和提示是否休息。
* 不纠错老人。
* 不做心理治疗。
* 不使用“您一定很痛苦吧”这类引导性语言。

Trauma & Grief Handling 在宪章 v2 中已经被定义为必须设计：拒答合法、情绪激动时建议停止、不主动深挖、不写苦情。

---

## 9.2 Extraction Agent

输入：

```json
{
  "transcript_segments": [],
  "photo_hypotheses": [],
  "user_inputs": {}
}
```

输出：

```json
{
  "claims": [
    {
      "claim_text": "父亲1978年进入县供销社工作",
      "claim_type": "work",
      "claim_priority": "P0",
      "entities": {
        "person": ["父亲"],
        "organization": ["县供销社"],
        "date": ["1978年"]
      },
      "source_segment_ids": [],
      "confidence": 0.82,
      "support_status": "supported",
      "sensitivity_level": "normal"
    }
  ]
}
```

P0 类型：

* 人名
* 亲属关系
* 关键年份
* 地名
* 学校
* 单位
* 迁徙路径
* 重大人生事件
* 敏感事件

---

## 9.3 Photo Hypothesis Agent

Phase 1 状态：

```text
feature_flag = internal_photo_hypothesis_only
```

规则：

* 不对用户承诺“AI 看懂老照片”。
* 所有输出必须使用“可能 / 大约 / 推测”。
* confidence < 0.5 的结果不得进入采访 prompt。
* 未经家人确认的 photo hypothesis 不进入故事正文。
* 只作为采访线索和核验问题候选。

旧文档也要求 VLM 输出必须标记为 hypothesis，并使用“可能/大约/推测”等限定词；v3 进一步规定它不是 Phase 1 验收项。

---

## 9.4 Narrative Agent

输入只能来自：

* `confirmed` claims
* `modified` claims
* `marked_unsure` claims，但只能进入“待确认”区
* confirmed photo captions
* family comments
* user inputs

禁止：

* 编造心理活动
* 补不存在的细节
* 写苦情文学
* 将历史背景混入个人事实
* 把 unsure claim 写成确定事实
* 使用“她至今仍然眼眶湿润”这类无证据描写

输出章节：

1. 开篇：这个人是谁
2. 童年与家庭
3. 求学与成长
4. 工作与迁徙
5. 婚姻与子女
6. 家人记住的几件事
7. 给后辈的话
8. 待确认事实与原声附录

---

## 9.5 Verifier Agent

四个 gate：

| Gate                | Block 条件                                      |
| ------------------- | --------------------------------------------- |
| Citation Coverage   | 事实句无 claim_ids                                |
| Unsupported Claim   | claim 无 evidence 或 support_status=unsupported |
| Sensitive Content   | sensitive/highly_sensitive 未经人工审核             |
| Family Confirmation | P0 claims 未处理                                 |

Verifier 输出：

```json
{
  "passed": false,
  "issues": [
    {
      "gate": "unsupported_claim",
      "severity": "block",
      "message": "该句缺少音频或家人确认证据",
      "chapter_id": "uuid",
      "citation_id": "uuid"
    }
  ]
}
```

只有 `passed = true` 才能进入二次同意流程。

---

## 10. Sprint Plan

## Sprint 0：Spec Freeze，3 天

交付：

* `docs/SPEC.md` 写入 v3
* ADR-001：为什么 Phase 1 不做视频/精装/历史卡片/app
* ADR-002：为什么支付用 manual deposit
* ADR-003：为什么 VLM 只做 internal hypothesis
* GitHub Project / Linear 初始化
* CI skeleton

DoD：

* 全员确认本文档为唯一 spec
* 所有 ticket 带 owner、依赖、DoD
* `.env.example` 完整
* CI 能跑空测试

---

## Sprint 1：Monorepo + Infra + DDL，1 周

交付：

* monorepo 初始化
* FastAPI app skeleton
* Celery worker skeleton
* Next.js admin skeleton
* 小程序 skeleton
* PostgreSQL + Redis + OSS dev config
* Alembic migration v1
* PII encryption utility
* audit log utility
* admin RBAC tables
* deletion fields 完整覆盖

DoD：

* `make dev` 本地启动 API / worker / admin
* `alembic upgrade head` 成功
* encryption unit test 100% 通过
* 所有 PII 日志脱敏
* DDL 包含 soft delete / purge 字段

---

## Sprint 2：Auth + Project + Manual Payment，1 周

交付：

* 微信登录
* JWT / refresh token
* 项目创建
* storyteller 创建
* pilot whitelist
* admin login
* admin mark payment
* 项目状态机 v1

DoD：

* 白名单用户可创建项目
* 非白名单用户看到友好提示
* admin 可标记 manual deposit
* 未支付项目不能进入采访发起
* 状态机非法 transition 返回 40901

---

## Sprint 3：Photo Upload + Interview Session Setup，1 周

交付：

* OSS presigned upload
* photo upload complete
* thumbnail generation
* interview session 创建
* elder-entry 页面
* consent page
* consent record 写入

DoD：

* 小程序可上传 3–10 张照片
* 老人入口链接可打开
* 采访前必须完成同意
* consent audio/text evidence 可回溯
* photo hypothesis 不对用户展示为事实

---

## Sprint 4：Voice Pipeline MVP，2 周

交付：

* WebSocket voice session
* audio chunk 300–500ms
* 限流 240 chunks/min
* 火山 streaming ASR
* 火山 TTS
* Capture Agent prompt v1
* partial transcript
* audio OSS upload
* session recovery

DoD：

* 15 分钟采访不中断
* 弱网下 chunk 缓存可恢复
* 老人可说“今天先到这里”结束
* 拒答后 agent 不再追问该话题
* session 状态只使用统一 enum
* audio + transcript 可在 admin 回放/查看

---

## Sprint 5：Batch Transcription + Claim Extraction，2 周

交付：

* 讯飞 batch ASR
* transcript cleanup
* segment confidence
* low-confidence review flag
* Extraction Agent
* Claim Ledger
* Claim Evidence
* claim embeddings
* claim dedup
* contradiction detection v0

DoD：

* 每条 claim 至少绑定一个 evidence
* P0/P1/P2 分类可用
* 低 confidence transcript 进入待核验
* 日期/地点矛盾可识别
* claim 合并有 unit test
* fixture transcript 能稳定抽出关键 claims

---

## Sprint 6：Photo Hypothesis Internal Mode，1 周

交付：

* Qwen3-VL photo hypothesis
* feature flag
* photo_analyses table
* admin-only display
* 可转成 correction candidate

DoD：

* 输出全部带 uncertainty
* confidence <0.5 不进采访 prompt
* 用户端不显示“AI 已识别”
* 家人确认前不进入 narrative

---

## Sprint 7：Family Correction Workflow，2 周

交付：

* 待核验列表
* 单条 claim 详情
* 音频片段播放
* confirm / modify / unsure / hide / delete
* 批量进度
* correction history
* P0 completion gate

DoD：

* P0 claims 排在最前
* 每次最多展示 20 条，避免疲劳
* 修改后 claim_text 用 modified_text
* delete 走 soft delete
* P0 未处理时不能生成正式 narrative
* 所有 correction 写 audit log

---

## Sprint 8：Narrative Generation，1 周

交付：

* Narrative Agent prompt v1
* Chapter schema
* Citation Binder
* draft generation task
* draft preview API
* markdown rendering

DoD：

* narrative 只使用 allowed claims
* 每个事实句有 claim_ids
* unsure claims 只进“待确认”区
* 没有 evidence 的句子被剔除
* 生成失败可重试

---

## Sprint 9：Verifier + Sensitive Review，1 周

交付：

* Verifier Agent
* verification_issues
* block/warn/info
* sensitive content classifier
* admin sensitive review queue
* issue resolve workflow

DoD：

* 四个 gate 都有测试
* unresolved block issue 禁止二次同意
* sensitive claim 未人工处理不能 publish
* admin resolve 必须写理由
* 无 admin force publish

---

## Sprint 10：Story Page + PDF，2 周

交付：

* story page
* share link
* password protection
* audio citation playback
* family comments
* PDF export
* link revoke
* access log

DoD：

* 家人可微信内查看
* 可听原声片段
* 可导出 PDF
* 分享链接可关闭/重置
* 密码保护生效
* PDF 不暴露 hidden claims

---

## Sprint 11：Second Consent + Publish Gate，1 周

交付：

* 二次同意页面
* 核心内容摘要
* 老人语音/文字确认
* publish gate implementation
* story page enable

DoD：

* 没有二次同意不能发布
* P0 未处理不能发布
* block issue 未解决不能发布
* audit log 记录 publish decision
* share link 默认 disabled，publish 后启用

---

## Sprint 12：Privacy / Export / Delete，1 周

交付：

* 隐私设置页
* 项目导出
* 删除请求
* T+7 purge worker
* OSS object deletion
* audit retained
* deletion status 查询

DoD：

* 用户删除后前端立即不可见
* 7 天后物理删除可测试
* audio/photos/pdf 从 OSS 删除
* audit logs 保留但脱敏
* e2e deletion_request 通过

---

## Sprint 13：Admin Ops + Metrics，1 周

交付：

* pilot dashboard
* project funnel
* stuck project alert
* support tickets
* internal notes
* NPS / feedback form
* cost tracking
  -人工处理时长记录

DoD：

* 每户状态可追踪
* 每户 AI 成本可导出
* 每户人工介入次数可导出
* NPS / 推荐率可统计
* 卡点项目可推给运营 owner

---

## Sprint 14：Hardening + QA，1 周

交付：

* rate limit
* Sentry
* OTEL tracing
* DB backup
* OSS backup
* security pass
* mobile compatibility QA
* legal copy finalization

DoD：

* 42901 限流生效
* 模拟 500 有告警
* restore 演练成功
* 三种 iPhone + 三种 Android 通过
* 微信内录音权限正常
* consent/privacy 文案确认

旧测试计划已经要求状态机、Claim Ledger、Verifier、Extraction、Capture、PII、Provider Router 等核心模块测试覆盖，并要求 e2e 覆盖删除、provider failover、敏感内容、矛盾 claims 等场景；v3 保留这些测试方向。

---

## Sprint 15–16：100 户 Pilot，2 周

样本结构：

| 类型          | 户数 |
| ----------- | -: |
| 标准礼物型       | 40 |
| 父母大寿型       | 20 |
| 春节/返乡触发型    | 15 |
| 轻抢救/早期记忆衰退型 | 15 |
| 跨城/跨国家庭     | 10 |

每户最低交付：

* 1 位老人
* 1 次 ≥15 分钟采访
* 1 份 Claim Ledger
* 1 轮家人核验
* 1 个数字故事页
* 1 份 PDF
* 1 次 NPS / 推荐意愿回访

DoD：

* 完成率、推荐率、NPS、重大事实错误投诉率可导出
* 单户人工处理时长可导出
* 退款/放弃原因分类
* 形成 `docs/reports/phase1-retrospective.md`
* Go/No-Go 结论明确

旧计划也把 Sprint 15–16 设置为 100 户 Pilot，并要求完成度统计、退款处理、复盘报告和 Phase 2 准备；v3 将 pilot 指标与 Go/No-Go 直接绑定。

---

## 11. 测试策略

## 11.1 Unit Test Coverage

| 模块               |  覆盖率 |
| ---------------- | ---: |
| State Machine    | ≥95% |
| PII Encryption   | 100% |
| Claim Ledger     | ≥85% |
| Verifier Agent   | ≥85% |
| Provider Router  | ≥80% |
| Capture Agent    | ≥75% |
| Extraction Agent | ≥70% |
| Narrative Agent  | ≥70% |

## 11.2 E2E Scenarios

必须覆盖：

1. `happy_path_short_interview`
2. `storyteller_aborts_early`
3. `dialect_low_confidence`
4. `contradictory_claims`
5. `sensitive_content_workflow`
6. `deletion_request_t_plus_7`
7. `provider_failover`
8. `manual_payment_required`
9. `publish_blocked_without_second_consent`
10. `publish_blocked_with_unresolved_issue`
11. `audio_chunk_rate_limit_normal_case`
12. `admin_cannot_force_publish`

---

## 12. Ralph / Codex 执行规则

Ralph Loop：

```text
loop:
  1. 取下一个未完成 ticket
  2. 读取本 spec 对应章节
  3. 实现最小变更
  4. 补测试
  5. 跑 lint/typecheck/test
  6. 若通过：commit
  7. 若失败：记录 blocker，不得瞎改 spec
  8. 连续 5 个 blocker 停止
```

提交规则：

```text
feat(api): add manual payment marking [S2-004]
fix(voice): align audio chunk limit with 300ms chunks [S4-003]
test(verifier): block publish with unresolved issues [S9-002]
```

禁止：

* 未经 spec 擅自改技术栈
* 用 mock 伪装真实 provider 接入
* 绕过状态机改项目状态
* admin 强制 publish
* 明文 PII 入库
* 任何 AI output 未经 verifier 进入 published
* 把 VLM hypothesis 写成事实
* 把 Phase 2 feature 偷偷塞进 Phase 1

---

## 13. 最终 Go / No-Go

## Go：进入 Phase 2 的条件

必须同时满足：

| 条件       |               通过线 |
| -------- | ----------------: |
| 100 户完成率 |              ≥70% |
| 有效采访完成率  |              ≥75% |
| 家人核验完成率  |              ≥70% |
| 重大事实错误投诉 |              <10% |
| NPS      |               >50 |
| 推荐率      |              ≥80% |
| 单户人工处理时长 |            <60 分钟 |
| 押金/付费占比  |              ≥30% |
| CAC 初步估算 | 可控制在 ¥200–400 区间内 |

## No-Go：停止或重做

任一触发：

* 用户不愿意付 ¥499 押金
* 老人采访失败率过高
* 核验流程没人做
* AI 输出被普遍认为“像编的”
* 客服/人工审核成本吞掉毛利
* 隐私/同意流程引发明显不信任
* 重大事实错误无法通过 Family Correction 压住

---

## 14. Phase 1 最终交付清单

Phase 1 结束时，必须有：

1. 微信小程序 MVP
2. H5 入口页
3. 管理后台
4. FastAPI backend
5. Celery worker
6. voice-pipeline
7. OSS/KMS 存储链路
8. PII encryption
9. audit logs
10. deletion worker
11. Claim Ledger
12. Family Correction Workflow
13. Narrative Agent
14. Verifier Agent
15. 二次同意流程
16. 私密故事页
17. PDF 导出
18. Pilot dashboard
19. 100 户内测数据
20. Phase 1 retrospective
21. Phase 2 Go/No-Go 决策

---

## 最终判断

这版可以执行。

核心变化是：**把 Phase 1 从“功能很多的 AI 回忆录产品”改成“执行安全的可信记录系统”**。
Ralph/Codex 可以按这版开工；不要再用旧版 plan。
