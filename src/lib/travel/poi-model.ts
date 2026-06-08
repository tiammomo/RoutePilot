import type { MealType, Poi, TravelPlanningRequest } from '@/lib/travel/planner-types';

export function hasAny(text: string, words: string[]): boolean {
  return words.some((word) => text.includes(word));
}

export function normalizePoiName(name?: string): string {
  return String(name || '')
    .replace(/[（(].*?[）)]/g, '')
    .replace(/[-—·\s]/g, '')
    .trim()
    .toLowerCase();
}

export function semanticKeysForPoiName(name?: string): string[] {
  const raw = String(name || '').trim();
  const normalized = normalizePoiName(raw);
  const keys = new Set<string>();
  if (raw) keys.add(raw);
  if (normalized) keys.add(normalized);
  const withoutSuffix = normalizePoiName(raw.replace(/[（(].*?[）)]/g, '').replace(/(公园|博物院|博物馆|景区|景点|店|门店|餐厅|饭店|咖啡|茶馆|小食铺|小吃)$/g, ''));
  if (withoutSuffix && withoutSuffix.length >= 2) keys.add(withoutSuffix);
  if (/长城|八达岭|慕田峪|居庸关|greatwall|badaling/i.test(normalized)) keys.add('长城');
  return Array.from(keys).filter(Boolean);
}

export function deriveMealSemantics(raw: Partial<Poi>) {
  const name = String(raw.name || '');
  const lowerName = name.toLowerCase();
  const metadata = [
    raw.category,
    raw.poi_type,
    raw.poi_subtype,
    raw.dining_style,
    ...(Array.isArray(raw.planning_tags) ? raw.planning_tags : []),
    ...(Array.isArray(raw.evidence_tags) ? raw.evidence_tags : []),
  ].map((value) => String(value || '').toLowerCase()).join(' ');

  const coffeeWords = ['咖啡', 'coffee', 'cafe', '星巴克', '瑞幸'];
  const mealWords = ['餐', '饭', '面', '涮肉', '烧麦', '烤鸭', '饺子', '炸酱', '炒肝', '火锅', '串', '食'];
  const snackWords = ['小吃', '麦当劳', '肯德基', '包子', '驴打滚', '糕', '饼'];
  const dessertWords = ['甜品', '下午茶', '茶饮', '奶茶'];
  const hotelWords = ['酒店', '宾馆', '漫心府', '亚朵', '主题酒店'];
  const scenicWords = ['公园', '博物院', '博物馆', '步行街', '景区', '景点', '寺', '殿', '塔', '后海', '前海', '鼓楼', '艺术中心', '探索中心'];

  coffeeWords.push('咖啡', '星巴克', '瑞幸');
  mealWords.push('餐', '饭', '面', '涮肉', '烤鸭', '烧鸭', '饺子', '炸酱', '炒肝', '火锅');
  snackWords.push('小吃', '麦当劳', '肯德基', '包子', '驴打滚', '茶馆', '夜市', '档口', '小食铺');
  dessertWords.push('甜品', '下午茶', '茶饮', '奶茶');
  hotelWords.push('酒店', '宾馆', '客栈', '漫心府', '住宿', '亚朵');
  scenicWords.push('公园', '博物馆', '博物院', '美术馆', '艺术中心', '文化中心', '展览馆', '步行街', '景区', '景点', '寺', '殿', '塔', '后海', '前海', '鼓楼', '售票处', '讲解服务处');

  const hasDiningMetadata = /(^|\s)(dining|food|restaurant|meal|lunch|dinner|snack|cafe|coffee)(\s|$)/.test(metadata);
  const coffee = hasAny(lowerName, coffeeWords);
  const mealName = hasAny(name, mealWords);
  const snackName = hasAny(name, snackWords);
  const dessertName = hasAny(name, dessertWords);
  const hotelName = hasAny(name, hotelWords);
  const scenicName = hasAny(name, scenicWords) || name === '什刹海';

  if (scenicName && !mealName && !snackName && !coffee && !dessertName) {
    return { meal_type: 'invalid' as MealType, is_lunch_suitable: false, is_coffee_stop: false, is_meal_stop: false };
  }
  if (!hasDiningMetadata && !mealName && !snackName && !coffee && !dessertName) {
    return { meal_type: 'non_food' as MealType, is_lunch_suitable: false, is_coffee_stop: false, is_meal_stop: false };
  }
  if (hotelName && !mealName && !snackName) {
    return { meal_type: 'hotel_dining' as MealType, is_lunch_suitable: false, is_coffee_stop: false, is_meal_stop: false };
  }
  if (coffee) {
    return { meal_type: 'coffee' as MealType, is_lunch_suitable: false, is_coffee_stop: true, is_meal_stop: true };
  }
  if (dessertName && !mealName && !snackName) {
    return { meal_type: 'dessert' as MealType, is_lunch_suitable: false, is_coffee_stop: false, is_meal_stop: true };
  }
  if (snackName) {
    return { meal_type: 'snack' as MealType, is_lunch_suitable: true, is_coffee_stop: false, is_meal_stop: true };
  }
  return { meal_type: 'meal' as MealType, is_lunch_suitable: true, is_coffee_stop: false, is_meal_stop: true };
}

