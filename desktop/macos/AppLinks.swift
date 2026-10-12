// What the app builds from a task's link and from the lines that connect it to Claude Code and to Codex (docs/design/task-sessions.md).
// Foundation only, no window and nothing run: tests/static/test_app_links.py compiles this file alone and checks it.
import Foundation

enum AppLinks {
    // MARK: a task's link

    /// A task's id is what the board's address and the agents' link tool both carry: letters, digits, `-` and `_`, up to 100.
    static func isTaskID(_ text: String) -> Bool {
        (1...100).contains(text.count) && text.allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-" || $0 == "_") }
    }

    /// `verticals://goal/<id>` is a task: a session begun for it starts with this link, Terminal and Codex show it as one, and the
    /// agent that finds it in a conversation calls the link tool with `<id>`. Anything else is not a link of the app's.
    static func taskID(_ link: URL) -> String? {
        guard link.scheme?.lowercased() == "verticals", link.host?.lowercased() == "goal" else { return nil }
        guard link.path.hasPrefix("/") else { return nil }
        let id = String(link.path.dropFirst())  // Foundation leaves a trailing slash out of `path`, so a link that carries one opens too
        return isTaskID(id) ? id : nil
    }

    /// What the board reads after `#` to open the task: its own address grammar (web/src/lib/urlState.ts), at start and on `popstate`.
    static func fragment(task id: String) -> String { "goal/\(id)" }

    /// The board's address for the task, to load when the page is not there yet or is somewhere else.
    static func boardURL(task id: String, ui: URL) -> URL? {
        guard isTaskID(id), var parts = URLComponents(url: ui, resolvingAgainstBaseURL: false) else { return nil }
        parts.path = "/"
        parts.fragment = fragment(task: id)
        return parts.url
    }

    // MARK: the lines that connect an agent

    /// Claude Code's name for the connection, kept from "Connect Claude Code" so an earlier one is replaced, not doubled.
    static let claudeServer = "verticals-desktop"
    /// Codex's: not `verticals_desktop`, which the app's own Codex keeps for itself (desktop/chat/chat.py, `codex_args`).
    static let codexServer = "verticals"

    /// What `claude mcp add-json` is given: the address, and a command that prints the token from the owner-only file when Claude
    /// Code connects, so the token is never written into Claude Code's own settings.
    static func claudeAddArguments(mcpURL: String, headersFile: String) -> [String]? {
        let quoted = headersFile.replacingOccurrences(of: "'", with: "'\\''")
        let server = ["type": "http", "url": mcpURL, "headersHelper": "cat '\(quoted)'"]
        guard let data = try? JSONSerialization.data(withJSONObject: server, options: [.sortedKeys]),
              let json = String(data: data, encoding: .utf8) else { return nil }
        return ["mcp", "add-json", "--scope", "user", claudeServer, json]
    }

    static let claudeRemoveArguments = ["mcp", "remove", "--scope", "user", claudeServer]

    /// What `codex mcp add` is given: a command Codex starts, the relay of desktop/chat/mcp_proxy.py, told the address and the
    /// file that holds the token. The token itself is not on the line, in Codex's settings or in its environment.
    static func codexAddArguments(python: String, relay: String, mcpURL: String, headersFile: String) -> [String] {
        ["mcp", "add", codexServer, "--env", "VERTICALS_MCP_URL=\(mcpURL)", "--env", "VERTICALS_MCP_HEADERS=\(headersFile)",
         "--", python, relay]
    }

    static let codexRemoveArguments = ["mcp", "remove", codexServer]
}
