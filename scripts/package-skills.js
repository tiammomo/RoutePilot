const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const root = process.cwd();
const registryPath = path.join(root, '.claude', 'skills.registry.json');
const skillsDir = path.join(root, '.claude', 'skills');
const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
const packageDir = path.join(root, registry.policy.packageDir || '.claude/skill-packages');

function fail(message) {
  console.error(`[package-skills] ${message}`);
  process.exit(1);
}

function packageSkill(skillId) {
  const sourceDir = path.join(skillsDir, skillId);
  const skillFile = path.join(sourceDir, 'SKILL.md');
  if (!fs.existsSync(skillFile)) {
    fail(`SKILL.md not found for ${skillId}`);
  }

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
  return outputPath;
}

const rawArgs = process.argv.slice(2);
const includeLegacy = rawArgs.includes('--include-legacy');
const requested = rawArgs.filter((arg) => arg !== '--include-legacy');
const coreIds = registry.coreSkills.map((skill) => skill.id);
const aliasIds = Object.keys(registry.legacyAliases || {});
const skillIds = requested.length ? requested : [...coreIds, ...(includeLegacy ? aliasIds : [])];

for (const skillId of skillIds) {
  const output = packageSkill(skillId);
  console.log(`[package-skills] ${skillId} -> ${path.relative(root, output)}`);
}