export function normalizePoi(raw: Poi): Poi {
  const name = String(raw.name || raw.display_name || raw.normalized_name || raw.poi_id);
  const isHotel = raw.poi_kind === 'hotel' || raw.poi_type === 'accommodation' || raw.entity_kind === 'hotel';
  const meal = deriveMealSemantics({ ...raw, name });
  return {
    ...raw,
    poi_id: String(raw.poi_id),
    name,
    lng: Number(raw.lng),
    lat: Number(raw.lat),
    rating: Number(raw.rating || 0),
    avg_cost: Number(raw.avg_cost || 0),
    review_count: Number(raw.review_count || 0),
    suggested_duration_min: isHotel ? 0 : Number(raw.suggested_duration_min || raw.avg_visit_duration_min || 90),
    poi_type: isHotel ? 'accommodation' : meal.is_meal_stop || meal.is_coffee_stop ? 'food' : 'culture',
    poi_kind: isHotel ? 'hotel' : raw.poi_kind,
    entity_kind: isHotel ? 'hotel' : raw.entity_kind,
    ...(isHotel
      ? { meal_type: 'hotel_dining' as MealType, is_lunch_suitable: false, is_coffee_stop: false, is_meal_stop: false }
      : meal),
  };
}

export function uniqueByName(items: Poi[]): Poi[] {
  const seenIds = new Set<string>();
  const seenNames = new Set<string>();
  return items.filter((item) => {
    const name = normalizePoiName(item.name);
    if (seenIds.has(item.poi_id) || seenNames.has(name)) return false;
    seenIds.add(item.poi_id);
    if (name) seenNames.add(name);
    return true;
  });
}

export function attractionGroupKey(item: Pick<Poi, 'name' | 'area' | 'district'>): string {
  const normalizedName = normalizePoiName(item.name);
  if (normalizedName.includes('\u6545\u5bab\u535a\u7269\u9662')) return '\u6545\u5bab\u535a\u7269\u9662';
  if (normalizedName.includes('\u5929\u5b89\u95e8\u5e7f\u573a')) return '\u5929\u5b89\u95e8\u5e7f\u573a';
  if (normalizedName.includes('\u4e2d\u56fd\u56fd\u5bb6\u535a\u7269\u9986')) return '\u4e2d\u56fd\u56fd\u5bb6\u535a\u7269\u9986';
  if (normalizedName.includes('\u5317\u6d77\u516c\u56ed')) return '\u5317\u6d77\u516c\u56ed';
  if (normalizedName.includes('\u666f\u5c71\u516c\u56ed')) return '\u666f\u5c71\u516c\u56ed';
  if (normalizedName.includes('故宫博物院')) return '故宫博物院';
  if (normalizedName.includes('天安门广场')) return '天安门广场';
  if (normalizedName.includes('中国国家博物馆')) return '中国国家博物馆';
  if (normalizedName.includes('北海公园')) return '北海公园';
  if (normalizedName.includes('景山公园')) return '景山公园';
  const baseName = String(item.name || '').split(/[-—–]/)[0]?.trim();
  return normalizePoiName(baseName || item.name || item.area || item.district || '');
}

