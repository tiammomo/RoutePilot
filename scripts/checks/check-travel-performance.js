const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:3000';

async function request(path, options = {}) {
  const started = Date.now();
  const response = await fetch(`${baseUrl}${path}`, options);
  const elapsedMs = Date.now() - started;
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status} ${text}`);
  }
  return { elapsedMs, json: text ? JSON.parse(text) : null };
}

async function post(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function collectTravelProgress(projectId, action) {
  const events = [];
  const controller = new AbortController();
  const response = await fetch(`${baseUrl}/api/chat/${projectId}/stream`, { signal: controller.signal });
  if (!response.ok || !response.body) {
    throw new Error(`SSE connection failed: ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let connected = false;
  const pump = (async () => {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split('\n\n');
      buffer = chunks.pop() || '';
      for (const chunk of chunks) {
        const line = chunk.split('\n').find((item) => item.startsWith('data: '));
        if (!line) continue;
        const envelope = JSON.parse(line.slice(6));
        if (envelope.type === 'connected') connected = true;
        if (envelope.type === 'travel_progress') events.push(envelope.data);
      }
    }
  })();
  const started = Date.now();
  while (!connected && Date.now() - started < 5000) {
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  if (!connected) throw new Error('SSE connection timed out');

  await action();
  await new Promise((resolve) => setTimeout(resolve, 500));
  controller.abort();
  await pump.catch(() => undefined);
  return events;
}

async function main() {
  const warmup = await post('/api/v1/travel/warmup', {});
  assert(warmup.json?.data_loaded === true, 'warmup should load travel data');
  assert(warmup.json?.cache?.poi_index_ready === true, 'warmup should build POI index');
  assert(warmup.json?.cache?.review_index_ready === true, 'warmup should build review index');
  console.log(`[travel-performance] warmup ${warmup.elapsedMs}ms, data load ${warmup.json.data_load_elapsed_ms}ms`);

  const planTimes = [];
  const plannerTimes = [];
  let seed = null;
  for (let index = 0; index < 8; index += 1) {
    const result = await post('/api/v1/travel/parse-and-plan', {
      goal: '故宫附近玩4小时，想看文化景点，少走路，不吃饭，预算100以内',
    });
    planTimes.push(result.elapsedMs);
    plannerTimes.push(Number(result.json?.planning_response?.generation_metrics?.elapsed_ms ?? Infinity));
    seed = result.json;
  }
  const hotPlannerTimes = plannerTimes.slice(1);
  assert(hotPlannerTimes.every((time) => time < 500), `hot planner should be under 500ms: ${plannerTimes.join(', ')}`);

  const replanTimes = [];
  const replanPlannerTimes = [];
  for (let index = 0; index < 8; index += 1) {
    const result = await post('/api/v1/travel/replan', {
      previous_request: seed.planning_response.request_snapshot,
      selected_proposal: seed.planning_response.proposals[0],
      adjustment_text: '再加一个顺路的室内美术馆，原来的点都保留',
    });
    replanTimes.push(result.elapsedMs);
    replanPlannerTimes.push(Number(result.json?.generation_metrics?.elapsed_ms ?? Infinity));
  }
  assert(replanPlannerTimes.slice(1).every((time) => time < 500), `hot replan planner should be under 500ms: ${replanPlannerTimes.join(', ')}`);

  const projectId = process.env.TRAVELPILOT_PROGRESS_PROJECT_ID;
  if (projectId) {
    const progressEvents = await collectTravelProgress(projectId, () => post(`/api/chat/${projectId}/act`, {
      instruction: '故宫附近玩4小时，想看文化景点，少走路，不吃饭，预算100以内',
      mode: 'act',
      isInitialPrompt: true,
    }));
    assert(progressEvents.length >= 4, `expected at least 4 travel_progress events, got ${progressEvents.length}`);
    console.log(`[travel-performance] progress events: ${progressEvents.map((event) => event.stage).join(' -> ')}`);
  } else {
    console.log('[travel-performance] skipped SSE chat progress check; set TRAVELPILOT_PROGRESS_PROJECT_ID to enable it.');
  }

  console.log(`[travel-performance] plan ms: ${planTimes.join(', ')}`);
  console.log(`[travel-performance] planner internal ms: ${plannerTimes.join(', ')}`);
  console.log(`[travel-performance] replan ms: ${replanTimes.join(', ')}`);
  console.log(`[travel-performance] replan internal ms: ${replanPlannerTimes.join(', ')}`);
  console.log('[travel-performance] passed');
}

main().catch((error) => {
  console.error('[travel-performance] failed:', error);
  process.exit(1);
});
