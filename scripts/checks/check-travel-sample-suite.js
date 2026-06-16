const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:33003';

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

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function firstProposal(result) {
  return result.planning_response?.proposals?.[0] || result.proposals?.[0];
}

function names(result) {
  return firstProposal(result)?.ordered_poi_names || [];
}

function pois(result) {
  return firstProposal(result)?.pois || [];
}

function allPois(result) {
  const proposalPois = result.planning_response?.proposals?.flatMap((proposal) => proposal.pois || []) || [];
  const dailyPois = result.planning_response?.daily_itinerary?.flatMap((day) => day.proposal?.pois || []) || [];
  return [...pois(result), ...proposalPois, ...dailyPois];
}

function allNames(result) {
  return allPois(result).map((poi) => String(poi.name || '')).filter(Boolean);
}

function assertNoWeakUserVisiblePoi(label, result) {
  const weakPattern = /\d+号(茶馆|小食铺|酒馆|餐馆|餐厅|饭馆|书吧|文创|商店|小店)|酒店|宾馆|客栈|漫心府|花间堂|住宿|肯德基|麦当劳|兰州牛肉拉面|臭豆腐|SLOWBOAT|悠航|精酿|酒吧|啤酒|市民文化中心|社区|居民|街道办|金鱼展|观景平台|售票|卫生间|游客中心|观众服务中心|讲解服务处|服务中心/;
  const largeScenicNames = ['故宫博物院', '天坛公园', '北海公园', '景山公园', '颐和园', '圆明园'];
  const bad = allNames(result).filter((name) => (
    weakPattern.test(name)
    || largeScenicNames.some((scenicName) => name.startsWith(scenicName) && !['', '遗址公园'].includes(name.slice(scenicName.length)))
  ));
  assert(bad.length === 0, `${label}: should not expose weak/synthetic POIs: ${bad.join(' -> ')}`);
}

function hasLunch(result) {
  return allPois(result).some((poi) => poi.meal_slot === 'lunch' || poi.poi_type === 'food');
}

function hasCoffeeMeal(result) {
  return pois(result).some((poi) => poi.meal_type === 'coffee' || poi.is_coffee_stop);
}

function hasRisk(result, pattern) {
  return (firstProposal(result)?.risks || []).some((risk) => pattern.test(String(risk)));
}

function assertNoSoftCultureMismatch(label, result) {
  const bad = names(result).filter((name) => /开心麻花|剧场|剧院|影院|电影|教堂|主教座堂|天主教|基督教|步行街|购物中心|商场/.test(String(name)));
  assert(bad.length === 0, `${label}: culture-first route should avoid soft mismatches: ${bad.join(' -> ')}`);
}

function validateCommon(label, result, options = {}) {
  const proposal = firstProposal(result);
  assert(proposal, `${label}: missing first proposal`);
  assert((proposal.ordered_poi_names || []).length >= 3, `${label}: should keep at least 3 POIs`);
  assert(result.generation_metrics?.within_10s ?? result.planning_response?.generation_metrics?.within_10s, `${label}: generation should be within 10s`);
  assertNoWeakUserVisiblePoi(label, result);
  if (options.food) assert(hasLunch(result), `${label}: expected food/lunch stop`);
  if (options.noFood) assert(!hasLunch(result), `${label}: expected no food stop`);
  if (options.maxBudget !== undefined) {
    assert(proposal.total_budget_estimate <= options.maxBudget || hasRisk(result, /budget|预算/i), `${label}: budget should be within cap or risk-visible`);
  }
  if (options.maxDuration !== undefined) {
    assert(proposal.total_route_duration_min <= options.maxDuration || hasRisk(result, /duration|时长|时间/i), `${label}: duration should be within cap or risk-visible`);
  }
}

