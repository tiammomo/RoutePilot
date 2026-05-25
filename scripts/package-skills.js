const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const root = process.cwd();
const registryPath = path.join(root, '.claude', 'skills.registry.json');
const skillsDir = path.join(root, '.claude', 'skills');
const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
const packageDir = path.join(root, registry.policy.packageDir || '.claude/skill-packages');
const lockPath = path.join(root, '.claude', 'skills.lock.json');

function fail(message) {
  console.error(`[package-skills] ${message}`);
  process.exit(1);
}

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

function readLockFile() {
  try {
    return JSON.parse(fs.readFileSync(lockPath, 'utf8'));
  } catch {
    return {
      schemaVersion: 1,
      packageFormat: registry.policy.packageFormat || 'tgz',
      skills: {},
    };
  }
}

function writeLockFile(lock) {
  fs.writeFileSync(lockPath, `${JSON.stringify(lock, null, 2)}\n`, 'utf8');
}

function getSkillVersion(skillId) {
  const coreSkill = registry.coreSkills.find((skill) => skill.id === skillId);
  return coreSkill?.version || null;
}

function packageSkill(skillId) {
  const sourceDir = path.join(skillsDir, skillId);
  const skillFile = path.join(sourceDir, 'SKILL.md');
  if (!fs.existsSync(skillFile)) {
    fail(`SKILL.md not found for ${skillId}`);
  }

  const sourceHash = hashSkillSource(skillId);
  fs.mkdirSync(packageDir, { recursive: true });
  const outputPath = path.join(packageDir, `${skillId}.tgz`);
  const result = spawnSync(
    'tar',
    ['-czf', outputPath, '-C', skillsDir, skillId],
    { cwd: root, stdio: 'inherit' }
  );
  if (result.status !== 0) {
    fail(`tar failed for ${skillId}`);
  }
  const packageSha256 = sha256(fs.readFileSync(outputPath));
  return {
    outputPath,
    packageSha256,
    ...sourceHash,
  };
}

const rawArgs = process.argv.slice(2);
const includeLegacy = rawArgs.includes('--include-legacy');
const requested = rawArgs.filter((arg) => arg !== '--include-legacy');
const coreIds = registry.coreSkills.map((skill) => skill.id);
const aliasIds = Object.keys(registry.legacyAliases || {});
const skillIds = requested.length ? requested : [...coreIds, ...(includeLegacy ? aliasIds : [])];
const lock = readLockFile();
lock.schemaVersion = 1;
lock.packageFormat = registry.policy.packageFormat || 'tgz';
lock.skills = lock.skills && typeof lock.skills === 'object' ? lock.skills : {};

for (const skillId of skillIds) {
  const output = packageSkill(skillId);
  lock.skills[skillId] = {
    version: getSkillVersion(skillId),
    packagePath: path.relative(root, output.outputPath).replaceAll(path.sep, '/'),
    sourceSha256: output.sourceSha256,
    packageSha256: output.packageSha256,
    fileCount: output.fileCount,
  };
  console.log(`[package-skills] ${skillId} -> ${path.relative(root, output.outputPath)}`);
}

writeLockFile(lock);
console.log(`[package-skills] lock -> ${path.relative(root, lockPath)}`);
