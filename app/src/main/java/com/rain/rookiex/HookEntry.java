package com.rain.rookiex;

import android.app.Application;
import android.content.Context;
import android.os.Environment;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * Rain / RookieX —— 菜鸟 APK 节点提取模块
 *
 * 钩三类入口，任一命中即 dump：
 *   1. XRayProxyClient.setCurrentProxyUri(String)   —— 内核启动前拿到的那条节点链接
 *   2. NodeConfig.getProxyList() / saveProxyList()  —— MMKV 里的完整节点 JSON
 *   3. Nodes.getNode()                              —— 服务器下发后反序列化的原始对象
 *
 * 输出：/sdcard/Android/data/<pkg>/files/rookiex/
 *   不写外部公共目录，避免权限与清理残留。
 *   模块自身不发起任何网络请求。
 */
public class HookEntry implements IXposedHookLoadPackage {

    private static final String TAG = "RookieX";
    private static final String TARGET_PKG = "com.rookie.v.func.pro";

    private static Writer logWriter;
    private static Context appCtx;

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!TARGET_PKG.equals(lpparam.packageName)) return;

        XposedBridge.log(TAG + ": 命中目标包 " + lpparam.packageName);

        XposedHelpers.findAndHookMethod(
                Application.class, "onCreate", new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        appCtx = (Application) param.thisObject;
                        openLog();
                        log("=== 进程启动，模块就位 ===");
                        dumpMmkvDir();
                    }
                });

        hookCurrentProxyUri(lpparam);
        hookNodeConfig(lpparam);
        hookNodes(lpparam);
        hookVpnModeSettle(lpparam);
    }

    // ---------------------------------------------------------------- 钩点 1
    private void hookCurrentProxyUri(XC_LoadPackage.LoadPackageParam lp) {
        try {
            XposedHelpers.findAndHookMethod(
                    "com.rookie.v.libs.XRayProxyClient",
                    lp.classLoader,
                    "setCurrentProxyUri",
                    String.class,
                    new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) {
                            String uri = (String) param.args[0];
                            log("[URI] setCurrentProxyUri => " + uri);
                            writeNodeUri(uri);
                        }
                    });
            log("钩点 1 挂上: XRayProxyClient.setCurrentProxyUri");
        } catch (Throwable t) {
            log("钩点 1 失败: " + t);
        }
    }

    // ---------------------------------------------------------------- 钩点 2
    private void hookNodeConfig(XC_LoadPackage.LoadPackageParam lp) {
        String cls = "com.rookie.v.func.config.NodeConfig";
        try {
            XposedHelpers.findAndHookMethod(cls, lp.classLoader, "getProxyList",
                    new XC_MethodHook() {
                        @Override
                        protected void afterHookedMethod(MethodHookParam param) {
                            Object r = param.getResult();
                            if (r instanceof List) {
                                StringBuilder sb = new StringBuilder();
                                for (Object o : (List<?>) r) {
                                    sb.append(safeToString(o)).append('\n');
                                }
                                log("[LIST] getProxyList size=" + ((List<?>) r).size());
                                log(sb.toString());
                                appendFile("proxies.list.txt", sb.toString());
                            }
                        }
                    });
            log("钩点 2a 挂上: NodeConfig.getProxyList");
        } catch (Throwable t) {
            log("钩点 2a 失败: " + t);
        }

        try {
            XposedHelpers.findAndHookMethod(cls, lp.classLoader, "saveProxyList", List.class,
                    new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) {
                            Object r = param.args[0];
                            if (r instanceof List) {
                                StringBuilder sb = new StringBuilder();
                                for (Object o : (List<?>) r) {
                                    sb.append(safeToString(o)).append('\n');
                                }
                                log("[SAVE] saveProxyList size=" + ((List<?>) r).size());
                                appendFile("proxies.save.txt", sb.toString());
                            }
                        }
                    });
            log("钩点 2b 挂上: NodeConfig.saveProxyList");
        } catch (Throwable t) {
            log("钩点 2b 失败: " + t);
        }

        // MMKV 里那两份裸字符串也顺手捞
        for (String m : new String[]{"getProxiesList", "getCurrentProxy"}) {
            try {
                XposedHelpers.findAndHookMethod(cls, lp.classLoader, m, new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        log("[MMKV] " + m + " => " + param.getResult());
                        appendFile("mmkv_raw.txt", m + " => " + param.getResult() + "\n");
                    }
                });
                log("钩点 2c 挂上: NodeConfig." + m);
            } catch (Throwable t) {
                log("钩点 2c 失败 " + m + ": " + t);
            }
        }
    }

    // ---------------------------------------------------------------- 钩点 3
    private void hookNodes(XC_LoadPackage.LoadPackageParam lp) {
        try {
            XposedHelpers.findAndHookMethod(
                    "com.rookie.v.data.api.Nodes",
                    lp.classLoader,
                    "getNode",
                    new XC_MethodHook() {
                        @Override
                        protected void afterHookedMethod(MethodHookParam param) {
                            Object r = param.getResult();
                            if (r instanceof List) {
                                StringBuilder sb = new StringBuilder();
                                for (Object o : (List<?>) r) {
                                    sb.append(safeToString(o)).append('\n');
                                }
                                log("[NODES] getNode size=" + ((List<?>) r).size());
                                appendFile("nodes.txt", sb.toString());
                            }
                        }
                    });
            log("钩点 3 挂上: Nodes.getNode");
        } catch (Throwable t) {
            log("钩点 3 失败: " + t);
        }
    }

    // ---------------------------------------------------------------- 回调兜底
    private void hookVpnModeSettle(XC_LoadPackage.LoadPackageParam lp) {
        // XRayProxyClient 里连接状态回调带诊断串，偶尔带真实地址
        try {
            XposedHelpers.findAndHookMethod(
                    "com.rookie.v.libs.XRayProxyClient$initialize$1",
                    lp.classLoader,
                    "onPingResponse",
                    int.class,
                    String.class,
                    new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) {
                            log("[PING] code=" + param.args[0] + " msg=" + param.args[1]);
                        }
                    });
            log("钩点 4 挂上: onPingResponse");
        } catch (Throwable t) {
            log("钩点 4 失败: " + t);
        }
    }

    // ---------------------------------------------------------------- 输出
    private static synchronized void openLog() {
        if (logWriter != null || appCtx == null) return;
        try {
            File dir = outDir();
            File f = new File(dir, "rookiex.log");
            logWriter = new OutputStreamWriter(new FileOutputStream(f, true), "UTF-8");
        } catch (Throwable ignore) {}
    }

    private static File outDir() {
        // 应用私有外部目录，不需要存储权限，卸载时一并清掉
        File base = appCtx.getExternalFilesDir(null);
        if (base == null) base = new File(appCtx.getFilesDir(), "ext");
        File d = new File(base, "rookiex");
        if (!d.exists()) d.mkdirs();
        return d;
    }

    private static void log(String s) {
        if (s == null) return;
        XposedBridge.log(TAG + ": " + s);
        String line = ts() + " " + s + "\n";
        openLog();
        if (logWriter != null) {
            try {
                logWriter.write(line);
                logWriter.flush();
            } catch (IOException ignore) {}
        }
    }

    private static synchronized void appendFile(String name, String content) {
        if (content == null || appCtx == null) return;
        try {
            File f = new File(outDir(), name);
            Writer w = new OutputStreamWriter(new FileOutputStream(f, true), "UTF-8");
            w.write(content);
            if (!content.endsWith("\n")) w.write("\n");
            w.close();
        } catch (Throwable ignore) {}
    }

    private static void writeNodeUri(String uri) {
        if (uri == null) return;
        appendFile("node_uris.txt", uri);
    }

    private static String safeToString(Object o) {
        if (o == null) return "null";
        try {
            return o.toString();
        } catch (Throwable t) {
            return "<toString 抛出 " + t + ">";
        }
    }

    private static String ts() {
        return new SimpleDateFormat("MM-dd HH:mm:ss", Locale.US).format(new Date());
    }

    // ---------------------------------------------------------------- 文件兜底
    private static void dumpMmkvDir() {
        // 只列清单，不读内容 —— 内容靠上面的钩子拿
        new Thread(() -> {
            try {
                File d = new File(appCtx.getFilesDir(), "mmkv");
                if (!d.exists()) {
                    log("mmkv 目录不存在: " + d);
                    return;
                }
                File[] fs = d.listFiles();
                log("mmkv 目录文件数: " + (fs == null ? 0 : fs.length));
                if (fs != null) {
                    for (File f : fs) log("  mmkv: " + f.getName() + " size=" + f.length());
                }
            } catch (Throwable t) {
                log("dumpMmkvDir 失败: " + t);
            }
        }, "rookiex-mmkv").start();
    }
}