async function main() {
  const cases = [
    ['qianmen', '前门附近玩4小时，中午吃饭，想吃好但不想排队，预算200以内，少走路', { food: true, maxBudget: 200, maxDuration: 240 }],
    ['gugong', '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭', { noFood: true, maxBudget: 100, maxDuration: 240 }],
    ['oneday', '北京1天游，想看经典文化景点，中午安排午餐，预算300以内，少走路', { food: true, maxBudget: 300, maxDuration: 480 }],
    ['twoday', '北京2天旅游，第一天经典文化景点，第二天吃逛结合，预算500以内，少走路', { maxBudget: 500 }],
    ['threeday', '北京3天旅游，想看经典文化景点，每天安排吃饭，预算600以内，不想排队', { maxBudget: 600 }],
    ['shichahai', '什刹海附近半日游，想喝咖啡，轻松一点，预算150以内', { food: true, maxBudget: 150, maxDuration: 240 }],
    ['wangfujing', '王府井附近晚上玩3小时，安排吃饭和一个娱乐点，不想排队', { food: true, maxDuration: 180 }],
    ['senior', '带老人去北海附近玩4小时，少走路，别太累，中午安排吃饭', { food: true, maxDuration: 240 }],
    ['couple', '情侣在故宫附近玩4小时，想浪漫一点，中午吃饭，预算300以内，少走路', { food: true, maxBudget: 300, maxDuration: 240 }],
    ['kids', '带小孩去北京玩4小时，亲子友好，中午吃饭，预算300以内，少走路', { food: true, maxBudget: 300, maxDuration: 240 }],
  ];

  const results = {};
  for (const [label, goal, expectation] of cases) {
    const result = await post('/api/v1/travel/parse-and-plan', { goal });
    validateCommon(label, result, expectation);
    results[label] = result;
    console.log(`[sample:${label}] ${names(result).join(' -> ')}`);
  }

  assertNoSoftCultureMismatch('gugong-culture-short', results.gugong);
  assert(/故宫博物院/.test(names(results.gugong).join(' -> ')), `gugong-culture-short: should keep Forbidden City as culture anchor: ${names(results.gugong).join(' -> ')}`);

  const beijing3 = await post('/api/v1/travel/parse-and-plan', {
    goal: '三天玩北京，想去颐和园，吃好吃的，逛故宫，预算3000',
  });
  validateCommon('beijing3-must-include', beijing3, { food: true, maxBudget: 3000 });
  const beijing3Names = allNames(beijing3).join(' -> ');
  assert(/颐和园/.test(beijing3Names), `beijing3-must-include: should include Summer Palace: ${beijing3Names}`);
  assert(/故宫博物院/.test(beijing3Names), `beijing3-must-include: should include Forbidden City: ${beijing3Names}`);
  assert(!/TRB|Forbidden City/.test(beijing3Names), `beijing3-must-include: should prefer Beijing-local food over TRB: ${beijing3Names}`);
  assert((beijing3.planning_response?.daily_itinerary || []).length === 3, 'beijing3-must-include: should produce 3 daily itinerary entries');
  console.log(`[sample:beijing3-must-include] ${beijing3.planning_response.daily_itinerary.map((day) => day.proposal.ordered_poi_names.join(' -> ')).join(' | ')}`);

  const hotelAnchor = await post('/api/v1/travel/parse-and-plan', {
    goal: '北京5天，住王府井，带父母，少走路，想吃烤鸭，预算不确定',
  });
  validateCommon('hotel-anchor', hotelAnchor, { food: true });
  assert((hotelAnchor.planning_response?.daily_itinerary || []).length === 5, 'hotel-anchor: should produce 5 daily itinerary entries');
  assert(hotelAnchor.planning_response?.proposals?.[0]?.accommodation, 'hotel-anchor: should expose accommodation anchor on proposal');
  assert(!names(hotelAnchor).some((name) => /王府井附近住宿|住宿|酒店|宾馆/.test(name)), `hotel-anchor: accommodation should not be a tourist stop: ${names(hotelAnchor).join(' -> ')}`);
  console.log(`[sample:hotel-anchor] ${names(hotelAnchor).join(' -> ')}`);

  const gugongBefore = names(results.gugong);
  const targeted = await post('/api/v1/travel/replan', {
    previous_request: results.gugong.planning_response.request_snapshot,
    selected_proposal: results.gugong.planning_response.proposals[0],
    adjustment_text: '把第二个点换成更少走路的室内点，其他地方不变',
  });
  const gugongAfter = names(targeted);
  assertNoWeakUserVisiblePoi('replan-targeted', targeted);
  assert(gugongAfter[0] === gugongBefore[0], 'targeted: first POI should stay');
  assert(gugongAfter[1] !== gugongBefore[1], 'targeted: second POI should change');
  assert(gugongAfter[2] === gugongBefore[2], 'targeted: third POI should stay');
  assert(!/Temple|剧场|酒店|市民文化中心/.test(gugongAfter[1]), `targeted: replacement should avoid weak tourist POIs: ${gugongAfter[1]}`);
  assert(/博物馆|美术馆|艺术中心|展览馆/.test(gugongAfter[1]), `targeted: replacement should be museum/gallery/art center: ${gugongAfter[1]}`);
  console.log(`[replan:targeted] ${gugongBefore.join(' -> ')} => ${gugongAfter.join(' -> ')}`);

  const lunchKeepBefore = names(results.qianmen);
  const lunchKeep = await post('/api/v1/travel/replan', {
    previous_request: results.qianmen.planning_response.request_snapshot,
    selected_proposal: results.qianmen.planning_response.proposals[0],
    adjustment_text: '把最后一个点换成室内景点，预算和午餐不变',
  });
  const lunchKeepAfter = names(lunchKeep);
  assertNoWeakUserVisiblePoi('replan-lunch-preserve', lunchKeep);
  const beforeFood = pois(results.qianmen).find((poi) => poi.poi_type === 'food')?.name;
  const afterFood = pois(lunchKeep).find((poi) => poi.poi_type === 'food')?.name;
  assert(beforeFood === afterFood, `lunch preserve: ${beforeFood} -> ${afterFood}`);
  assert(lunchKeepAfter[lunchKeepAfter.length - 1] !== lunchKeepBefore[lunchKeepBefore.length - 1], 'last stop should change');
  console.log(`[replan:lunch-preserve] ${lunchKeepBefore.join(' -> ')} => ${lunchKeepAfter.join(' -> ')}`);

  const meal = await post('/api/v1/travel/replan', {
    previous_request: results.wangfujing.planning_response.request_snapshot,
    selected_proposal: results.wangfujing.planning_response.proposals[0],
    adjustment_text: '去掉餐饮，换一个预算80以内的正餐，其他地方不变',
  });
  assert(hasLunch(meal), 'formal meal: should still include food');
  assertNoWeakUserVisiblePoi('replan-formal-meal', meal);
  assert(!hasCoffeeMeal(meal), `formal meal: should not choose coffee, got ${names(meal).join(' -> ')}`);
  console.log(`[replan:formal-meal] ${names(meal).join(' -> ')}`);

  const addBefore = names(results.gugong);
  const added = await post('/api/v1/travel/replan', {
    previous_request: results.gugong.planning_response.request_snapshot,
    selected_proposal: results.gugong.planning_response.proposals[0],
    adjustment_text: '再加一个顺路的室内美术馆，原来的点都保留',
  });
  const addAfter = names(added);
  assertNoWeakUserVisiblePoi('replan-add-stop', added);
  assert(addAfter.length === addBefore.length + 1, `add stop: expected one extra POI: ${addBefore.join(' -> ')} => ${addAfter.join(' -> ')}`);
  for (const original of addBefore) {
    assert(addAfter.includes(original), `add stop: original POI should stay: ${original}`);
  }
  const addedName = addAfter.find((name) => !addBefore.includes(name));
  assert(addedName && /博物馆|美术馆|艺术中心|展览馆/.test(addedName), `add stop: added POI should be indoor culture: ${addedName}`);
  console.log(`[replan:add-stop] ${addBefore.join(' -> ')} => ${addAfter.join(' -> ')}`);

  for (const adjustmentText of [
    '再加一个顺路的景点，原来的点都保留',
    '/再加一个顺路的景点，原来的点都保留',
  ]) {
    const genericAdded = await post('/api/v1/travel/replan', {
      previous_request: results.gugong.planning_response.request_snapshot,
      selected_proposal: results.gugong.planning_response.proposals[0],
      adjustment_text: adjustmentText,
    });
    const genericAfter = names(genericAdded);
    assertNoWeakUserVisiblePoi(`replan-generic-add-stop:${adjustmentText}`, genericAdded);
    assert(genericAfter.length === addBefore.length + 1, `generic add stop: expected one extra POI: ${addBefore.join(' -> ')} => ${genericAfter.join(' -> ')}`);
    for (const original of addBefore) {
      assert(genericAfter.includes(original), `generic add stop: original POI should stay: ${original}`);
    }
    const genericAddedName = genericAfter.find((name) => !addBefore.includes(name));
    assert(genericAddedName, `generic add stop: should add a visible new POI: ${genericAfter.join(' -> ')}`);
    assert(!/餐|饭|咖啡|小吃|甜品/.test(genericAddedName), `generic add stop: scenic stop should not become food: ${genericAddedName}`);
    console.log(`[replan:generic-add-stop] ${adjustmentText} => ${genericAfter.join(' -> ')}`);
  }

  const addLunchToCulture = await post('/api/v1/travel/replan', {
    previous_request: results.gugong.planning_response.request_snapshot,
    selected_proposal: results.gugong.planning_response.proposals[0],
    adjustment_text: '再加一个顺路的午餐地点，原来的点都保留',
  });
  const addLunchNames = names(addLunchToCulture);
  const addLunchPois = pois(addLunchToCulture);
  assertNoWeakUserVisiblePoi('replan-add-lunch-to-culture', addLunchToCulture);
  assert(addLunchToCulture.route_mode === 'mixed', 'add lunch to culture: route mode should switch to mixed');
  assert(addLunchPois.filter((poi) => poi.poi_type === 'food').length === 1, `add lunch to culture: should add exactly one food stop: ${addLunchNames.join(' -> ')}`);
  assert(addLunchPois.some((poi) => poi.meal_slot === 'lunch'), `add lunch to culture: should mark lunch slot: ${addLunchNames.join(' -> ')}`);
  for (const original of addBefore) {
    assert(addLunchNames.includes(original), `add lunch to culture: original POI should stay: ${original}`);
  }
  console.log(`[replan:add-lunch-to-culture] ${addBefore.join(' -> ')} => ${addLunchNames.join(' -> ')}`);

  console.log('[travel-sample-suite] passed');
}

main().catch((error) => {
  console.error('[travel-sample-suite] failed:', error);
  process.exit(1);
});
