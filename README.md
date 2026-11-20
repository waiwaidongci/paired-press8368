# 栖木印刷套印格图分析簿

两道工艺色差格图按纸样与定位角对齐 → 同向越门槛斑块 → 逐张整图符号翻转、以最大斑块面积给出校正 p 值；容量限 14 张纸、每图 96×96 格，全枚举限 60 秒。原生 HTML/CSS/JavaScript 多模块工作席，所有计算由 Python 完成。

## 为什么不只看整纸平均色差
整张纸的平均色差会把成片、同向的套印偏差与反向波动相互抵消，从而**盖住**真实的套印问题。因此本簿在保留原平均色差分析的同时，以格图为单位检测"越过门槛、方向一致、四邻接相连"的斑块，并用整图符号翻转检验斑块是否大到非偶然。

## 模拟业务
栖木研究协作组，12 名分析师与业务人员，日常使用 `paired-press-202611-1.csv` 手工抄表。当前三个痛点：观测与口径不可追溯、重算易出错、结果与复核割裂。上游提供独立合成业务观测；本应用接管格图登记、方法执行和输入冻结；下游负责人形成复测/预算方案，观察员获取复核后的 CSV。

核心业务实体：PressStudy / PressSheet / GridRun / Review。源码 model/schema/service/controller/route 与前端 api/store/pages 完成链路，不依赖浏览器本地假数据。

## 数据与对齐规则
- 每张**纸样**分别补传**两道工艺**（工艺A、工艺B）的色差格图；同版两侧行列必须一致，齐备后才一次性对齐。
- 每张纸带**定位角**（0/90/180/270°）。算法把格图旋转回统一物理坐标后再逐格配对；方阵格图支持全部四个角度，矩形格图仅支持 0/180°（90/270° 会交换行列、无法与同版对齐，排队前即 422 拒绝）。
- **逐格配对**：同一纸样上两工艺都实测的格才成对；缺测（null/空/NA/-）不补值、不插补。每个格至少有 **2 张纸**成对实测才进入统计。
- 容量：同一研究最多 **14 张纸**，单张格图每维最多 **96 格（96×96）**，超出拒绝录入/排队。

## 方法
1. 对每格计算跨纸的平均配对差（工艺B − 工艺A）。
2. 取绝对值**严格大于门槛** `threshold`（ΔE，>0）的格；正、负方向分别处理，按**四邻接**（不含对角）连成斑块。
3. 记录观测到的**最大斑块面积**。
4. **逐张整图符号翻转**：在零假设下，每张纸的整张差值格图共用一个符号（不逐格独立翻转）。枚举全部 2^S 种符号组合（S=纸张数，S≤14），对每种组合重算斑块并取最大面积。
5. 校正 p 值采用**加一校正** `(命中数+1)/(组合数+1)`，避免 p=0。全枚举向量化分块执行，硬限时 **60 秒**，超时任务失败并保留错误。
6. 原整纸平均色差、配对差 t 区间等口径**照用保留**，与斑块/校正 p 并列展示。

每次运行冻结参数、格图快照和 SHA256。Redis 任务由独立 worker 计算，写 DB 与共享产物卷；输入修改不会改写历史结果。负责人复核不可覆盖；审计记录登录、数据改动、排队、复核与导出；240 请求/分钟限流、全局可恢复错误。

## 快速启动
```bash
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```
访问 http://localhost:18242 ，API http://localhost:19242/docs 。数据库映射 17742。无需 Node 构建。可以从中文和带空格目录启动。清理 `docker compose down -v --remove-orphans` 会删除本题演示数据卷。

|角色|账号|密码|权限与典型动作|
|---|---|---|---|
|admin 负责人|admin@demo.local|Research2026!|全部读写、批准复核、下载|
|analyst 分析师|analyst@demo.local|Research2026!|数据修改、创建任务、读取结果及下载；不能复核|
|viewer 观察员|viewer@demo.local|Research2026!|只读；仅可导出已复核结果|

