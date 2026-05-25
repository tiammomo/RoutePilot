const fs = require('fs');
const path = require('path');

const root = process.cwd();
const registryPath = path.join(root, '.claude', 'skills.registry.json');
const skillsDir = path.join(root, '.claude', 'skills');

function fail(message) {
  console.error(`[skills-registry] ${message}`);
  process.exit(1);
}

const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
const packageDir = path.join(root, registry.policy.packageDir || '.claude/skill-packages');
const checkLegacyPackages = process.argv.includes('--include-legacy');
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