export function uniqueByAttractionGroup(items: Poi[]): Poi[] {
  const seenIds = new Set<string>();
  const seenGroups = new Set<string>();
  return items.filter((item) => {
    const group = attractionGroupKey(item);
    if (seenIds.has(item.poi_id) || (group && seenGroups.has(group))) return false;
    seenIds.add(item.poi_id);
    if (group) seenGroups.add(group);
    return true;
  });
}

export function poiText(item: Poi): string {
  return [
    item.name,
    item.category,
    item.poi_type,
    item.family_friendliness,
    ...(Array.isArray(item.planning_tags) ? item.planning_tags : []),
    ...(Array.isArray(item.evidence_tags) ? item.evidence_tags : []),
  ].map((value) => String(value || '').toLowerCase()).join(' ');
}

export function isFoodPoi(item: Poi): boolean {
  const mealType = String(item.meal_type || '').toLowerCase();
  if (mealType === 'invalid' || mealType === 'non_food' || mealType === 'hotel_dining') return false;
  const text = poiText(item);
  const name = String(item.name || '');
  if (/\u9152\u5e97|\u5bbe\u9986|\u5ba2\u6808|\u6f2b\u5fc3\u5e9c|\u4f4f\u5bbf/.test(name)) return false;
  if (/\u552e\u7968\u5904|\u8bb2\u89e3|\u670d\u52a1\u4e2d\u5fc3|\u5e02\u6c11\u6587\u5316\u4e2d\u5fc3|停车场|出入口|足球场|体育中心|运动场|售票处|卫生间|游客中心|观众服务中心/.test(name)) return false;
  return ['meal', 'snack', 'coffee', 'dessert'].includes(mealType)
    || /(^|\s)(food|dining|restaurant|meal|snack|coffee|cafe)(\s|$)/.test(text)
    || Boolean(item.is_lunch_suitable || item.is_coffee_stop);
}

export function isLunchPoi(item: Poi): boolean {
  return Boolean(item.is_lunch_suitable);
}

export function isCoffeePoi(item: Poi): boolean {
  return Boolean(item.is_coffee_stop);
}

export function isSnackOrTeaPoi(item: Poi): boolean {
  return item.meal_type === 'snack'
    || item.meal_type === 'coffee'
    || item.meal_type === 'dessert'
    || /茶馆|夜市|档口|小食铺|小吃/.test(String(item.name || ''));
}

export function isWeakFoodPoi(item: Poi): boolean {
  const name = String(item.name || '');
  const text = poiText(item);
  const hasChinese = /[\u4e00-\u9fff]/.test(name);
  const weakEvidence = Number(item.rating || 0) <= 0 && Number(item.review_count || 0) <= 0;
  if (!hasChinese && weakEvidence) return true;
  if (/\d+(?:\u53f7|\?)(?:\u4e66\u5427|\u8336\u9986|\u5496\u5561\u9986|\u5c0f\u98df\u94fa|\u9152\u9986|\u9910\u9986|\u9910\u5385|\u996d\u9986|\u6587\u521b|\u5546\u5e97|\u5c0f\u5e97|\?+)|\u4e66\u5427|\u6587\u521b|\u5546\u5e97/.test(name)) return true;
  if (/\d+号(茶馆|小食铺|酒馆|餐馆|餐厅|饭馆|书吧|文创|商店|小店)/.test(name)) return true;
  if (/shared_commerce_pool/.test(text) && /茶馆|小食铺|酒馆/.test(name)) return true;
  if (/酒店|宾馆|客栈|漫心府|花间堂|住宿/.test(name)) return true;
  if (/肯德基|麦当劳|兰州牛肉拉面|臭豆腐|SLOWBOAT|悠航|精酿|酒吧|啤酒/.test(name)) return true;
  if (/咖啡|coffee|cafe|下午茶|甜品|茶馆/.test(name) && item.meal_type !== 'coffee' && item.meal_type !== 'dessert') return true;
  return false;
}

