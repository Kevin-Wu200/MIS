# AI 功能集成评估

## 异常检测

- 实现位置：`backend/ai.py`
- 策略：采用历史 z-score + 固定环境阈值 + **时间维度分析** 组合，对温度、湿度、PM2.5、气压、露点温度、热指数、风速等生成 `anomaly_score`。
- 实时性：上传接口只执行轻量评分，复杂摘要生成放入 `BackgroundTasks`，避免阻塞数据写入主流程。
- 异常阈值：`anomaly_score >= 0.75` 标记为 `is_anomaly = true`。
- 模型版本：`rules-zscore-time-v3`

## 时间维度分析（v3 新增）

基于气象学理论的六项时间维度规则：

### 1. 气压倾向分析 (Pressure Tendency)
- **来源**：气压倾向 (Barometric Tendency) 气象学理论
- 3小时内下降 >2hPa → 风暴/冷锋逼近预警
- 3小时内上升 >3hPa → 天气转晴（注意突变）
- 持续低于 990hPa → 风暴系统停留

### 2. 温度变化率 (Temperature Rate of Change)
- **来源**：Diurnal Temperature Variation + 冷锋气象理论
- 1小时内下降 >5°C → 冷锋过境/寒潮预警
- 1小时内上升 >4°C → 暖锋逼近/焚风效应

### 3. 露点差分析 (Dew Point Spread)
- **来源**：Dew Point 气象学理论
- 温度-露点 <2°C → 浓雾/凝结风险
- 露点 >20°C → 高湿热不适
- 露点 <0°C 且接近气温 → 霜冻风险

### 4. 热指数危险等级 (Heat Index Danger)
- **来源**：Steadman 热指数公式 (1979)
- HI >40°C → 危险（中暑风险较高）
- HI >54°C → 极度危险（建议停止野外作业）

### 5. 连续异常模式 (Consecutive Anomaly Pattern)
- 同一设备连续 ≥3 条异常 → 持续性环境风险
- 24小时内 ≥5 条异常 → 系统性问题

### 6. 多参数协同趋势 (Multi-parameter Trend)
- 升温+降压 → 暖锋/低压系统逼近
- 降温+升压 → 冷锋过境后/高压控制
- 升温+降湿 → 干燥热风/焚风效应

## 新增参数

| 字段 | 类型 | 说明 | 气象学依据 |
|---|---|---|---|
| dew_point | REAL | 露点温度 (°C) | Magnus公式自动计算 |
| heat_index | REAL | 热指数/体感温度 (°C) | Steadman公式自动计算(≥27°C) |
| wind_speed | REAL | 风速 (m/s) | Beaufort风级分类 |
| wind_direction | REAL | 风向 (0-360°) | 气象学标准 |

## LLM 洞察

- 默认行为：未配置密钥时使用本地规则摘要，保证离线可运行。
- 可选配置：
  - `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`
  - `AI_LLM_BASE_URL`，默认 `https://api.deepseek.com/v1`
  - `AI_LLM_MODEL`，默认 `deepseek-chat`
- 输出字段：单条数据摘要写入 `ai_summary`，聚合洞察由 `/api/ai/insights` 返回。v3 新增 `time_dimension_alerts` 字段。

## 性能影响

- 上传主流程新增时间维度查询（同设备3h/1h/24h历史），预期 10-30ms。
- LLM 调用通过后台任务执行，不进入上传 API 响应路径。
- 建议压测指标：
  - `POST /api/data` P95 延迟
  - 后台摘要任务成功率
  - `/api/ai/insights` 查询耗时

## 成本估算

- 单条摘要提示词约 200-350 tokens，输出约 50-150 tokens（v3 新增时间维度告警信息）。
- 若每天 10,000 条记录全部调用 LLM，日消耗约 250 万至 500 万 tokens。
- 成本控制建议：
  - 仅对异常记录调用 LLM；
  - 对批次数据生成摘要，而不是每条记录生成摘要；
  - 缓存 `ai_summary`，避免重复生成。

## 数据库优化

- `is_anomaly` 普通索引：支持快速筛选异常记录。
- `anomaly_score DESC` 索引：支持按风险排序。
- `ai_metadata` GIN 索引：支持按模型版本、算法参数等 JSONB 元数据过滤。
- `(device_id, timestamp)` 联合索引：加速时间维度历史查询。

