export function adjustmentWantsFreshPlan(text: string): boolean {
  return /全新|重新来|不保留|重新安排所有|全部重排/.test(text);
}

export function adjustmentWantsFoodChange(text: string): boolean {
  return /(午餐|午饭|中午吃|吃饭|餐饮|餐厅|饭店|小吃|咖啡|正餐|美食|把午餐|换午餐|午餐换|换成.*(?:午餐|午饭|小吃|咖啡|餐厅|饭店|正餐|美食)|改成.*(?:午餐|午饭|小吃|咖啡|餐厅|饭店|正餐|美食))/.test(text);
}

export function adjustmentWantsSnack(text: string): boolean {
  return /小吃|下午茶|甜品|茶饮|奶茶|咖啡|预算\s*\d+\s*以内的小吃|换成.*(?:小吃|下午茶|甜品|茶饮|奶茶|咖啡)/.test(text);
}

export function parseTargetedReplacementIndex(text: string, total: number): number | null {
  if (!total || !/(换成|换一个|替换|改成|更换)/.test(text)) return null;
  if (/最后一个|最后1个|末尾|最后一站|最后1站/.test(text)) return total - 1;
  const chineseNumbers: Record<string, number> = {
    一: 0,
    二: 1,
    两: 1,
    三: 2,
    四: 3,
    五: 4,
    六: 5,
  };
  const chineseMatch = text.match(/第\s*([一二两三四五六])\s*(?:个|站|处)?(?:点|景点|地点|餐厅|饭店|POI)?/);
  if (chineseMatch?.[1] && chineseMatch[1] in chineseNumbers) {
    const index = chineseNumbers[chineseMatch[1]];
    return index >= 0 && index < total ? index : null;
  }
  const digitMatch = text.match(/第\s*(\d+)\s*(?:个|站|处)?(?:点|景点|地点|餐厅|饭店|POI)?/i);
  if (digitMatch?.[1]) {
    const index = Number(digitMatch[1]) - 1;
    return index >= 0 && index < total ? index : null;
  }
  return null;
}

export function stableWantsFreshPlan(text: string): boolean {
  return /\u5168\u65b0|\u91cd\u65b0\u6765|\u4e0d\u4fdd\u7559|\u91cd\u65b0\u5b89\u6392\u6240\u6709|\u5168\u90e8\u91cd\u6392/.test(text);
}

export function stableWantsFoodChange(text: string): boolean {
  return /(\u5348\u9910|\u5348\u996d|\u4e2d\u5348\u5403|\u5403\u996d|\u9910\u996e|\u9910\u5385|\u996d\u5e97|\u5c0f\u5403|\u5496\u5561|\u6b63\u9910|\u7f8e\u98df|\u6362\u6210.*(?:\u5348\u9910|\u5348\u996d|\u5c0f\u5403|\u5496\u5561|\u9910\u5385|\u996d\u5e97|\u6b63\u9910|\u7f8e\u98df)|\u6539\u6210.*(?:\u5348\u9910|\u5348\u996d|\u5c0f\u5403|\u5496\u5561|\u9910\u5385|\u996d\u5e97|\u6b63\u9910|\u7f8e\u98df))/.test(text);
}

export function stableWantsSnack(text: string): boolean {
  return /\u5c0f\u5403|\u4e0b\u5348\u8336|\u751c\u54c1|\u8336\u996e|\u5976\u8336|\u5496\u5561|\u9884\u7b97\s*\d+\s*\u4ee5\u5185\u7684\u5c0f\u5403|\u6362\u6210.*(?:\u5c0f\u5403|\u4e0b\u5348\u8336|\u751c\u54c1|\u8336\u996e|\u5976\u8336|\u5496\u5561)/.test(text);
}

export function stableWantsFormalMeal(text: string): boolean {
  return /\u6b63\u9910|\u9910\u5385|\u996d\u5e97|\u9002\u5408\u5348\u9910|\u4e0d\u8981\u5496\u5561|\u522b\u8981\u5496\u5561/.test(text);
}

