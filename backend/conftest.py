# 说明：backend/__init__.py（PyInstaller 打包需要）会让 pytest 在确定测试模块
# basedir 时向上越过 backend 根目录。在 /app 布局的容器里运行时，若挂载点
# 恰好叫 /app，根目录下的 app/ 子目录会被误解析为 `app` 包。测试时应将
# backend 挂载到非 /app 路径（如 /srv），或保证父目录无同名目录遮蔽。
