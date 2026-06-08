const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:3000';

async function post(path, body) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

function namesOf(result) {
  return result.proposals?.[0]?.ordered_poi_names || result.planning_response?.proposals?.[0]?.ordered_poi_names || [];
}

function assertNoName(result, forbidden, label) {
  const names = namesOf(result);
  if (names.some((name) => String(name).includes(forbidden))) {
    throw new Error(`${label}: excluded "${forbidden}" leaked into route: ${names.join(' -> ')}`);
  }
}

async function main() {
  const seed = await post('/api/v1/travel/parse-and-plan', {
    goal: '前门附近玩4小时，中午吃饭，想吃好但不想排队，预算200以内，少走路',
  });
  let previous = seed.planning_response.request_snapshot;
  let selected = seed.planning_response.proposals[0];

  const foodReplan = await post('/api/v1/travel/replan', {
    previous_request: previous,
    selected_proposal: selected,
    adjustment_text: '去掉方砖厂69号炸酱面，换一个更适合午餐的地方，仍然控制在4小时以内',
  });
  assertNoName(foodReplan, '方砖厂69号炸酱面', 'food replacement');
  previous = foodReplan.request_snapshot;
  selected = foodReplan.proposals[0];

  for (const text of ['不去正阳门箭楼', '别去正阳门箭楼', '不要去正阳门箭楼', '排除正阳门箭楼']) {
    const result = await post('/api/v1/travel/replan', {
      previous_request: previous,
      selected_proposal: selected,
      adjustment_text: text,
    });
    assertNoName(result, '正阳门箭楼', text);
    const mustIds = new Set(result.request_snapshot?.must_include_poi_ids || []);
    const excludedIds = new Set(result.request_snapshot?.exclude_poi_ids || []);
    for (const id of excludedIds) {
      if (mustIds.has(id)) {
        throw new Error(`${text}: excluded POI id still present in must_include_poi_ids: ${id}`);
      }
    }
  }

  console.log('[travel-replan-exclusions] passed');
}

main().catch((error) => {
  console.error('[travel-replan-exclusions] failed:', error);
  process.exit(1);
});