function isLargeScenicSubPoiName(name: string): boolean {
  const scenicNames = ['故宫博物院', '天坛公园', '北海公园', '景山公园', '颐和园', '圆明园'];
  if (name === '圆明园遗址公园') return false;
  return scenicNames.some((scenicName) => name.startsWith(scenicName) && !['', '遗址公园'].includes(name.slice(scenicName.length)));
}

export function isClassicBackbonePoi(item: Poi): boolean {
  const name = String(item.name || '');
  if (/石碑|碑刻|观景平台|管理处|服务处|科普小屋|文化活动室|售票|入口|出口|卫生间|停车场/.test(name)) return false;
  return /故宫博物院|天坛公园|颐和园|圆明园|听鹂馆|八达岭长城|中国长城博物馆|景山公园|北海公园|什刹海|后海公园|天安门广场|鼓楼|南锣鼓巷|雍和宫|奥林匹克公园|北京环球|环球影城|环球城市大道/.test(name);
}

export function isRecommendablePoi(item: Poi): boolean {
  if (isFoodPoi(item)) return !isWeakFoodPoi(item);
  const name = String(item.name || '');
  const text = poiText(item);
  const hasChinese = /[\u4e00-\u9fff]/.test(name);
  const latinCount = (name.match(/[A-Za-z]/g) || []).length;
  const weakEvidence = Number(item.review_count || 0) <= 0 && !/museum|art_gallery|attraction|scene:indoor|theme:museum|theme:art/.test(text);
  if (!hasChinese) return false;
  if (/\d+(?:\u53f7|\?)(?:\u4e66\u5427|\u8336\u9986|\u5496\u5561\u9986|\u5c0f\u98df\u94fa|\u9152\u9986|\u9910\u9986|\u9910\u5385|\u996d\u9986|\u6587\u521b|\u5546\u5e97|\u5c0f\u5e97|\?+)|\u4e66\u5427|\u6587\u521b|\u5546\u5e97/.test(name)) return false;
  if (latinCount >= 4 && weakEvidence) return false;
  if (/\u9152\u5e97|\u5bbe\u9986|\u6f2b\u5fc3\u5e9c|\u5ba2\u6808|\u4f4f\u5bbf|花间堂/.test(name)) return false;
  if (/\u5e02\u6c11\u6587\u5316\u4e2d\u5fc3|\u793e\u533a|\u5c45\u6c11|\u8857\u9053\u529e|市民文化中心|社区|居民|街道办|金鱼展|观景平台/.test(name)) return false;
  if (isLargeScenicSubPoiName(name)) return false;
  if (/\u5efa\u8bbe\u4e2d|\u89c2\u4f17\u670d\u52a1\u4e2d\u5fc3|\u8bb2\u89e3\u670d\u52a1\u5904|停车场|出入口|足球场|体育中心|运动场|售票处|卫生间|游客中心|观众服务中心/.test(name)) return false;
  if (!isClassicBackbonePoi(item) && /石碑|碑刻|观景平台|管理处|服务处|科普小屋|文化活动室|售票|入口|出口|卫生间|停车场/.test(name)) return false;
  return true;
}

export function isOverSpecificCulturePoi(item: Poi): boolean {
  if (isClassicBackbonePoi(item)) return false;
  const name = String(item.name || '');
  const latinCount = (name.match(/[A-Za-z]/g) || []).length;
  return latinCount >= 4
    || /金鱼展|观景平台|碑|石碑|遗址$|美术馆|艺术馆|创意产业园|文化宫|劳动人民文化宫|HERE|Mood|SLOWBOAT/i.test(name);
}