export function stablePreservesFood(text: string): boolean {
  return /\u5348\u9910\u4e0d\u53d8|\u9910\u996e\u4e0d\u53d8|\u5403\u996d\u4e0d\u53d8|\u996d\u5e97\u4e0d\u53d8|\u4fdd\u7559(?:\u5f53\u524d|\u539f\u6765|\u539f\u6709)?\u5348\u9910|\u4fdd\u7559(?:\u5f53\u524d|\u539f\u6765|\u539f\u6709)?\u9910\u996e|\u4fdd\u7559(?:\u5f53\u524d|\u539f\u6765|\u539f\u6709)?\u996d\u5e97/.test(text);
}

export function stablePreservesCulture(text: string): boolean {
  return /\u666f\u70b9\u4e0d\u53d8|\u6587\u5316\u70b9\u4e0d\u53d8|\u5176\u4ed6\u666f\u70b9\u4e0d\u53d8|\u4fdd\u7559\u666f\u70b9|\u4fdd\u7559\u6587\u5316\u70b9/.test(text);
}

export function stablePreservesOthers(text: string): boolean {
  return /\u5176\u4ed6\u5730\u65b9\u4e0d\u53d8|\u5176\u4ed6\u5730\u70b9\u4e0d\u53d8|\u5176\u4ed6\u4e0d\u53d8|\u4e0d\u53d8|\u4fdd\u7559\u5176\u4ed6/.test(text);
}

export function stableWantsIndoor(text: string): boolean {
  return /\u5ba4\u5185|\u4e0d\u6652|\u4e0b\u96e8|\u5c55\u9986|\u535a\u7269\u9986|\u7f8e\u672f\u9986|\u827a\u672f\u4e2d\u5fc3/.test(text);
}

export function stableWantsAddStop(text: string): boolean {
  return /\u52a0\u4e00\u4e2a|\u6dfb\u52a0|\u52a0\u4e0a|\u987a\u8def\u52a0|\u518d\u5b89\u6392\u4e00\u4e2a|\u591a\u4e00\u4e2a|\u589e\u52a0\u4e00\u4e2a|\u518d\u52a0|\u8fd8\u60f3|\u4e5f\u60f3|\u60f3\u53bb|\u6709\u70b9\u60f3\u53bb|\u987a\u4fbf|\u653e\u8fdb\u53bb|\u6392\u8fdb\u53bb/.test(text);
}

export function stableWantsGenericAttraction(text: string): boolean {
  return /\u666f\u70b9|\u666f\u533a|\u5730\u70b9|\u5730\u65b9|\u6587\u5316\u70b9|\u597d\u73a9\u7684|\u987a\u8def/.test(text);
}

export function stableTargetedReplacementIndex(text: string, total: number): number | null {
  if (!total || !/(\u6362\u6210|\u6362\u4e00\u4e2a|\u66ff\u6362|\u6539\u6210|\u66f4\u6362)/.test(text)) return null;
  if (/\u6700\u540e\u4e00\u4e2a|\u6700\u540e1\u4e2a|\u672b\u5c3e|\u6700\u540e\u4e00\u7ad9|\u6700\u540e1\u7ad9/.test(text)) return total - 1;
  const chineseNumbers: Record<string, number> = {
    '\u4e00': 0,
    '\u4e8c': 1,
    '\u4e24': 1,
    '\u4e09': 2,
    '\u56db': 3,
    '\u4e94': 4,
    '\u516d': 5,
  };
  const chineseMatch = text.match(/\u7b2c\s*([\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d])\s*(?:\u4e2a|\u7ad9|\u5904)?(?:\u70b9|\u666f\u70b9|\u5730\u70b9|\u9910\u5385|\u996d\u5e97|POI)?/);
  if (chineseMatch?.[1] && chineseMatch[1] in chineseNumbers) {
    const index = chineseNumbers[chineseMatch[1]];
    return index >= 0 && index < total ? index : null;
  }
  const digitMatch = text.match(/\u7b2c\s*(\d+)\s*(?:\u4e2a|\u7ad9|\u5904)?(?:\u70b9|\u666f\u70b9|\u5730\u70b9|\u9910\u5385|\u996d\u5e97|POI)?/i);
  if (digitMatch?.[1]) {
    const index = Number(digitMatch[1]) - 1;
    return index >= 0 && index < total ? index : null;
  }
  return null;
}
