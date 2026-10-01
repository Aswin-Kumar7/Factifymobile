// Which build is running, so an open tab can tell it has been left behind by a deploy
// (components/version-guard.tsx).
import { readFile } from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-dynamic";

export async function GET() {
  const id = await readFile(path.join(process.cwd(), ".next", "BUILD_ID"), "utf8").catch(() => "dev");
  return Response.json({ build: id.trim() }, { headers: { "cache-control": "no-store" } });
}
