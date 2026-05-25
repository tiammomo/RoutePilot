const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const root = process.cwd();
const registryPath = path.join(root, '.claude', 'skills.registry.json');
const skillsDir = path.join(root, '.claude', 'skills');
const changelogPath = path.join(root, '.claude', 'skills.changelog.json');
const lockPath = path.join(root, '.claude', 'skills.lock.json');

function fail(message) {
  console.error(`[skills-registry] ${message}`);
  process.exit(1);
}

const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
const packageDir = path.join(root, registry.policy.packageDir || '.claude/skill-packages');
const checkLegacyPackages = process.argv.includes('--include-legacy');
const checkLock = process.argv.includes('--check-lock');

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function listFiles(dir) {
  if (!fs.existsSync(dir)) {
    return [];
  }

  const entries = fs.readdirSync(dir, { withFileTypes: true });
  return entries.flatMap((entry) => {
    if (entry.name === '.DS_Store') {
      return [];
    }

    const absolutePath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      return listFiles(absolutePath);
    }
    if (!entry.isFile()) {
      return [];
    }
    return [absolutePath];
  }).sort();
}

function hashSkillSource(skillId) {
  const sourceDir = path.join(skillsDir, skillId);
  const files = listFiles(sourceDir);
  const hash = crypto.createHash('sha256');
  for (const filePath of files) {
    const relativePath = path.relative(sourceDir, filePath).replaceAll(path.sep, '/');
    hash.update(relativePath);
    hash.update('\0');
    hash.update(fs.readFileSync(filePath));
    hash.update('\0');
  }
  return {
    fileCount: files.length,
    sourceSha256: hash.digest('hex'),
  };
}

function parseJsonFile(filePath, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return fallback;
  }
}

function isSemver(version) {
  return /^\d+\.\d+\.\d+$/.test(version);
}

const changelog = parseJsonFile(changelogPath, { schemaVersion: 1, skills: {} });
const lock = parseJsonFile(lockPath, { schemaVersion: 1, skills: {} });
if (registry.schemaVersion !== 1) {
  fail('schemaVersion must be 1');
}

if (!Array.isArray(registry.coreSkills) || registry.coreSkills.length === 0) {
  fail('coreSkills must be a non-empty array');
}

const ids = new Set();
for (const skill of registry.coreSkills) {
  if (!skill.id || !skill.name || !skill.version || !skill.status || !skill.boundary) {
    fail(`core skill is missing required fields: ${JSON.stringify(skill)}`);
  }
  if (!isSemver(skill.version)) {
    fail(`core skill ${skill.id} version must be semver x.y.z, got: ${skill.version}`);
  }
  if (ids.has(skill.id)) {
    fail(`duplicate core skill id: ${skill.id}`);
  }
  ids.add(skill.id);

  const skillFile = path.join(skillsDir, skill.id, 'SKILL.md');
  if (!fs.existsSync(skillFile)) {
    fail(`core skill SKILL.md not found: ${skill.id}`);
  }

  const packagePath = path.join(packageDir, `${skill.id}.tgz`);
  if (fs.existsSync(packageDir) && !fs.existsSync(packagePath)) {
    fail(`core skill package not found: ${path.relative(root, packagePath)}`);
  }

  const skillChangelog = changelog.skills?.[skill.id];
  if (!skillChangelog || !Array.isArray(skillChangelog.releases)) {
    fail(`missing changelog releases for core skill: ${skill.id}`);
  }
  const currentRelease = skillChangelog.releases.find((release) => release.version === skill.version);
  if (!currentRelease) {
    fail(`missing changelog release ${skill.version} for core skill: ${skill.id}`);
  }
  if (!currentRelease.date || !currentRelease.summary || !Array.isArray(currentRelease.changes) || currentRelease.changes.length === 0) {
    fail(`invalid changelog release ${skill.id}@${skill.version}; date, summary and changes are required`);
  }

  const lockEntry = lock.skills?.[skill.id];
  if (!lockEntry) {
    fail(`missing lock entry for core skill: ${skill.id}`);
  }
  if (lockEntry.version !== skill.version) {
    fail(`lock version mismatch for ${skill.id}: registry=${skill.version}, lock=${lockEntry.version}`);
  }
  if (checkLock) {
    const sourceHash = hashSkillSource(skill.id);
    if (lockEntry.sourceSha256 !== sourceHash.sourceSha256) {
      fail(`source hash mismatch for ${skill.id}; run npm run package:skills -- ${skill.id}`);
    }
    if (lockEntry.fileCount !== sourceHash.fileCount) {
      fail(`source file count mismatch for ${skill.id}; run npm run package:skills -- ${skill.id}`);
    }
    if (!fs.existsSync(packagePath)) {
      fail(`package missing for ${skill.id}: ${path.relative(root, packagePath)}`);
    }
    const packageSha256 = sha256(fs.readFileSync(packagePath));
    if (lockEntry.packageSha256 !== packageSha256) {
      fail(`package hash mismatch for ${skill.id}; run npm run package:skills -- ${skill.id}`);
    }
  }
}

const aliases = registry.legacyAliases || {};
for (const [alias, target] of Object.entries(aliases)) {
  if (!ids.has(target)) {
    fail(`legacy alias ${alias} points to unknown core skill ${target}`);
  }

  const aliasSkillFile = path.join(skillsDir, alias, 'SKILL.md');
  if (!fs.existsSync(aliasSkillFile)) {
    fail(`legacy alias SKILL.md not found: ${alias}`);
  }

  const packagePath = path.join(packageDir, `${alias}.tgz`);
  if (checkLegacyPackages && fs.existsSync(packageDir) && !fs.existsSync(packagePath)) {
    fail(`legacy alias package not found: ${path.relative(root, packagePath)}`);
  }
}

if (registry.coreSkills.length > registry.policy.targetCoreSkillCount) {
  fail(
    `core skill count ${registry.coreSkills.length} exceeds target ${registry.policy.targetCoreSkillCount}`
  );
}

console.log(
  `[skills-registry] ok: ${registry.coreSkills.length} core skills, ${Object.keys(aliases).length} legacy aliases${checkLegacyPackages ? ', legacy packages checked' : ''}`
);
