# RookieX

菜鸟 APK（com.rookie.v.func.pro）节点提取 —— NPatch/Xposed 模块。

- 钩 `XRayProxyClient.setCurrentProxyUri` / `NodeConfig.getProxyList` / `Nodes.getNode`
- 结果落 `/sdcard/Android/data/com.rookie.v.func.pro/files/rookiex/`
- 模块自身不申请 INTERNET 权限，全程不发网络请求
- 本地用 `rookiex_parse.py` 转 Clash / 分享链接

## 构建

CI: push 到 `main` 自动出 APK（Actions → Artifacts）。

本地拉日志：

```bash
export GITHUBTOKEN=***
python3 scripts/ghbuild.py
```

日志落在 `./buildlogs/run_<id>/`。