## 一天的工作剧本
1. 09:00 admin 登录，查"栖木·米白纸套印"。
2. 09:10 analyst 在来源页分版补传工艺A、工艺B两张格图，选择定位角；缺测格留空。
3. 09:15 系统校验双版尺寸、矩形/方阵角度兼容性与 14 张容量，不合格当场拒绝。
4. 09:20 分析执行页设置门槛 `{"threshold": 1.5}`，命名本轮研究。
5. 09:21 冻结配对格图与门槛并排队，worker 实算，结果页自动刷新。
6. 09:25 查看热图斑块标注、校正 p 值、每格样本数，以及保留的原平均色差；失败先修格图重跑。
7. 09:35 admin 打开业务复核，写明限制与下一步动作，归档后不可覆盖。
8. 09:40 viewer 读取复核意见并下载含斑块与每格样本数的 CSV，在操作留痕页核对下载事件。

## 结果页与导出
- 热图以颜色区分正/负向越门槛斑块，斜纹格表示样本不足或缺测；悬停每格显示平均配对差与**成对样本数**。
- 核心数值同时给出斑块数、最大斑块面积、**校正 p 值（加一）**、符号组合数/命中数、枚举耗时，以及原平均色差口径。
- CSV 导出含指标、斑块明细（编号/面积/方向/格坐标）与逐格的平均差、样本数、斑块编号。

## 技术与目录
|部分|实现|
|---|---|
|前端|原生 ES modules、HTML/CSS、Nginx1.27，无前端框架|
|API|Python3.11、FastAPI0.115、SQLAlchemy2、JWT、PBKDF2 密码|
|计算|NumPy2.2、SciPy1.15（`scipy.ndimage.label` 四邻接连通）|
|数据库|PostgreSQL16|
|任务|Redis7 持久队列，Python 独立 worker，心跳 healthcheck|

`frontend/src/` 分 api、stores、types、components/common、hooks、pages、router、utils、constants；`backend/src/` 分 config、models、schemas、services、controllers、routes、middlewares、utils、constants；`backend/scripts/seed_demo.py` 自然键插入、重复不覆盖修改；`backend/migrations/README.md` 说明 schema 版本。

环境变量 `.env.example`：COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、DB_PASSWORD、JWT_SECRET、SEED_DEMO。开发时在本地 venv 安装 backend/requirements.txt，设置 DATABASE_URL、REDIS_URL、JWT_SECRET 再运行 uvicorn；前端开发经 Nginx 代理 `/api/` 到不带前缀的 API。

共享枚举：角色 admin/analyst/viewer 和队列 queued/running/completed/failed；后端 `src/constants/enums.py`、认证与 worker 使用相同值；前端 `src/types/enums.js`、状态与角色界面使用相同值。Google Fonts：Noto Serif SC + IBM Plex Mono；断网使用 serif/monospace 回退。

## 算法输入、失败态与复现
输入为选定批次全部纸样的双工艺格图和门槛参数，输出核心数值、格图/斑块、每格样本数与解释；参数经后端严格白名单和范围验证（仅 `threshold`）。空批次拒绝；格图非矩形/非有限数/负值/双版尺寸不一致/角度不兼容/超容量拒绝；没有任何格具备 ≥2 张成对实测时任务 failed 并保留错误；全枚举超 60 秒 failed。固定种子 42 的合成数据、输入 checksum 相同可复现。独立 oracle：纯 Python 暴力重算最大斑块与全枚举 p；交换两工艺后差值符号反转、最大斑块面积与校正 p 不变；缺测不补值。

已知边界：小型本地研究应用，使用合成数据，不含企业 SSO 与外发邮件；结果由人工复核，不自动执行业务决策；单 worker 恢复 queued/running 任务，数据库与 Redis 间未采用分布式事务。实际验证结果见 TESTING.md。

MIT License。
