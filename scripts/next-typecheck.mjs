import { spawnSync } from "node:child_process";
import { rmSync } from "node:fs";
import { join } from "node:path";

rmSync(join(process.cwd(), ".next", "types"), { recursive: true, force: true });

for (const [command, args] of [
  ["next", ["typegen"]],
  ["tsc", ["--noEmit", "--incremental", "false"]],
]) {
  const result = spawnSync(command, args, { stdio: "inherit", shell: process.platform === "win32" });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}
