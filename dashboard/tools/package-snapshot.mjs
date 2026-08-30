import { createHash } from "node:crypto";
import { readFile, realpath, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { validateSnapshot } from "../src/snapshot.js";

const MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024;
const MAX_ARTIFACT_BYTES = 16 * 1024 * 1024;

function issue(code, artifactRef, message) {
  return { code, artifact_ref: artifactRef, message };
}

function isWithin(basePath, targetPath) {
  const relative = path.relative(basePath, targetPath);
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}

export function resolveLogicalArtifactPath(baseDirectory, artifactRef) {
  if (typeof artifactRef !== "string" || artifactRef.length === 0 || artifactRef.includes("\\")) {
    throw new Error("artifact_ref must be a non-empty logical path");
  }
  const basePath = path.resolve(baseDirectory);
  const targetPath = path.resolve(basePath, ...artifactRef.split("/"));
  if (!isWithin(basePath, targetPath)) throw new Error("artifact_ref escapes the artifact directory");
  return targetPath;
}

export async function verifyAndPackageSnapshot(snapshot, artifactDirectory) {
  const validation = validateSnapshot(snapshot);
  if (!validation.ok) {
    return { ok: false, stage: "snapshot_contract", issues: validation.issues };
  }

  const issues = [];
  let basePath;
  try {
    basePath = await realpath(path.resolve(artifactDirectory));
  } catch {
    return {
      ok: false,
      stage: "artifact_binding",
      issues: [issue("ARTIFACT_DIRECTORY_UNAVAILABLE", "", "source artifact directory is unavailable")]
    };
  }

  for (const artifact of snapshot.provenance.source_artifacts) {
    let candidatePath;
    try {
      candidatePath = resolveLogicalArtifactPath(basePath, artifact.artifact_ref);
      const actualPath = await realpath(candidatePath);
      if (!isWithin(basePath, actualPath)) throw new Error("resolved artifact escapes the artifact directory");
      const metadata = await stat(actualPath);
      if (!metadata.isFile()) throw new Error("resolved artifact is not a file");
      if (metadata.size > MAX_ARTIFACT_BYTES) {
        issues.push(issue("ARTIFACT_TOO_LARGE", artifact.artifact_ref, "source artifact exceeds the packaging size limit"));
        continue;
      }
      const bytes = await readFile(actualPath);
      const actualDigest = createHash("sha256").update(bytes).digest("hex");
      if (actualDigest !== artifact.sha256) {
        issues.push(issue("ARTIFACT_DIGEST_MISMATCH", artifact.artifact_ref, "source artifact digest does not match snapshot provenance"));
      }
    } catch {
      issues.push(issue("ARTIFACT_UNAVAILABLE", artifact.artifact_ref, "declared source artifact is unavailable inside the package directory"));
    }
  }

  if (issues.length > 0) return { ok: false, stage: "artifact_binding", issues };
  return {
    ok: true,
    stage: "packaged",
    verified_artifact_count: snapshot.provenance.source_artifacts.length,
    snapshot: structuredClone(snapshot)
  };
}

function usage() {
  return [
    "Usage:",
    "  node tools/package-snapshot.mjs --snapshot <approved.json> --artifacts-dir <dir> --output <packaged.json>",
    "",
    "The command validates the snapshot and every declared source-artifact digest.",
    "It does not create human decisions, redaction approval, or assessment results."
  ].join("\n");
}

function parseArguments(argv) {
  if (argv.includes("--help") || argv.includes("-h")) return { help: true };
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const flag = argv[index];
    const value = argv[index + 1];
    if (!value || !["--snapshot", "--artifacts-dir", "--output"].includes(flag)) {
      throw new Error("invalid command arguments");
    }
    result[flag.slice(2)] = value;
  }
  if (!result.snapshot || !result["artifacts-dir"] || !result.output) throw new Error("all command arguments are required");
  return result;
}

async function main() {
  let args;
  try {
    args = parseArguments(process.argv.slice(2));
  } catch (error) {
    console.error(error.message);
    console.error(usage());
    process.exitCode = 2;
    return;
  }
  if (args.help) {
    console.log(usage());
    return;
  }

  const snapshotPath = path.resolve(args.snapshot);
  const outputPath = path.resolve(args.output);
  if (snapshotPath === outputPath) {
    console.error("output must not overwrite the approved snapshot input");
    process.exitCode = 2;
    return;
  }

  let snapshot;
  try {
    const metadata = await stat(snapshotPath);
    if (!metadata.isFile() || metadata.size > MAX_SNAPSHOT_BYTES) throw new Error("snapshot input is not an allowed file");
    snapshot = JSON.parse(await readFile(snapshotPath, "utf8"));
  } catch {
    console.error("snapshot input could not be read as bounded JSON");
    process.exitCode = 1;
    return;
  }

  const packaged = await verifyAndPackageSnapshot(snapshot, args["artifacts-dir"]);
  if (!packaged.ok) {
    console.error(JSON.stringify({ stage: packaged.stage, issues: packaged.issues }, null, 2));
    process.exitCode = 1;
    return;
  }

  try {
    await writeFile(outputPath, `${JSON.stringify(packaged.snapshot, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
  } catch {
    console.error("output could not be created; existing files are not overwritten");
    process.exitCode = 1;
    return;
  }
  console.log(`snapshot package verified: ${packaged.verified_artifact_count} source artifact(s)`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}
