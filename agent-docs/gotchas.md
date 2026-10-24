# 踩坑记录（跨会话运维/开发注意事项）

本文件记录影响后续操作的坑，随问题出现持续追加。具体某个问题的完整修复方案见 [fixes/](fixes/)。

## 容器内跑 pytest 的两个坑

镜像布局下 `backend/__init__.py`（PyInstaller 打包需要）会让 pytest 把 basedir
推断到挂载根，导致模块解析错乱。表现为 `No module named 'app.transcriber'`。

1. **挂载点不能叫 `/app`**：`-v ...:/app` 时根目录下的 `app/` 包会解析到整个
   backend 目录。**必须挂到别的路径（如 /srv）**。
2. **镜像内 COPY 的旧代码会遮蔽挂载**：容器启动时先 `mv /app /app.bak 2>/dev/null`。

验证可用的命令模板：

```bash
docker run --rm -v /mnt/d/CodeRepos/BiliNote-pro/backend:/srv -w /srv \
  bilinote-pro-backend:latest bash -c \
  "mv /app /app.bak 2>/dev/null; pip install -q pytest; python -m pytest tests/ -q"
```

`backend/conftest.py` 里也留了同样的说明注释。

## tests/test_ydl_retry_opts.py 的 sys.modules 污染（预先存在，未修）

`tests/test_ydl_retry_opts.py` 的 `_load_base()` 用 `sys.modules.setdefault`
打桩且不还原，跨测试污染 `app.models.transcriber_model`，导致后续
`app/downloaders/base.py:8` 报
`ImportError: cannot import name 'TranscriptResult' from 'app.models.transcriber_model'`。

影响用例（全量套件会出现 4 个失败，属预先存在，与近期改动无关）：

- `tests/test_task_serial_executor.py::TestTaskSerialExecutor::test_executor_runs_tasks_one_by_one`
- `tests/test_ydl_retry_opts.py::RetryOptsValueTest` 的 3 个用例

如果单独跑这些用例（不与其他测试混跑），`_load_base()` 自己 setdefault 之前
没有污染源，能通过——判断改动是否引入新失败时用排除法：跑不含新文件的套件对照。
