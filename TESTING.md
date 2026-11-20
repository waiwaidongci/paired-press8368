# 测试与验证记录

验证环境：本地 Python 3.11 venv，NumPy 2.2.1 / SciPy 1.15.1 / FastAPI 0.115.6 / SQLAlchemy 2.0.36。
应用目标运行时为 docker compose（PostgreSQL16 + Redis7），下列离线测试用 SQLite + 假 Redis 覆盖等价的服务/算法/路由逻辑，未启动容器。

## 测试脚本（位于仓库外的临时目录，独立于交付代码）
- `test_algorithm.py`：算法单元 + 纯 Python 暴力 oracle（独立重算四邻接斑块与 2^S 全枚举 p）。
- `test_integration.py`：SQLite 上从录入→冻结→实算→导出→复核→角色权限的服务级端到端。
- `test_http.py`：FastAPI TestClient 路由级冒烟，含鉴权、422/403/409、队列、结果字段与 CSV 内容。

## 覆盖的规格要点与结果（全部通过）
1. 双工艺格图、同版尺寸一致、定位角 0/90/180/270 旋转对齐；方阵支持四角，矩形仅 0/180，冲突在排队前 422。
2. 逐格配对：两工艺均实测才成对；缺测不补值；每格 ≥2 张成对才入统计，样本不足格标记且平均差为 null。
3. 越门槛为严格大于：恰等于门槛不计；正/负方向分别按四邻接连块，对角不连通，搭桥后连通。
4. 逐张整图符号翻转（非逐格），枚举 2^S 组合，最大斑块面积的加一校正 p 与纯 Python oracle 完全一致。
5. 交换两工艺：差值符号反转，最大斑块面积与校正 p 不变。
6. 容量：>14 张、每图 >96 格拒绝；全枚举 60 秒超时会抛出并使任务失败。
7. 原平均色差、配对差 t 区间等口径保留。
8. 复核不可覆盖（409）；viewer 复核前禁止导出（403）、复核后可导出；analyst 不能复核；未认证 401。
9. 导出 CSV 含斑块明细与逐格平均差/样本数/斑块编号。

## 性能实测（硬边界）
- 满载 14 张 × 96×96 格、2^14=16384 种符号组合：实测约 8.6 秒完成，低于 60 秒上限。
- 演示种子（3 研究 × 6 张 12×12 方阵，混合 0/90/180/270、含约 4% 缺测）：正向 20 格、负向 4 格斑块均在旋转对齐后正确检出。

## 复跑方式
```bash
python3 -m venv --without-pip .venv && . .venv/bin/activate
python get-pip.py            # 环境无 ensurepip 时
pip install -r backend/requirements.txt
PYTHONPATH=backend python -I /path/to/test_algorithm.py
PYTHONPATH=backend python -I /path/to/test_integration.py
PYTHONPATH=backend python -I /path/to/test_http.py
```
后端全部模块 `python -m py_compile` 通过，前端全部 ES module `node --check` 通过。
