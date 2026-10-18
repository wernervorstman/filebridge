// FileBridge Downloads – a small Mac app that shows how often FileBridge is downloaded.
// It asks the public GitHub API for the download counts of every release, keeps one snapshot per day in
// ~/Library/Application Support/FileBridge Downloads/history.json (shared with tools/download_counts.py)
// and shows them in dashboard.html. Built by tools/make_downloads_app.py.
import Cocoa
import WebKit

let api = URL(string: "https://api.github.com/repos/wernervorstman/filebridge/releases?per_page=100")!
let historyURL = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    .appendingPathComponent("FileBridge Downloads/history.json")

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var web: WKWebView!
    var pageReady = false

    func applicationDidFinishLaunching(_ n: Notification) {
        buildMenu()
        let cfg = WKWebViewConfiguration()
        cfg.userContentController.add(self, name: "refresh")
        web = WKWebView(frame: .zero, configuration: cfg)
        web.navigationDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1100, height: 860),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "FileBridge Downloads"
        window.contentView = web
        window.setFrameAutosaveName("FileBridgeDownloadsWindow")
        window.collectionBehavior = [.moveToActiveSpace]   // open on the Space you are on, not on an old one
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        if let page = Bundle.main.url(forResource: "dashboard", withExtension: "html") {
            web.loadFileURL(page, allowingReadAccessTo: page.deletingLastPathComponent())
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }

    // opened again (Dock, Launchpad, Finder) while it is already running: show the window here and refresh
    func applicationShouldHandleReopen(_ s: NSApplication, hasVisibleWindows: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil)
        if pageReady { update() }
        return true
    }

    // MARK: page
    func webView(_ w: WKWebView, didFinish nav: WKNavigation!) {
        pageReady = true
        show(loadHistory(), state: nil)   // what we have, right away
        update()                          // then today's numbers from GitHub
    }

    // links (GitHub, datalore.eu) open in the browser
    func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if a.navigationType == .linkActivated, let url = a.request.url, url.scheme?.hasPrefix("http") == true {
            NSWorkspace.shared.open(url); decisionHandler(.cancel); return
        }
        decisionHandler(.allow)
    }

    func userContentController(_ c: WKUserContentController, didReceive m: WKScriptMessage) {
        if m.name == "refresh" { update() }
    }

    func show(_ history: [[String: Any]], state: [String: Any]?) {
        guard pageReady,
              let h = try? JSONSerialization.data(withJSONObject: history),
              let s = try? JSONSerialization.data(withJSONObject: state ?? [:]),
              let hs = String(data: h, encoding: .utf8), let ss = String(data: s, encoding: .utf8) else { return }
        web.evaluateJavaScript("window.fbRender(\(hs), \(ss))", completionHandler: nil)
    }

    // MARK: data
    func loadHistory() -> [[String: Any]] {
        guard let d = try? Data(contentsOf: historyURL),
              let list = try? JSONSerialization.jsonObject(with: d) as? [[String: Any]] else { return [] }
        return list
    }

    func save(_ history: [[String: Any]]) {
        try? FileManager.default.createDirectory(at: historyURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if let d = try? JSONSerialization.data(withJSONObject: history, options: [.prettyPrinted, .sortedKeys]) {
            try? d.write(to: historyURL, options: .atomic)
        }
    }

    @objc func update() {
        var req = URLRequest(url: api, timeoutInterval: 20)
        req.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        req.setValue("FileBridge-Downloads-app", forHTTPHeaderField: "User-Agent")
        URLSession.shared.dataTask(with: req) { data, resp, err in
            DispatchQueue.main.async {
                guard err == nil, let data = data, (resp as? HTTPURLResponse)?.statusCode == 200,
                      let releases = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
                    self.show(self.loadHistory(), state: ["error": "GitHub is nu niet bereikbaar; je ziet de laatst bekende cijfers. Klik hier om het opnieuw te proberen."])
                    return
                }
                let snap = self.snapshot(releases)
                var history = self.loadHistory().filter { ($0["date"] as? String) != (snap["date"] as? String) }
                history.append(snap)
                history.sort { ($0["date"] as? String ?? "") < ($1["date"] as? String ?? "") }
                self.save(history)
                self.show(history, state: nil)
            }
        }.resume()
    }

    /// The same snapshot as tools/download_counts.py: installers only (.dmg, .exe, .tar.gz).
    func snapshot(_ releases: [[String: Any]]) -> [String: Any] {
        var rels: [[String: Any]] = []
        var total = ["mac": 0, "win": 0, "linux": 0]
        for rel in releases {
            var c = ["mac": 0, "win": 0, "linux": 0]
            for a in rel["assets"] as? [[String: Any]] ?? [] {
                let name = a["name"] as? String ?? "", n = a["download_count"] as? Int ?? 0
                if name.hasSuffix(".dmg") { c["mac"]! += n } else if name.hasSuffix(".exe") { c["win"]! += n }
                else if name.hasSuffix(".tar.gz") { c["linux"]! += n }
            }
            for k in c.keys { total[k]! += c[k]! }
            rels.append(["tag": rel["tag_name"] as? String ?? "", "published": rel["published_at"] as? String ?? "",
                         "mac": c["mac"]!, "win": c["win"]!, "linux": c["linux"]!])
        }
        let now = Date()
        let day = DateFormatter(); day.dateFormat = "yyyy-MM-dd"; day.timeZone = .current
        let iso = ISO8601DateFormatter(); iso.timeZone = .current; iso.formatOptions = [.withInternetDateTime]
        return ["date": day.string(from: now), "taken_at": iso.string(from: now),
                "total": total.values.reduce(0, +), "mac": total["mac"]!, "win": total["win"]!, "linux": total["linux"]!,
                "releases": rels]
    }

    // MARK: menu
    func buildMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem(); main.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(NSMenuItem(title: "Over FileBridge Downloads", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: ""))
        appMenu.addItem(.separator())
        appMenu.addItem(NSMenuItem(title: "Verberg FileBridge Downloads", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h"))
        appMenu.addItem(NSMenuItem(title: "Stop FileBridge Downloads", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        appItem.submenu = appMenu
        let viewItem = NSMenuItem(); main.addItem(viewItem)
        let view = NSMenu(title: "Weergave")
        let refresh = NSMenuItem(title: "Nu bijwerken", action: #selector(update), keyEquivalent: "r"); refresh.target = self
        view.addItem(refresh)
        viewItem.submenu = view
        let winItem = NSMenuItem(); main.addItem(winItem)
        let win = NSMenu(title: "Venster")
        win.addItem(NSMenuItem(title: "Minimaliseer", action: #selector(NSWindow.miniaturize(_:)), keyEquivalent: "m"))
        win.addItem(NSMenuItem(title: "Sluit venster", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w"))
        winItem.submenu = win
        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