export function isIndoorCulturePoi(item: Poi): boolean {
  if (isFoodPoi(item)) return false;
  const text = poiText(item);
  return /museum|art_gallery|exhibition|theme:museum|theme:art|\u535a\u7269\u9986|\u7f8e\u672f\u9986|\u827a\u672f\u4e2d\u5fc3|\u5c55\u89c8\u9986|\u79d1\u6559\u6587\u5316/.test(text);
}

export function mealQualityScore(item: Poi): number {
  let score = 0;
  if (item.meal_type === 'meal') score += 12;
  if (item.meal_type === 'snack') score += 10;
  if (item.meal_type === 'coffee') score -= 6;
  if (item.meal_type === 'dessert') score -= 8;
  if (item.meal_type === 'hotel_dining' || item.meal_type === 'invalid') score -= 20;
  if (Number(item.avg_cost || 0) > 0) score += 3;
  return score;
}

export function foodPreferenceScore(item: Poi, request: TravelPlanningRequest): number {
  if (!isFoodPoi(item)) return 0;
  const goal = String(request.goal || '');
  const name = String(item.name || '');
  const text = poiText(item);
  const cost = Number(item.avg_cost || 0);
  let score = 0;
  const pairs: Array<[RegExp, RegExp]> = [
    [/烤鸭|北京菜/, /烤鸭|四季民福|全聚德|便宜坊|大董|利群/],
    [/涮肉|铜锅|火锅/, /涮肉|铜锅|南门|鸦儿李记|烤肉季/],
    [/炸酱面/, /炸酱面|方砖厂/],
    [/豆汁|小吃|老北京小吃/, /豆汁|小吃|护国寺|锦馨|紫光园|门钉肉饼|烧麦/],
    [/咖啡|下午茶/, /咖啡|coffee|cafe|下午茶/],
  ];
  for (const [intent, foodName] of pairs) {
    if (intent.test(goal) && foodName.test(name)) score += 60;
  }
  if (request.preference_signals?.roast_duck && /烤鸭|四季民福|全聚德|便宜坊|大董|利群/.test(name)) score += 70;
  if (request.preference_signals?.hotpot && /涮肉|铜锅|南门|鸦儿李记|烤肉季/.test(name)) score += 60;
  if (request.preference_signals?.zhajiangmian && /炸酱面|方砖厂/.test(name)) score += 60;
  if (request.preference_signals?.beijing_snack && /豆汁|小吃|护国寺|锦馨|紫光园|门钉肉饼|烧麦/.test(name)) score += 50;
  if (/好吃|吃好|吃点好的|靠谱|美食|口碑|招牌|特色|不踩雷|推荐餐厅/.test(goal)) {
    if (/四季民福|便宜坊|大董|全聚德|南门涮肉|鸦儿李记|烤肉季|方砖厂|紫光园|护国寺|门钉肉饼|京味|北京菜|烤鸭|涮肉|铜锅|炸酱面/.test(name)) score += 34;
    if (/西餐|TRB|Forbidden City|coffee|cafe|咖啡|下午茶/i.test(name)) score -= /西餐|高级|米其林|fine|精致|约会/.test(goal) ? 0 : 28;
    if (/shared_commerce_pool|小食铺|茶馆/.test(text) && !/小吃|茶馆|下午茶|咖啡/.test(goal)) score -= 20;
  }
  if (/北京|故宫|颐和园|天坛|什刹海|前门|王府井/.test(goal) && /好吃|美食|特色|本地|老北京|吃/.test(goal)) {
    if (/北京菜|京味|烤鸭|涮肉|铜锅|炸酱面|爆肚|烧麦|豆汁|卤煮|门钉肉饼|护国寺|紫光园|鸦儿李记|南门涮肉|烤肉季|四季民福|全聚德|便宜坊/.test(name)) score += 46;
  }
  if (/预算|3000|舒适|品质|吃好/.test(goal) && cost >= 80 && cost <= 260) score += 8;
  if (/预算|省钱|便宜|以内/.test(goal) && cost > 180) score -= 18;
  if (/咖啡|下午茶/.test(goal) && !/咖啡|coffee|cafe|下午茶/.test(name)) score -= 20;
  return score;
}
