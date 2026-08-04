#!/usr/bin/env node
/**
 * ORA safety gate — blocks clearly destructive shell commands unless the
 * user already confirmed in-band. Fail-open on parse errors so agents are
 * not wedged.
 */
const fs = require("fs");

const DENY = [
  /\b(rm\s+-rf\s+[\\/]|Remove-Item\s+-Recurse\s+-Force\s+[\\/])/i,
  /\bdrop\s+database\b/i,
  /\bdrop\s+collection\b/i,
  /\bmongo(?:sh)?\b.*\bdropDatabase\b/i,
  /\bgit\s+push\s+.*--force\b/i,
  /\bgit\s+push\s+-f\b/i,
  /\bgit\s+reset\s+--hard\b/i,
  /\bformat\s+[A-Z]:/i,
];

async function readStdin() {
  const chunks = [];
  for await (const c of process.stdin) chunks.push(c);
  return Buffer.concat(chunks).toString("utf8");
}

function decide(command) {
  const cmd = String(command || "");
  for (const re of DENY) {
    if (re.test(cmd)) {
      return {
        permission: "deny",
        user_message:
          "Comando bloccato dalla safety gate ORA (distruttivo o force-push). Chiedi conferma esplicita all'utente e riprova solo dopo il consenso.",
        agent_message:
          "Blocked destructive shell command. Obtain explicit user consent before retrying.",
      };
    }
  }
  return { permission: "allow" };
}

(async () => {
  try {
    const raw = await readStdin();
    let payload = {};
    try {
      payload = JSON.parse(raw || "{}");
    } catch {
      process.stdout.write(JSON.stringify({ permission: "allow" }));
      return;
    }
    const result = decide(payload.command || payload.cmd || "");
    process.stdout.write(JSON.stringify(result));
  } catch (err) {
    fs.appendFileSync(
      ".cursor/hooks/safety-gate.log",
      `[${new Date().toISOString()}] fail-open: ${err}\n`
    );
    process.stdout.write(JSON.stringify({ permission: "allow" }));
  }
})();
