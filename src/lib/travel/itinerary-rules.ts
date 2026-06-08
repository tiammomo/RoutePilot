import { BEIJING_AREA_ANCHORS } from '@/lib/travel/constants';
import { normalizePoiName } from '@/lib/travel/poi-model';

export function landmarkPoiIdsForName(name: string): string[] {
  const normalized = normalizePoiName(name);
  if (/故宫|紫禁城|forbiddencity|palacemuseum/i.test(normalized)) {
    return ['amap_B000A8UIN8'];
  }
  if (/(长城|八达岭|慕田峪|居庸关|greatwall|badaling)/i.test(normalized)) {
    return ['fixture_badaling_great_wall'];
  }
  if (/颐和园|summerpalace/i.test(normalized)) {
    return ['fixture_summer_palace'];
  }
  if (/圆明园|yuanmingyuan/i.test(normalized)) {
    return ['fixture_yuanmingyuan_park'];
  }
  if (/环球影城|北京环球|universal/i.test(normalized)) {
    return ['fixture_universal_beijing_resort'];
  }
  return [];
}

export function classicPoiIdsForArea(area?: string | null): string[] {
  const normalized = normalizePoiName(area || '');
  if (!normalized) return [];
  if (/故宫|紫禁城/.test(normalized)) return ['amap_B000A8UIN8', 'amap_B000A7I1OL', 'amap_B000A80UL1'];
  if (/天坛/.test(normalized)) return ['amap_B000A81CB2', 'real_dining_amap_b000a80wkg', 'amap_B000A16BBC'];
  if (/颐和园/.test(normalized)) return ['fixture_summer_palace', 'fixture_tingliguan_summer_palace', 'fixture_yuanmingyuan_park'];
  if (/圆明园/.test(normalized)) return ['fixture_yuanmingyuan_park', 'fixture_summer_palace', 'fixture_tingliguan_summer_palace'];
  if (/长城|八达岭/.test(normalized)) return ['fixture_badaling_great_wall', 'fixture_badaling_lunch_anchor', 'fixture_badaling_great_wall_museum'];
  if (/环球影城|北京环球|universal/.test(normalized)) return ['fixture_universal_beijing_resort', 'fixture_universal_citywalk_lunch', 'fixture_universal_citywalk'];
  if (/北海/.test(normalized)) return ['amap_B000A80UL1', 'amap_B000A7I1OL', 'amap_B000A7O5PK'];
  if (/什刹海|后海/.test(normalized)) return ['amap_B000A7O5PK', 'amap_B0FFFS33G2', 'real_dining_kaorouji_shichahai'];
  if (/天安门/.test(normalized)) return ['amap_B000A83C1S', 'real_dining_quanjude_qianmen', 'amap_B000A8UIN8'];
  if (/南锣鼓巷/.test(normalized)) return ['amap_B0FFFAH7I9', 'amap_B0FFFS33G2', 'real_dining_amap_b0j21ufgsm'];
  if (/雍和宫|地坛/.test(normalized)) return ['amap_B000A7BGMG'];
  return [];
}

export function anchorForName(name?: string | null) {
  const normalized = normalizePoiName(name || '');
  const direct = Object.entries(BEIJING_AREA_ANCHORS)
    .find(([area]) => normalized.includes(normalizePoiName(area)) || normalizePoiName(area).includes(normalized));
  return direct ? { area: direct[0], ...direct[1] } : null;
}
