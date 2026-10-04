const fs = require('fs');
const path = require('path');
const {
  withDangerousMod,
  withXcodeProject,
  IOSConfig,
} = require('@expo/config-plugins');

const SWIFT_FILE = 'OraSiriIntents.swift';

const swiftSource = `import AppIntents
import Foundation

@available(iOS 17.0, *)
struct AskOraIntent: AppIntent {
    static var title: LocalizedStringResource = "Chiedi a ORA"
    static var description = IntentDescription("Invia una richiesta a ORA usando la stessa conversazione dell'app.")

    @Parameter(title: "Richiesta", requestValueDialog: IntentDialog("Cosa vuoi chiedere a ORA?"))
    var request: String

    static var parameterSummary: some ParameterSummary {
        Summary("Chiedi a ORA: \\(.\\$request)")
    }

    static var supportedModes: IntentModes = [.foreground(.immediate)]

    func perform() async throws -> some IntentResult & OpensIntent {
        let trimmed = request.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            throw OraSiriError.emptyRequest
        }

        var components = URLComponents()
        components.scheme = "ora"
        components.host = "conversation"
        components.queryItems = [
            URLQueryItem(name: "text", value: trimmed),
            URLQueryItem(name: "origin", value: "siri"),
        ]
        guard let url = components.url else {
            throw OraSiriError.invalidURL
        }
        return .result(opensIntent: OpenURLIntent(url))
    }
}

@available(iOS 17.0, *)
enum OraSiriError: Error, CustomLocalizedStringResourceConvertible {
    case emptyRequest
    case invalidURL

    var localizedStringResource: LocalizedStringResource {
        switch self {
        case .emptyRequest:
            return "Dimmi cosa vuoi chiedere a ORA."
        case .invalidURL:
            return "Non riesco ad aprire ORA."
        }
    }
}

@available(iOS 17.0, *)
struct OraShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: AskOraIntent(),
            phrases: [
                "Dì a \\(.applicationName) \\(.$request)",
                "Chiedi a \\(.applicationName) \\(.$request)",
                "\\(.applicationName), \\(.$request)",
            ],
            shortTitle: "Chiedi a ORA",
            systemImageName: "sparkles"
        )
    }
}
`;

function withOraSiri(config) {
  config = withDangerousMod(config, [
    'ios',
    async (mod) => {
      const projectRoot = mod.modRequest.platformProjectRoot;
      const candidates = fs.readdirSync(projectRoot, { withFileTypes: true })
        .filter((entry) => entry.isDirectory() && !entry.name.endsWith('.xcodeproj') && entry.name !== 'Pods')
        .map((entry) => path.join(projectRoot, entry.name));

      const appDir = candidates.find((dir) =>
        fs.existsSync(path.join(dir, 'Info.plist'))
      );
      if (!appDir) {
        throw new Error('ORA Siri plugin: iOS app source directory not found');
      }
      fs.writeFileSync(path.join(appDir, SWIFT_FILE), swiftSource, 'utf8');
      return mod;
    },
  ]);

  config = withXcodeProject(config, (mod) => {
    const project = mod.modResults;
    const projectName = IOSConfig.XcodeUtils.getProjectName(mod.modRequest.projectRoot);
    const relativePath = `${projectName}/${SWIFT_FILE}`;

    const existing = project.hasFile?.(relativePath);
    if (!existing) {
      project.addSourceFile(relativePath, {}, project.getFirstTarget().uuid);
    }
    return mod;
  });

  return config;
}

module.exports = withOraSiri;
