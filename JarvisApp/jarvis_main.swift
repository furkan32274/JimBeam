import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var pollTimer: Timer?

    func applicationDidFinishLaunching(_ n: Notification) {
        NSApp.setActivationPolicy(.regular)

        let wvc = WKWebViewConfiguration()
        wvc.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")
        webView = WKWebView(frame: .zero, configuration: wvc)
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 960, height: 720),
            styleMask: [.titled, .closable, .resizable, .miniaturizable, .fullSizeContentView],
            backing: .buffered, defer: false)
        window.title = "Jarvis"
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        window.backgroundColor = .black
        window.contentView = webView
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        startBackendIfNeeded()
        pollForServer()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }

    private func startBackendIfNeeded() {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        // Only start if not already running
        let check = Process()
        check.launchPath = "/bin/bash"
        check.arguments = ["-c", "pgrep -f chatbot_speech_to_speech.py"]
        let pipe = Pipe()
        check.standardOutput = pipe
        try? check.run()
        check.waitUntilExit()
        let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        if !out.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return }

        let home2 = home
        let task = Process()
        task.launchPath = "/bin/bash"
        task.arguments = ["-c",
            "cd \"\(home2)/JimBeam\" && source .venv311/bin/activate && nohup python chatbot_speech_to_speech.py > /tmp/jarvis.log 2>&1 &"]
        try? task.run()
    }

    private func pollForServer() {
        pollTimer = Timer.scheduledTimer(withTimeInterval: 1.5, repeats: true) { [weak self] t in
            guard let self = self else { t.invalidate(); return }
            guard let url = URL(string: "http://127.0.0.1:3000") else { return }
            URLSession.shared.dataTask(with: url) { _, resp, _ in
                if (resp as? HTTPURLResponse)?.statusCode == 200 {
                    DispatchQueue.main.async {
                        t.invalidate()
                        self.webView.load(URLRequest(url: URL(string: "http://localhost:3000")!))
                    }
                }
            }.resume()
        }
    }

    func webView(_ w: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let h = action.request.url?.host ?? ""
        decisionHandler(h == "localhost" || h == "127.0.0.1" ? .allow : .cancel)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
